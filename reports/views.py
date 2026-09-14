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
from core.audit_export import log_export
from core.capabilities import capability_required
from core.models import ClassGroup, CustomUser, StudentEnrollment
from core.models.academic import grade_number
from core.pdf_utils import render_pdf

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
    """يضيف `final_status` و`status_tone` إلى السياق.

    كان يضع لوناً سداسيّاً (`status_color`) يُكتب في `style=` الشهادة — وأحدُها
    أخضرُ لا رمزَ له في الهويّة. والنغمةُ اسمٌ تقرؤه الشهادةُ صنفاً
    (`cert-status is-success`) يأخذ ألوانَه من `brand_color`.
    """
    if ctx["failed"] == 0 and ctx["passed"] > 0:
        ctx.update(final_status="ناجح", status_tone="success")
    elif ctx["failed"] > 0:
        ctx.update(final_status="راسب", status_tone="danger")
    else:
        ctx.update(final_status="غير مكتمل", status_tone="warning")


# ── عرضُ الوثائق المطبوعة: الألوانُ تُحسم هنا لا في القالب ─────────────
# النغماتُ أسماءُ أصناف `c-*` في `reports/base_qatar_report.html`.

#: حالةُ الطالب النصّيّة في كشف الفصل ← نغمتُها.
_RESULT_TEXT_TONE = {"ناجح": "green", "راسب": "red"}

#: حالةُ النتيجة السنويّة ← (الاسم، النغمة).
_ANNUAL_STATUS = {
    "pass": ("ناجح", "green"),
    "fail": ("راسب", "red"),
    "second_round": ("دور ثانٍ", "orange"),
}


def _grade_tone(total) -> str:
    """لونُ المجموع السنويّ — عتباتُ القالب القديم: 90 ممتاز، 75 جيّد، 50 نجاح."""
    if not total:
        return "muted"
    if total >= 90:
        return "green"
    if total >= 75:
        return "blue"
    if total >= 50:
        return "orange"
    return "red"


def _class_results_presentation(ctx: dict) -> None:
    """أرقامُ كشف الفصل ونغماتُ خاناته."""
    total, passed = ctx["total_students"], ctx["total_passed"]
    ctx["report_kpis"] = [
        {"label": "إجمالي الطلاب", "value": total, "tone": "maroon"},
        {"label": "ناجحون", "value": passed, "tone": "green"},
        {"label": "راسبون", "value": ctx["total_failed"], "tone": "red"},
        {
            "label": "نسبة النجاح",
            "value": f"{round(passed / total * 100)}%" if total else "—",
            "tone": "maroon",
        },
    ]
    for row in ctx["student_rows"]:
        row["status_tone"] = _RESULT_TEXT_TONE.get(row["status"], "orange")
        row["grade_cells"] = [
            {
                "value": ann.annual_total if ann and ann.annual_total else None,
                "tone": _grade_tone(ann.annual_total if ann else None),
            }
            for ann in row["grades_list"]
        ]


def _student_result_presentation(ctx: dict) -> None:
    """أرقامُ نتيجة الطالب ونغماتُ سطور موادّه."""
    ctx["report_kpis"] = [
        {"label": "المواد", "value": ctx["total"], "tone": "maroon"},
        {"label": "ناجح", "value": ctx["passed"], "tone": "green"},
        {"label": "راسب", "value": ctx["failed"], "tone": "red"},
        {"label": "المتوسط / 100", "value": ctx["avg"] or "—", "tone": "maroon"},
        {"label": "غياب", "value": ctx["absent_total"], "tone": "orange"},
        {"label": "تأخر", "value": ctx["late_total"], "tone": "maroon"},
    ]
    _subject_rows_presentation(ctx["rows"])


def _subject_rows_presentation(rows: list[dict]) -> None:
    """نغمةُ مجموع كلّ مادّةٍ واسمُ حالتها — في نتيجة الطالب وشهادته."""
    for row in rows:
        annual = row["annual"]
        row["total_tone"] = _grade_tone(annual.annual_total if annual else None)
        row["status_label"], row["status_tone"] = _ANNUAL_STATUS.get(
            annual.status if annual else "", ("غير مكتمل", "orange")
        )


def _annual_grade(total) -> str:
    """صنفُ مجموع المادّة في كشف النتائج السنويّ (`grade-*` في قالبه).

    عتباتُ القالب القديم كما كانت: 90 ممتاز، 75 جيّد، 60 مقبول، وما دونها
    يُبرَز — وبلا مجموعٍ رماديّ. وليست عتباتِ `_grade_tone` (50 للنجاح):
    كشفٌ رسميٌّ لا يتغيّر لونُه في ترحيل.
    """
    if not total:
        return "na"
    if total >= 90:
        return "a"
    if total >= 75:
        return "b"
    if total >= 60:
        return "c"
    return "f"


def _annual_result_presentation(ctx: dict) -> None:
    """نغمةُ مجموع كلّ مادّةٍ في كشف النتائج السنويّ."""
    for row in ctx["rows"]:
        annual = row["annual"]
        row["annual_grade"] = _annual_grade(annual.annual_total if annual else None)


