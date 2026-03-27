"""
reports/views.py — HTTP layer فقط (thin views)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
كل منطق البيانات  → ReportDataService
كل منطق Excel     → ExcelService
PDF               → core.pdf_utils.render_pdf
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone

from assessments.models import SubjectClassSetup
from core.models import ClassGroup, CustomUser, StudentEnrollment
from core.pdf_utils import render_pdf

from core.permissions import leadership_required, role_required

from .services import ExcelService, ReportDataService

# ── helpers مشتركة ──────────────────────────────────────────────────


def _has_parent_access(request, student, school) -> bool:
    """يتحقق من أن المستخدم الحالي هو ولي أمر مرتبط بالطالب في هذه المدرسة."""
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
def reports_index(request):
    """فهرس التقارير — تبويبات + فلاتر + بطاقات فصول."""
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    tab = request.GET.get("tab", "results")
    grade_filter = request.GET.get("grade", "")
    level_filter = request.GET.get("level", "")

    if request.user.is_admin():
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).order_by("grade", "section")
    else:
        ids = SubjectClassSetup.objects.filter(
            school=school, teacher=request.user, academic_year=year
        ).values_list("class_group_id", flat=True)
        classes = ClassGroup.objects.filter(id__in=ids).order_by("grade", "section")

    # فلترة
    if level_filter:
        classes = classes.filter(level_type=level_filter)
    if grade_filter:
        classes = classes.filter(grade=grade_filter)

    # الصفوف المتاحة فعلياً (للفلاتر)
    all_classes = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
    if level_filter:
        available_grades = (
            all_classes.filter(level_type=level_filter)
            .values_list("grade", flat=True)
            .distinct()
            .order_by("grade")
        )
    else:
        available_grades = all_classes.values_list("grade", flat=True).distinct().order_by("grade")

    ctx = {
        "classes": classes,
        "year": year,
        "school": school,
        "tab": tab,
        "grade_filter": grade_filter,
        "level_filter": level_filter,
        "available_grades": available_grades,
        "GRADES": ClassGroup.GRADES,
        "LEVELS": ClassGroup.LEVELS,
    }

    return render(request, "reports/index.html", ctx)


# ══════════════════════════════════════════════════════════════════════
# PDF — تقارير الفصل
# ══════════════════════════════════════════════════════════════════════


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
def class_results_pdf(request, class_id):
    """PDF: كشف نتائج كامل لجميع طلاب فصل"""
    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    preview = request.GET.get("preview") == "1"

    ctx = ReportDataService.get_class_results(class_grp, school, year)

    # ── Guard: لا توليد PDF عند عدم وجود طلاب (reportlab يفشل مع جدول فارغ) ──
    if not ctx.get("student_rows"):
        if preview:
            return render(request, "reports/class_results.html", ctx)
        return render(
            request,
            "reports/class_results.html",
            {**ctx, "_empty_msg": "لا يوجد طلاب في هذا الفصل لتوليد التقرير."},
        )

    if preview:
        return render(request, "reports/class_results.html", ctx)

    html = render_to_string("reports/class_results.html", ctx, request=request)
    return render_pdf(
        html,
        f"نتائج_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
    )


@login_required
@leadership_required
def class_certificates_pdf(request, class_id):
    """PDF: شهادات جميع طلاب فصل في ملف واحد"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
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
@leadership_required
def attendance_report_pdf(request, class_id):
    """PDF: تقرير حضور وغياب الفصل"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
def student_result_pdf(request, student_id):
    """PDF: تقرير نتيجة طالب مفصّل"""
    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
def student_annual_result_pdf(request, student_id):
    """كشف نتائج الطالب السنوي — PDF للطباعة الرسمية"""
    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    preview = request.GET.get("preview") == "1"

    if not (request.user.is_admin() or request.user.is_teacher() or request.user == student):
        if not _has_parent_access(request, student, school):
            return HttpResponse("غير مسموح", status=403)

    ctx = ReportDataService.get_student_report(student, school, year)
    _set_final_status(ctx)

    if preview:
        return render(request, "reports/student_result_pdf.html", ctx)

    html = render_to_string("reports/student_result_pdf.html", ctx, request=request)
    return render_pdf(html, f"كشف_نتائج_{student.full_name}_{year}.pdf")


@login_required
@leadership_required
def student_certificate_pdf(request, student_id):
    """PDF: شهادة نتيجة سنوية رسمية"""
    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
def class_results_excel(request, class_id):
    """Excel: كشف نتائج الفصل"""
    if not (request.user.is_admin() or request.user.is_teacher()):
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    return ExcelService.class_results_excel(
        class_grp, school, request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    )


@login_required
@leadership_required
def attendance_excel(request, class_id):
    """Excel: تقرير الغياب"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    return ExcelService.attendance_excel(
        class_grp, school, request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    )


@login_required
@leadership_required
def behavior_excel(request):
    """Excel: تقرير المخالفات السلوكية"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    return ExcelService.behavior_excel(
        school, request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    )
