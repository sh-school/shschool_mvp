"""
academic_management/views.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQ-SH-002 — 9 stub pages for the submenu restructure (classroom_visits → quality:observation_list)
REQ-SH-003 — 4 academic reports + landing page (Client #001, MTG-007)
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from core.capabilities import capability_required
from core.pdf_utils import render_pdf
from reports.services import AcademicReportsExcel, AcademicReportsService

MODULE_NAME = "إدارة الشؤون الأكاديمية"


def _stub_view(request, page_title_ar: str, icon: str = "📚"):
    """Generic stub renderer for academic management pages under construction."""
    return render(
        request,
        "academic_management/stub.html",
        {
            "page_title": page_title_ar,
            "icon": icon,
            "module_name": MODULE_NAME,
        },
    )


# ══════════════════════════════════════════════════════════════════════
# REQ-SH-002 — stub submenu pages
# ══════════════════════════════════════════════════════════════════════


@login_required
def evaluations(request):
    return _stub_view(request, "التقييمات والدرجات", "📊")


@login_required
def departments(request):
    return _stub_view(request, "إدارة الأقسام التعليمية", "🏛️")


@login_required
def test_analytics(request):
    return _stub_view(request, "تحليلات الاختبارات", "📈")


@login_required
def department_reports(request):
    return _stub_view(request, "التقارير الخاصة بالقسم", "📄")


@login_required
def elearning(request):
    return _stub_view(request, "التعليم الإلكتروني", "💻")


@login_required
def class_performance(request):
    return _stub_view(request, "تقارير الأداء الصفي", "📉")


@login_required
def underperformance(request):
    return _stub_view(request, "إدارة الأداء دون المستوى", "⚠️")


# ══════════════════════════════════════════════════════════════════════
# REQ-SH-003 — Academic Reports (4 report types)
# ══════════════════════════════════════════════════════════════════════


def _get_school(request):
    """Resolve the active school for the authenticated user."""
    if hasattr(request.user, "get_school"):
        return request.user.get_school()
    return None


def _parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ── عرضُ التقارير: ما كان يُركَّب ويُلوَّن في القالب ─────────────────────

#: أسماءُ الأشهر لقائمة الشهر — كانت اثنتي عشرة سطراً مكتوبةً باليد.
MONTH_CHOICES = [
    (1, "يناير"),
    (2, "فبراير"),
    (3, "مارس"),
    (4, "أبريل"),
    (5, "مايو"),
    (6, "يونيو"),
    (7, "يوليو"),
    (8, "أغسطس"),
    (9, "سبتمبر"),
    (10, "أكتوبر"),
    (11, "نوفمبر"),
    (12, "ديسمبر"),
]


def _num(value) -> str:
    """رقمٌ بلا أصفارٍ زائدة، و«—» حين لا قيمة — والصفرُ صفرٌ لا شَرطة."""
    return "—" if value is None else f"{value:g}"


def _range_label(low, high) -> str:
    """الأدنى والأعلى في خانةٍ واحدة: «40–95»."""
    if low is None or high is None:
        return "—"
    return f"{low:g}–{high:g}"


def _combined_tone(score) -> str:
    """لونُ التقييم المدمج — العتباتُ التي كانت في القالب: 75 فأكثر، ثمّ 50."""
    if score is None:
        return "is-muted"
    if score >= 75:
        return "is-success"
    if score >= 50:
        return "is-warning"
    return "is-danger"


def _present_quiz(data: dict) -> None:
    data["range_label"] = _range_label(data.get("min_pct"), data.get("max_pct"))
    for r in data["rows"]:
        r["grade_label"] = f"{_num(r['raw_grade'])} / {_num(r['max_grade'])}"


def _present_exam_results(data: dict) -> None:
    for r in data["rows"]:
        r["range_label"] = _range_label(r["min_score"], r["max_score"])


def _present_progress(data: dict) -> None:
    for s in data["students"]:
        s["range_label"] = _range_label(s["min_pct"], s["max_pct"])


def _present_monthly(data: dict) -> None:
    data["month_choices"] = MONTH_CHOICES
    for r in data["rows"]:
        r["combined_tone"] = _combined_tone(r["combined_score"])


@login_required
@capability_required("academic.reports_school")
def reports_landing(request):
    """
    REQ-SH-003 — Academic reports landing page.
    Shows 4 report-type cards, with the monthly flagship highlighted.
    """
    return render(
        request,
        "academic_management/reports/landing.html",
        {
            "page_title": "التقارير الأكاديمية",
            "page_subtitle": "أربعة تقارير لقرارات الإدارة الأكاديمية — تُصدَّر PDF وExcel",
            "module_name": MODULE_NAME,
        },
    )


def _export_response(request, template: str, data: dict, excel_fn, pdf_name: str):
    """
    Shared export helper: handles ?export=pdf and ?export=excel for any report.
    Renders the same template for HTML and for PDF (WeasyPrint).
    """
    export = request.GET.get("export")
    school = _get_school(request)

    if export in ("pdf", "excel"):
        from core.audit_export import log_export

        rows = data.get("rows") if isinstance(data.get("rows"), list) else None
        log_export(request, f"academic.{template.rsplit('/', 1)[-1]}:{export}", rows=rows)

    if export == "pdf":
        ctx = {"data": data, "school": school, "pdf_mode": True}
        html = render_to_string(template, ctx, request=request)
        return render_pdf(html, pdf_name)

    if export == "excel":
        return excel_fn(data, school)

    return None


@login_required
@capability_required("academic.reports_school")
def quiz_reports(request):
    """Report 1 — تقارير الاختبارات القصيرة."""
    school = _get_school(request)
    if school is None:
        return HttpResponse("لا توجد مدرسة مرتبطة", status=403)

    data = AcademicReportsService.get_quiz_reports(
        school,
        subject_id=request.GET.get("subject_id") or None,
        class_group_id=request.GET.get("class_group_id") or None,
        student_id=request.GET.get("student_id") or None,
        date_from=request.GET.get("date_from") or None,
        date_to=request.GET.get("date_to") or None,
    )
    _present_quiz(data)

    export_resp = _export_response(
        request,
        "academic_management/reports/quiz_reports.html",
        data,
        AcademicReportsExcel.quiz_reports_excel,
        "quiz_reports.pdf",
    )
    if export_resp is not None:
        return export_resp

    return render(
        request,
        "academic_management/reports/quiz_reports.html",
        {
            "data": data,
            "school": school,
            "page_title": "تقارير الاختبارات القصيرة",
            "page_subtitle": "نتائج الاختبارات القصيرة حسب المواد على مستوى الطالب أو الشعبة",
            "module_name": MODULE_NAME,
        },
    )


@login_required
@capability_required("academic.reports_school")
def exam_results_reports(request):
    """Report 2 — تقارير نتائج الاختبارات (package comparison)."""
    school = _get_school(request)
    if school is None:
        return HttpResponse("لا توجد مدرسة مرتبطة", status=403)

    data = AcademicReportsService.get_exam_results_reports(
        school,
        package_type=request.GET.get("package_type") or None,
        semester=request.GET.get("semester") or None,
        class_group_id=request.GET.get("class_group_id") or None,
    )
    _present_exam_results(data)

    export_resp = _export_response(
        request,
        "academic_management/reports/exam_results.html",
        data,
        AcademicReportsExcel.exam_results_excel,
        "exam_results.pdf",
    )
    if export_resp is not None:
        return export_resp

    return render(
        request,
        "academic_management/reports/exam_results.html",
        {
            "data": data,
            "school": school,
            "page_title": "تقارير نتائج الاختبارات",
            "page_subtitle": "نتائج اختبارات الباقات (P1-P4, AW) — مقارنة بين الفصول والطلاب",
            "module_name": MODULE_NAME,
        },
    )


@login_required
@capability_required("academic.reports_school")
def academic_progress_reports(request):
    """Report 3 — تقارير التقدم الأكاديمي."""
    school = _get_school(request)
    if school is None:
        return HttpResponse("لا توجد مدرسة مرتبطة", status=403)

    data = AcademicReportsService.get_academic_progress_reports(
        school,
        class_group_id=request.GET.get("class_group_id") or None,
        date_from=request.GET.get("date_from") or None,
        date_to=request.GET.get("date_to") or None,
    )
    _present_progress(data)

    export_resp = _export_response(
        request,
        "academic_management/reports/academic_progress.html",
        data,
        AcademicReportsExcel.academic_progress_excel,
        "academic_progress.pdf",
    )
    if export_resp is not None:
        return export_resp

    return render(
        request,
        "academic_management/reports/academic_progress.html",
        {
            "data": data,
            "school": school,
            "page_title": "تقارير التقدم الأكاديمي",
            "page_subtitle": "نتائج التقييمات في شعبةٍ خلال فترة — مرتّبةً بمتوسط الطالب",
            "module_name": MODULE_NAME,
        },
    )


@login_required
@capability_required("academic.reports_school")
def monthly_ba_report(request):
    """
    Report 4 — FLAGSHIP التقرير السلوكي والتعليمي الشهري.
    Combines quiz averages + behavior infractions for a given month.
    """
    school = _get_school(request)
    if school is None:
        return HttpResponse("لا توجد مدرسة مرتبطة", status=403)

    now = timezone.now()
    month = _parse_int(request.GET.get("month"), now.month)
    year = _parse_int(request.GET.get("year"), now.year)
    if not (1 <= month <= 12):
        month = now.month
    if not (2000 <= year <= 2100):
        year = now.year

    data = AcademicReportsService.get_monthly_behavior_academic_report(
        school,
        month=month,
        year=year,
        scope=request.GET.get("scope", "section"),
        class_group_id=request.GET.get("class_group_id") or None,
        student_id=request.GET.get("student_id") or None,
    )
    _present_monthly(data)

    export_resp = _export_response(
        request,
        "academic_management/reports/monthly_ba.html",
        data,
        AcademicReportsExcel.monthly_behavior_academic_excel,
        f"monthly_ba_{data['period']}.pdf",
    )
    if export_resp is not None:
        return export_resp

    return render(
        request,
        "academic_management/reports/monthly_ba.html",
        {
            "data": data,
            "school": school,
            "page_title": "التقرير السلوكي والتعليمي الشهري",
            "page_subtitle": "متوسط الاختبارات القصيرة مع عدد المخالفات خلال شهر — للطالب أو الشعبة",
            "module_name": MODULE_NAME,
            "flagship": True,
        },
    )
