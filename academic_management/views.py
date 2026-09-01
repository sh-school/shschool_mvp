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

from academic_management import workload_service
from core.academic_calendar import academic_year_for
from core.pdf_utils import render_pdf
from core.permissions import SCHEDULE_MANAGE, role_required
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
@role_required(SCHEDULE_MANAGE | {"coordinator"})
def workload(request):
    """أساسُ إسناد الأنصبة — قراءةً محضة، وثلاثةُ مناظير.

    تجيب الشاشةُ عن: مَن يُدرّس ماذا، ولأيّ شعبة، وكم حصّة. أمّا سؤالُ
    «ما الفرقُ بين المرصود والمعتمد؟» فمعروضٌ بلا جواب — لأنّ المعتمَدَ ليس
    في القاعدة، ولا يُشتقّ من الجدول:

        HistoricalAssignment → Proposal        (وليس → Truth)
    """
    school = _get_school(request)
    year = request.GET.get("year") or academic_year_for(request)
    perspective = request.GET.get("view", "teachers")
    if perspective not in ("teachers", "subjects", "sections"):
        perspective = "teachers"

    context = {
        "page_title": "إسناد الأنصبة",
        "module_name": MODULE_NAME,
        "year": year,
        "perspective": perspective,
        "plan": workload_service.plan_context(school, year),
        "unknown": workload_service.UNKNOWN,
    }
    if school is None:
        return render(request, "academic_management/workload.html", context)

    lessons, rows = workload_service.load(school, year)
    plans = workload_service.plans_by_teacher(school, year)
    context["totals"] = workload_service.totals(lessons, rows)
    context["gate"] = workload_service.gate(lessons, rows, plans)
    if perspective == "teachers":
        context["teachers"] = workload_service.teacher_view(lessons, rows, plans)
    elif perspective == "subjects":
        context["subjects"] = workload_service.subject_view(lessons, rows)
    else:
        context["sections"] = workload_service.section_view(lessons, rows)
    return render(request, "academic_management/workload.html", context)


@login_required
def assignments(request):
    return _stub_view(request, "التكاليف", "📝")


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


@login_required
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

    if export == "pdf":
        ctx = {"data": data, "school": school, "pdf_mode": True}
        html = render_to_string(template, ctx, request=request)
        return render_pdf(html, pdf_name)

    if export == "excel":
        return excel_fn(data, school)

    return None


@login_required
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
            "module_name": MODULE_NAME,
        },
    )


@login_required
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
            "module_name": MODULE_NAME,
        },
    )


@login_required
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
            "module_name": MODULE_NAME,
        },
    )


@login_required
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
            "module_name": MODULE_NAME,
            "flagship": True,
        },
    )