def _attendance_presentation(ctx: dict) -> None:
    """رقمُ تقرير الحضور ونغمةُ كلّ طالب — عتباتُ القالب القديم: 95 ممتاز، 80 مقبول،
    وأكثرُ من عشرة غياباتٍ تُبرَز."""
    ctx["report_kpis"] = [
        {"label": "إجمالي الطلاب", "value": len(ctx["student_rows"]), "tone": "maroon"}
    ]
    for row in ctx["student_rows"]:
        pct = row["attendance_pct"]
        if pct >= 95:
            row["attendance_label"], row["attendance_tone"] = "ممتاز", "green"
        elif pct >= 80:
            row["attendance_label"], row["attendance_tone"] = "مقبول", "orange"
        else:
            row["attendance_label"], row["attendance_tone"] = "منخفض", "red"
        row["absent_tone"] = "red" if row["absent"] > 10 else ""


def _get_paper_size(request) -> str:
    """Return a validated report paper size."""
    paper = request.GET.get("paper", "A4").upper()
    return paper if paper in {"A3", "A4"} else "A4"


# ── فهرس التقارير ───────────────────────────────────────────────────


@login_required
@capability_required("reports.results")
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
        "page_subtitle": f"تصدير تقارير PDF جاهزة للطباعة — العام {year}",
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
@capability_required("reports.results")
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
    _class_results_presentation(ctx)
    log_export(
        request,
        "reports.class_results",
        rows=len(ctx["student_rows"]),
        object_id=class_grp.pk,
        object_repr=f"كشف نتائج {class_grp} — {year}",
    )

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
@capability_required("reports.school")
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
    # شهاداتُ فصلٍ في ملفٍّ واحدٍ كشفٌ جماعيّ — الرقمُ فيها مستور.
    log_export(
        request,
        "reports.class_certificates",
        rows=len(students_ctx),
        object_id=class_grp.pk,
        object_repr=f"شهادات {class_grp} — {year}",
    )
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
@capability_required("reports.school")
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
    _attendance_presentation(ctx)
    log_export(
        request,
        "reports.attendance",
        rows=len(ctx["student_rows"]),
        object_id=class_grp.pk,
        object_repr=f"تقرير حضور {class_grp} — {year}",
    )
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
@capability_required("reports.results")
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
    _student_result_presentation(ctx)
    # وثيقةٌ فرديّةٌ تُسلَّم لصاحبها: الرقمُ كاملاً — والتدقيقُ ثمنُه.
    log_export(
        request,
        "reports.student_result",
        rows=1,
        full_national_id=True,
        object_id=student.pk,
        object_repr=f"نتيجة {student.full_name} — {year}",
    )
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
@capability_required("reports.results")
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
    _annual_result_presentation(ctx)
    ctx["paper_size"] = paper
    log_export(
        request,
        "reports.student_annual_result",
        rows=1,
        full_national_id=True,
        object_id=student.pk,
        object_repr=f"كشف نتائج {student.full_name} — {year}",
    )

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
@capability_required("reports.school")
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
    _subject_rows_presentation(ctx["rows"])
    ctx["paper_size"] = paper
    log_export(
        request,
        "reports.certificate",
        rows=1,
        full_national_id=True,
        object_id=student.pk,
        object_repr=f"شهادة {student.full_name} — {year}",
    )

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
@capability_required("reports.results")
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
    # الرقم الشخصيّ: مستور — `ExcelService.class_results_excel` يستره، والسجلُّ يقولها.
    log_export(
        request,
        "reports.class_results_xlsx",
        rows=StudentEnrollment.objects.filter(class_group=class_grp, is_active=True).count(),
        full_national_id=False,
        object_id=class_grp.pk,
        object_repr=f"Excel نتائج {class_grp} — {year}",
    )
    return ExcelService.class_results_excel(class_grp, school, year, paper=paper)


@login_required
@capability_required("reports.school")
def attendance_excel(request, class_id):
    """Excel: تقرير الغياب"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    class_grp = get_object_or_404(ClassGroup, id=class_id, school=school)
    paper = _get_paper_size(request).lower()
    year = request.GET.get("year") or academic_year_for(request)
    # الرقم الشخصيّ: مستور — `ExcelService.attendance_excel` يستره.
    log_export(
        request,
        "reports.attendance_xlsx",
        rows=StudentEnrollment.objects.filter(class_group=class_grp, is_active=True).count(),
        full_national_id=False,
        object_id=class_grp.pk,
        object_repr=f"Excel حضور {class_grp} — {year}",
    )
    return ExcelService.attendance_excel(class_grp, school, year, paper=paper)


@login_required
@capability_required("reports.school")
def behavior_excel(request):
    """Excel: تقرير المخالفات السلوكية"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    paper = _get_paper_size(request).lower()
    year = request.GET.get("year") or academic_year_for(request)
    # الرقم الشخصيّ: مستور — `ExcelService.behavior_excel` يستره.
    log_export(
        request,
        "reports.behavior_xlsx",
        full_national_id=False,
        object_repr=f"Excel سلوك — {year}",
    )
    return ExcelService.behavior_excel(school, year, paper=paper)
