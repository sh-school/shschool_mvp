"""
reports/views.py — HTTP layer فقط (thin views)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
كل منطق البيانات  → ReportDataService
كل منطق Excel     → ExcelService
PDF               → core.pdf_utils.render_pdf
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone

from assessments.models import SubjectClassSetup
from core.models import ClassGroup, CustomUser, StudentEnrollment
from core.pdf_utils import render_pdf

from .services import ExcelService, ReportDataService

# ── helpers مشتركة ──────────────────────────────────────────────────


def _has_parent_access(request, student, school) -> bool:
    from core.models import ParentStudentLink

    return ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).exists()


def _set_final_status(ctx: dict) -> None:
    """يضيف final_status و status_color إلى السياق"""
    if ctx["failed"] == 0 and ctx["passed"] > 0:
        ctx.update(final_status="ناجح", status_color="#15803d")
    elif ctx["failed"] > 0:
        ctx.update(final_status="راسب", status_color="#dc2626")
    else:
        ctx.update(final_status="غير مكتمل", status_color="#d97706")


# ── فهرس التقارير ───────────────────────────────────────────────────


@login_required
def reports_index(request):
    school = request.user.get_school()
    year = request.GET.get("year", "2025-2026")

    if request.user.is_admin():
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).order_by("grade", "section")
    else:
        ids = SubjectClassSetup.objects.filter(
            school=school, teacher=request.user, academic_year=year
        ).values_list("class_group_id", flat=True)
        classes = ClassGroup.objects.filter(id__in=ids)

    return render(
        request,
        "reports/index.html",
        {
            "classes": classes,
            "year": year,
            "school": school,
        },
    )


# ══════════════════════════════════════════════════════════════════════
# PDF — تقارير الفصل
# ══════════════════════════════════════════════════════════════════════


@login_required
def class_results_pdf(request, class_id):
    """PDF: كشف نتائج كامل لجميع طلاب فصل"""
    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year", "2025-2026")
    preview = request.GET.get("preview") == "1"

    ctx = ReportDataService.get_class_results(class_grp, school, year)
    if preview:
        return render(request, "reports/class_results.html", ctx)

    html = render_to_string("reports/class_results.html", ctx, request=request)
    return render_pdf(
        html,
        f"نتائج_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
    )


@login_required
def class_certificates_pdf(request, class_id):
    """PDF: شهادات جميع طلاب فصل في ملف واحد"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year", "2025-2026")
    preview = request.GET.get("preview") == "1"

    enrollments = (
        StudentEnrollment.objects.filter(class_group=class_grp, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    students_ctx = []
    for enr in enrollments:
        ctx = ReportDataService.get_student_report(enr.student, school, year)
        _set_final_status(ctx)
        students_ctx.append(ctx)

    page_ctx = {
        "students_ctx": students_ctx,
        "class_group": class_grp,
        "school": school,
        "year": year,
        "print_date": timezone.now().date(),
    }
    if preview:
        return render(request, "reports/class_certificates.html", page_ctx)

    html = render_to_string("reports/class_certificates.html", page_ctx, request=request)
    return render_pdf(
        html,
        f"شهادات_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
    )


@login_required
def attendance_report_pdf(request, class_id):
    """PDF: تقرير حضور وغياب الفصل"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year", "2025-2026")
    preview = request.GET.get("preview") == "1"

    ctx = ReportDataService.get_attendance_report(class_grp, school, year)
    if preview:
        return render(request, "reports/attendance_report.html", ctx)

    html = render_to_string("reports/attendance_report.html", ctx, request=request)
    return render_pdf(
        html,
        f"غياب_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
    )


# ══════════════════════════════════════════════════════════════════════
# PDF — تقارير الطالب الفردي
# ══════════════════════════════════════════════════════════════════════


@login_required
def student_result_pdf(request, student_id):
    """PDF: تقرير نتيجة طالب مفصّل"""
    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", "2025-2026")
    preview = request.GET.get("preview") == "1"

    if not (request.user.is_admin() or request.user.is_teacher() or request.user == student):
        if not _has_parent_access(request, student, school):
            return HttpResponse("غير مسموح", status=403)

    ctx = ReportDataService.get_student_report(student, school, year)
    if preview:
        return render(request, "reports/student_result.html", ctx)

    html = render_to_string("reports/student_result.html", ctx, request=request)
    return render_pdf(html, f"نتيجة_{student.full_name}_{year}.pdf")


@login_required
def student_certificate_pdf(request, student_id):
    """PDF: شهادة نتيجة سنوية رسمية"""
    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", "2025-2026")
    preview = request.GET.get("preview") == "1"

    if not (request.user.is_admin() or request.user.is_teacher()):
        if not _has_parent_access(request, student, school):
            return HttpResponse("غير مسموح", status=403)

    ctx = ReportDataService.get_student_report(student, school, year)
    _set_final_status(ctx)

    if preview:
        return render(request, "reports/certificate.html", ctx)

    html = render_to_string("reports/certificate.html", ctx, request=request)
    return render_pdf(html, f"شهادة_{student.full_name}_{year}.pdf")


# ══════════════════════════════════════════════════════════════════════
# Excel Exports — عبر ExcelService
# ══════════════════════════════════════════════════════════════════════


@login_required
def class_results_excel(request, class_id):
    """Excel: كشف نتائج الفصل"""
    if not (request.user.is_admin() or request.user.is_teacher()):
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    return ExcelService.class_results_excel(class_grp, school, request.GET.get("year", "2025-2026"))


@login_required
def attendance_excel(request, class_id):
    """Excel: تقرير الغياب"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    return ExcelService.attendance_excel(class_grp, school, request.GET.get("year", "2025-2026"))


@login_required
def behavior_excel(request):
    """Excel: تقرير المخالفات السلوكية"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    return ExcelService.behavior_excel(school, request.GET.get("year", "2025-2026"))
