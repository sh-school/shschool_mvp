"""
reports/views.py — HTTP layer فقط (thin views)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
كل منطق البيانات  → ReportDataService
كل منطق Excel     → ExcelService
PDF               → core.pdf_utils.render_pdf
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.clickjacking import xframe_options_sameorigin

from assessments.models import SubjectClassSetup
from core.academic_calendar import academic_year_for
from core.models import ClassGroup, CustomUser, StudentEnrollment
from core.models.academic import grade_number
from core.pdf_utils import render_pdf
from core.permissions import leadership_required, role_required

from .services import ExcelService, ReportDataService


@login_required
def report_viewer(request):
    """يعرض تقريراً داخل صفحةٍ لها فتات خبز وزرّ رجوع وتحميل.

    كانت «المعاينة» تفتح تبويباً جديداً وتُعيد وثيقة الطباعة نفسها — قالبٌ
    يمتدّ من `base_qatar_report` بلا قائمة ولا فتات خبز ولا رجوع. طريقٌ مسدود.

    و`r` يُطابَق على قائمةٍ بيضاء ثم يُعكَس بـ`reverse`: لا يُبنى مسارٌ من نصّ
    المستخدم، فلا يصير الحقل باباً لإعادة توجيهٍ إلى أيّ عنوان.
    """
    name = request.GET.get("r", "")
    if name not in VIEWABLE_REPORTS:
        messages.error(request, "تقرير غير معروف.")
        return redirect("reports_index")

    obj_id = request.GET.get("id", "")
    try:
        target = reverse(name, args=[obj_id])
    except Exception:  # noqa: BLE001 — معرّف غير صالح: رسالةٌ لا انهيار
        messages.error(request, "معرّف غير صالح.")
        return redirect("reports_index")

    passthrough = [
        (k, v) for k, v in request.GET.items() if k in ("year", "paper", "tab", "level", "grade")
    ]
    query = urlencode(passthrough)

    return render(
        request,
        "reports/report_viewer.html",
        {
            "report_title": VIEWABLE_REPORTS[name],
            "report_url": f"{target}?{query}" if query else f"{target}?",
            "back_query": f"?{query}" if query else "",
        },
    )


# ── helpers مشتركة ──────────────────────────────────────────────────


def _has_parent_access(request, student, school) -> bool:
    """يتحقق من أن المستخدم الحالي هو ولي أمر مرتبط بالطالب في هذه المدرسة."""
    from core.models import ParentStudentLink

    return ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).exists()


def _teacher_can_access_class(request, school, class_grp, year) -> bool:
    """[SEC-04] القيادة/الإدارة/المنسّق: وصول إشرافي مبرّر. المعلّم: فصوله فقط."""
    user = request.user
    role = user.get_role()
    if (
        user.is_superuser
        or user.is_admin()
        or role
        in (
            "principal",
            "vice_academic",
            "vice_admin",
            "coordinator",
        )
    ):
        return True
    return SubjectClassSetup.objects.filter(
        school=school, teacher=user, class_group=class_grp, academic_year=year
    ).exists()


def _wants_download(request) -> bool:
    """`download=1` يجعل المتصفّح ينزّل الملفّ بدل أن يحلّ محلّ الصفحة."""
    return request.GET.get("download") == "1"


#: التقارير التي تُعرض في الصفحة العارضة — قائمةٌ بيضاء لا يُبنى منها مسارٌ حرّ.
VIEWABLE_REPORTS = {
    "class_results_pdf": "كشف نتائج الفصل",
    "class_certificates_pdf": "شهادات الفصل",
    "attendance_report_pdf": "تقرير الحضور والغياب",
    "student_result_pdf": "نتيجة الطالب",
    "student_annual_result_pdf": "كشف نتائج الطالب",
    "student_certificate_pdf": "شهادة الطالب",
}


def _set_final_status(ctx: dict) -> None:
    """يضيف final_status و status_color إلى السياق"""
    if ctx["failed"] == 0 and ctx["passed"] > 0:
        ctx.update(final_status="ناجح", status_color="#15803d")
    elif ctx["failed"] > 0:
        ctx.update(final_status="راسب", status_color="#dc2626")
    else:
        ctx.update(final_status="غير مكتمل", status_color="#d97706")


def _get_paper_size(request) -> str:
    """Return a validated report paper size."""
    paper = request.GET.get("paper", "A4").upper()
    return paper if paper in {"A3", "A4"} else "A4"


# ── فهرس التقارير ───────────────────────────────────────────────────


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
def reports_index(request):
    """فهرس التقارير — تبويبات + فلاتر + بطاقات فصول."""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    tab = request.GET.get("tab", "results")
    grade_filter = request.GET.get("grade", "")
    level_filter = request.GET.get("level", "")
    paper = _get_paper_size(request)

    if request.user.is_admin():
        classes = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).in_school_order()
    else:
        ids = SubjectClassSetup.objects.filter(
            school=school, teacher=request.user, academic_year=year
        ).values_list("class_group_id", flat=True)
        classes = ClassGroup.objects.filter(id__in=ids).in_school_order()

    # فلترة
    if level_filter:
        classes = classes.filter(level_type=level_filter)
    if grade_filter:
        classes = classes.filter(grade=grade_filter)

    # الصفوف المتاحة فعلياً (للفلاتر)
    all_classes = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
    if level_filter:
        grades = all_classes.filter(level_type=level_filter).values_list("grade", flat=True)
    else:
        grades = all_classes.values_list("grade", flat=True)
    # الفرزُ في بايثون: «G10» قبل «G7» أبجديّاً، والترتيبُ بتعبيرٍ محسوبٍ
    # يتعارض مع `DISTINCT` في المحرّك.
    available_grades = sorted(set(grades), key=grade_number)

    ctx = {
        "classes": classes,
        "year": year,
        "school": school,
        "tab": tab,
        "grade_filter": grade_filter,
        "level_filter": level_filter,
        "paper": paper,
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
@xframe_options_sameorigin
def class_results_pdf(request, class_id):
    """PDF: كشف نتائج كامل لجميع طلاب فصل"""
    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year") or academic_year_for(request)
    # [SEC-04] المعلّم لا يصدّر إلا فصوله — المدرسة وحدها لا تكفي كنطاق
    if not _teacher_can_access_class(request, school, class_grp, year):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("لا تملك صلاحية الوصول إلى تقارير هذا الفصل")
    preview = request.GET.get("preview") == "1"
    paper = _get_paper_size(request)

    ctx = ReportDataService.get_class_results(class_grp, school, year)
    ctx["paper_size"] = paper

    # ── Guard: لا توليد PDF عند عدم وجود طلاب (reportlab يفشل مع جدول فارغ) ──
    if not ctx.get("student_rows"):
        # وثيقة الطباعة صفحةٌ بلا قائمة ولا رجوع، فعرضُها كرسالة خطأ طريقٌ مسدود.
        messages.warning(request, "لا يوجد طلاب في هذا الفصل لتوليد التقرير.")
        return redirect("reports_index")

    if preview:
        return render(request, "reports/class_results.html", ctx)

    html = render_to_string("reports/class_results.html", ctx, request=request)
    return render_pdf(
        html,
        f"نتائج_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
        paper_size=paper,
        as_attachment=_wants_download(request),
    )


@login_required
@leadership_required
@xframe_options_sameorigin
def class_certificates_pdf(request, class_id):
    """PDF: شهادات جميع طلاب فصل في ملف واحد"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year") or academic_year_for(request)
    preview = request.GET.get("preview") == "1"
    paper = _get_paper_size(request)

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
        "paper_size": paper,
    }
    if preview:
        return render(request, "reports/class_certificates.html", page_ctx)

    html = render_to_string("reports/class_certificates.html", page_ctx, request=request)
    return render_pdf(
        html,
        f"شهادات_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
        paper_size=paper,
        as_attachment=_wants_download(request),
    )


@login_required
@leadership_required
@xframe_options_sameorigin
def attendance_report_pdf(request, class_id):
    """PDF: تقرير حضور وغياب الفصل"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = request.GET.get("year") or academic_year_for(request)
    preview = request.GET.get("preview") == "1"
    paper = _get_paper_size(request)

    ctx = ReportDataService.get_attendance_report(class_grp, school, year)
    ctx["paper_size"] = paper
    if preview:
        return render(request, "reports/attendance_report.html", ctx)

    html = render_to_string("reports/attendance_report.html", ctx, request=request)
    return render_pdf(
        html,
        f"غياب_{class_grp.get_grade_display()}_{class_grp.section}_{year}.pdf",
        paper_size=paper,
        as_attachment=_wants_download(request),
    )


# ══════════════════════════════════════════════════════════════════════
# PDF — تقارير الطالب الفردي
# ══════════════════════════════════════════════════════════════════════


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
@xframe_options_sameorigin
def student_result_pdf(request, student_id):
    """PDF: تقرير نتيجة طالب مفصّل"""
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = request.GET.get("year") or academic_year_for(request)
    preview = request.GET.get("preview") == "1"
    paper = _get_paper_size(request)

    if not (request.user.is_admin() or request.user.is_teacher() or request.user == student):
        if not _has_parent_access(request, student, school):
            return HttpResponse("غير مسموح", status=403)

    ctx = ReportDataService.get_student_report(student, school, year)
    ctx["paper_size"] = paper
    if preview:
        return render(request, "reports/student_result.html", ctx)

    html = render_to_string("reports/student_result.html", ctx, request=request)
    return render_pdf(
        html,
        f"نتيجة_{student.full_name}_{year}.pdf",
        paper_size=paper,
        as_attachment=_wants_download(request),
    )


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher")
@xframe_options_sameorigin
def student_annual_result_pdf(request, student_id):
    """كشف نتائج الطالب السنوي — PDF للطباعة الرسمية"""
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = request.GET.get("year") or academic_year_for(request)
    preview = request.GET.get("preview") == "1"
    paper = _get_paper_size(request)

    if not (request.user.is_admin() or request.user.is_teacher() or request.user == student):
        if not _has_parent_access(request, student, school):
            return HttpResponse("غير مسموح", status=403)

    ctx = ReportDataService.get_student_report(student, school, year)
    _set_final_status(ctx)
    ctx["paper_size"] = paper

    if preview:
        return render(request, "reports/student_result_pdf.html", ctx)

    html = render_to_string("reports/student_result_pdf.html", ctx, request=request)
    return render_pdf(
        html,
        f"كشف_نتائج_{student.full_name}_{year}.pdf",
        paper_size=paper,
        as_attachment=_wants_download(request),
    )


@login_required
@leadership_required
@xframe_options_sameorigin
def student_certificate_pdf(request, student_id):
    """PDF: شهادة نتيجة سنوية رسمية"""
    school = request.user.get_school()
    student = get_object_or_404(
        CustomUser,
        id=student_id,
        memberships__school=school,
        memberships__is_active=True,
    )
    year = request.GET.get("year") or academic_year_for(request)
    preview = request.GET.get("preview") == "1"
    paper = _get_paper_size(request)

    if not (request.user.is_admin() or request.user.is_teacher()):
        if not _has_parent_access(request, student, school):
            return HttpResponse("غير مسموح", status=403)

    ctx = ReportDataService.get_student_report(student, school, year)
    _set_final_status(ctx)
    ctx["paper_size"] = paper

    if preview:
        return render(request, "reports/certificate.html", ctx)

    html = render_to_string("reports/certificate.html", ctx, request=request)
    return render_pdf(
        html,
        f"شهادة_{student.full_name}_{year}.pdf",
        paper_size=paper,
        as_attachment=_wants_download(request),
    )


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
    year = request.GET.get("year") or academic_year_for(request)
    # [SEC-04] المعلّم لا يصدّر إلا فصوله — المدرسة وحدها لا تكفي كنطاق
    if not _teacher_can_access_class(request, school, class_grp, year):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("لا تملك صلاحية الوصول إلى تقارير هذا الفصل")
    paper = _get_paper_size(request).lower()
    return ExcelService.class_results_excel(class_grp, school, year, paper=paper)


@login_required
@leadership_required
def attendance_excel(request, class_id):
    """Excel: تقرير الغياب"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    paper = _get_paper_size(request).lower()
    return ExcelService.attendance_excel(
        class_grp,
        school,
        request.GET.get("year") or academic_year_for(request),
        paper=paper,
    )


@login_required
@leadership_required
def behavior_excel(request):
    """Excel: تقرير المخالفات السلوكية"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    paper = _get_paper_size(request).lower()
    return ExcelService.behavior_excel(
        school,
        request.GET.get("year") or academic_year_for(request),
        paper=paper,
    )
