# analytics/views.py — thin views (Phase 4)
"""
لوحة الإحصاءات المتقدمة — SchoolOS V2
تشمل 7 APIs للرسوم البيانية بـ Chart.js + 10 KPIs
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from assessments.models import StudentSubjectResult
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit, HealthRecord
from core import brand
from core.academic_calendar import academic_year_for
from core.capabilities import capability_required
from core.domain.attendance import attendance_rate
from core.domain.grades import GRADE_BANDS, band_of
from core.models import Membership, StudentEnrollment
from core.models.academic import grade_order
from core.pdf_utils import render_pdf
from library.models import BookBorrowing, LibraryBook
from operations.models import Session, StudentAttendance
from quality.models import OperationalDomain, OperationalProcedure
from transport.models import SchoolBus

from .services import KPIService


# ── لوحة القيادة الرئيسية ────────────────────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def analytics_dashboard(request):
    """لوحة الإحصاءات المتقدمة للمدير"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    today = timezone.now().date()

    # ── KPIs الأساسية ─────────────────────────────────────────
    total_students = StudentEnrollment.objects.filter(
        class_group__school=school, class_group__academic_year=year, is_active=True
    ).count()

    total_teachers = Membership.objects.filter(
        school=school, is_active=True, role__name__in=["teacher", "coordinator"]
    ).count()

    # الحضور
    sessions_today = Session.objects.filter(school=school, date=today)
    att_today = StudentAttendance.objects.filter(session__in=sessions_today)
    present_today = att_today.filter(status="present").count()
    total_att = att_today.count()
    att_pct_today = attendance_rate(present_today, total_att)

    # العيادة
    clinic_visits_today = ClinicVisit.objects.filter(school=school, visit_date__date=today).count()
    chronic_cases = (
        HealthRecord.objects.filter(student__memberships__school=school)
        .exclude(chronic_diseases="")
        .distinct()
        .count()
    )

    # السلوك
    behavior_infractions_month = BehaviorInfraction.objects.filter(
        school=school, date__month=today.month, date__year=today.year
    ).count()
    critical_infractions = BehaviorInfraction.objects.filter(
        school=school, level__in=[3, 4], is_resolved=False
    ).count()

    # النقل
    total_buses = SchoolBus.objects.filter(school=school).count()
    students_on_bus = (
        StudentEnrollment.objects.filter(student__bus_routes__bus__school=school, is_active=True)
        .distinct()
        .count()
    )

    # المكتبة
    total_books = LibraryBook.objects.filter(school=school).count()
    active_loans = BookBorrowing.objects.filter(book__school=school, status="BORROWED").count()
    overdue_books = BookBorrowing.objects.filter(book__school=school, status="OVERDUE").count()

    # الخطة التشغيلية
    total_procs = OperationalProcedure.objects.filter(school=school, academic_year=year).count()
    completed_procs = OperationalProcedure.objects.filter(
        school=school, academic_year=year, status="Completed"
    ).count()
    plan_pct = round(completed_procs / total_procs * 100) if total_procs else 0

    kpis = {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "att_pct_today": att_pct_today,
        "present_today": present_today,
        "clinic_today": clinic_visits_today,
        "chronic_cases": chronic_cases,
        "behavior_month": behavior_infractions_month,
        "critical_issues": critical_infractions,
        "total_buses": total_buses,
        "bus_students": students_on_bus,
        "library_books": total_books,
        "active_loans": active_loans,
        "overdue_books": overdue_books,
        "plan_pct": plan_pct,
        "completed_procs": completed_procs,
        "total_procs": total_procs,
    }

    return render(
        request,
        "analytics/dashboard.html",
        {
            "kpis": kpis,
            "year": year,
            "school": school,
            "today": today,
            **_dashboard_presentation(kpis, school),
        },
    )


def _dashboard_presentation(kpis: dict, school) -> dict:
    """نصوصُ بطاقات لوحة المدير وألوانُها — ما كان يُركَّب ويُشرَط في القالب.

    كانت بطاقاتُ الخدمات تُلحق بالرقم سطرَ تنبيهٍ («3 مزمنة»، «2 جسيمة»،
    «5 متأخرة») ثمّ يكرّره شريطُ تنبيهٍ تحتها. فصار اللونُ التنبيه: أحمرُ حين
    يوجد ما يُنبَّه إليه (العتبةُ التي كانت في القالب: أكبرُ من صفر)، والتفصيلُ
    سطرٌ واحد.
    """
    chronic, critical, overdue = (
        kpis["chronic_cases"],
        kpis["critical_issues"],
        kpis["overdue_books"],
    )
    return {
        "subtitle": f"نظرة شاملة على أداء {getattr(school, 'name', '') or 'المدرسة'}",
        "att_label": f"{kpis['att_pct_today']}%",
        "present_label": f"{kpis['present_today']} حاضر",
        "plan_label": f"{kpis['plan_pct']}%",
        "procs_label": f"{kpis['completed_procs']}/{kpis['total_procs']}",
        "clinic_sub": f"{chronic} حالة مزمنة",
        "clinic_tone": "red" if chronic > 0 else "teal",
        "behavior_sub": f"{critical} جسيمة" if critical > 0 else "لا جسيمة",
        "behavior_tone": "red" if critical > 0 else "orange",
        "buses_sub": f"{kpis['total_buses']} حافلة",
        "library_sub": f"{overdue} متأخرة" if overdue > 0 else "إعارة نشطة",
        "library_tone": "red" if overdue > 0 else "purple",
    }


# ── API 1: منحنى الحضور (آخر 30 يوم) ────────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_attendance_trend(request):
    school = request.user.get_school()
    days = int(request.GET.get("days", 30))
    since = timezone.now().date() - timedelta(days=days)

    qs = (
        StudentAttendance.objects.filter(session__school=school, session__date__gte=since)
        .values("session__date")
        .annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
        )
        .order_by("session__date")
    )

    labels = []
    present_data = []
    absent_data = []

    for row in qs:
        d = row["session__date"]
        labels.append(d.strftime("%d/%m"))
        pct = attendance_rate(row["present"], row["total"])
        present_data.append(pct)
        absent_data.append(100 - pct)

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "نسبة الحضور %",
                    "data": present_data,
                    "borderColor": brand.STATUS_SUCCESS,
                    "backgroundColor": brand.rgba(brand.STATUS_SUCCESS, 0.1),
                    "fill": True,
                    "tension": 0.3,
                },
                {
                    "label": "نسبة الغياب %",
                    "data": absent_data,
                    "borderColor": brand.STATUS_DANGER,
                    "backgroundColor": brand.rgba(brand.STATUS_DANGER, 0.1),
                    "fill": True,
                    "tension": 0.3,
                },
            ],
        }
    )


# ── API 2: توزيع الدرجات ────────────────────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_grades_distribution(request):
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    grades = StudentSubjectResult.objects.filter(
        setup__school=school, setup__academic_year=year
    ).values_list("total", flat=True)

    buckets = {band.label: 0 for band in GRADE_BANDS}
    for g in grades:
        band = band_of(g)
        if band is not None:
            buckets[band.label] += 1

    colors = [
        brand.STATUS_SUCCESS,
        brand.STATUS_INFO,
        brand.STATUS_WARNING,
        brand.ACCENT_ORANGE,
        brand.ACCENT_PURPLE,
        brand.STATUS_DANGER,
    ]

    return JsonResponse(
        {
            "labels": list(buckets.keys()),
            "datasets": [
                {
                    "label": "عدد الطلاب",
                    "data": list(buckets.values()),
                    "backgroundColor": colors,
                    "borderWidth": 1,
                }
            ],
        }
    )


# ── API 3: مقارنة الفصول الدراسية ───────────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_class_comparison(request):
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    classes = (
        StudentSubjectResult.objects.filter(setup__school=school, setup__academic_year=year)
        .values("setup__class_group__grade", "setup__class_group__section")
        .annotate(avg=Avg("total"))
        .order_by(grade_order("setup__class_group__grade"), "setup__class_group__section")
    )

    labels = [
        r["setup__class_group__grade"] + "-" + (r["setup__class_group__section"] or "")
        for r in classes
    ]
    data = [round(float(r["avg"]), 1) if r["avg"] else 0 for r in classes]

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "متوسط الدرجات",
                    "data": data,
                    "backgroundColor": brand.rgba(brand.MAROON, 0.7),
                    "borderColor": brand.MAROON,
                    "borderWidth": 1,
                }
            ],
        }
    )


# ── API 4: مقارنة المواد الدراسية ───────────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_subject_comparison(request):
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    subjects = (
        StudentSubjectResult.objects.filter(setup__school=school, setup__academic_year=year)
        .values("setup__subject__name_ar")
        .annotate(
            avg=Avg("total"),
            fail_count=Count("id", filter=Q(total__lt=50)),
            total=Count("id"),
        )
        .order_by("-avg")
    )

    labels = [r["setup__subject__name_ar"] or "—" for r in subjects]
    avg_data = [round(float(r["avg"]), 1) if r["avg"] else 0 for r in subjects]
    fail_rates = [round(r["fail_count"] / r["total"] * 100) if r["total"] else 0 for r in subjects]

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "متوسط الدرجة",
                    "data": avg_data,
                    "backgroundColor": brand.rgba(brand.STATUS_INFO, 0.7),
                    "borderColor": brand.STATUS_INFO,
                    "borderWidth": 1,
                    "yAxisID": "y",
                },
                {
                    "label": "نسبة الرسوب %",
                    "data": fail_rates,
                    "backgroundColor": brand.rgba(brand.STATUS_DANGER, 0.7),
                    "borderColor": brand.STATUS_DANGER,
                    "borderWidth": 1,
                    "yAxisID": "y1",
                    "type": "line",
                },
            ],
        }
    )


# ── API 5: تقدم الخطة التشغيلية (حسب المجال) ───────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_plan_progress(request):
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    domains = OperationalDomain.objects.filter(school=school, academic_year=year).order_by("order")

    labels = []
    complete = []
    pending = []

    for d in domains:
        total = d.total_procedures
        done = d.completed_procedures
        labels.append(d.name[:20])
        complete.append(done)
        pending.append(total - done)

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "مكتمل",
                    "data": complete,
                    "backgroundColor": brand.STATUS_SUCCESS,
                },
                {
                    "label": "قيد التنفيذ",
                    "data": pending,
                    "backgroundColor": brand.STATUS_WARNING,
                },
            ],
        }
    )


# ── API 6: مخالفات السلوك (آخر 6 أشهر) ─────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_behavior_trend(request):
    school = request.user.get_school()
    today = timezone.now().date()
    since = today.replace(day=1) - timedelta(days=150)

    qs = (
        BehaviorInfraction.objects.filter(school=school, date__gte=since)
        .values("date__month", "date__year", "level")
        .annotate(count=Count("id"))
        .order_by("date__year", "date__month")
    )

    # بناء labels من آخر 6 أشهر
    months = []
    cur = since.replace(day=1)
    while cur <= today:
        months.append((cur.year, cur.month))
        next_month = cur.month + 1 if cur.month < 12 else 1
        next_year = cur.year if cur.month < 12 else cur.year + 1
        cur = cur.replace(year=next_year, month=next_month)

    month_names = [
        "يناير",
        "فبراير",
        "مارس",
        "أبريل",
        "مايو",
        "يونيو",
        "يوليو",
        "أغسطس",
        "سبتمبر",
        "أكتوبر",
        "نوفمبر",
        "ديسمبر",
    ]
    labels = [month_names[m - 1] for _, m in months]

    data_by_level = {1: {}, 2: {}, 3: {}, 4: {}}
    for row in qs:
        key = (row["date__year"], row["date__month"])
        data_by_level[row["level"]][key] = row["count"]

    level_colors = {
        1: (brand.STATUS_SUCCESS, "بسيطة"),
        2: (brand.STATUS_WARNING, "متوسطة"),
        3: (brand.ACCENT_ORANGE, "جسيمة"),
        4: (brand.STATUS_DANGER, "شديدة الخطورة"),
    }

    datasets = []
    for lvl, (color, label) in level_colors.items():
        datasets.append(
            {
                "label": label,
                "data": [data_by_level[lvl].get(m, 0) for m in months],
                "backgroundColor": color,
            }
        )

    return JsonResponse({"labels": labels, "datasets": datasets})


# ── API 7: الطلاب الراسبون (حسب الفصل) ─────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_failing_by_class(request):
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    qs = (
        StudentSubjectResult.objects.filter(
            setup__school=school, setup__academic_year=year, total__lt=50
        )
        .values("setup__class_group__grade", "setup__class_group__section")
        .annotate(fail_count=Count("student", distinct=True))
        .order_by("-fail_count")[:10]
    )

    return JsonResponse(
        {
            "labels": [
                r["setup__class_group__grade"] + "-" + (r["setup__class_group__section"] or "")
                for r in qs
            ],
            "datasets": [
                {
                    "label": "طلاب راسبون",
                    "data": [r["fail_count"] for r in qs],
                    "backgroundColor": brand.STATUS_DANGER,
                }
            ],
        }
    )


# ── API 8: إحصائيات العيادة (آخر 30 يوم) ────────────────────
@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_clinic_stats(request):
    school = request.user.get_school()
    since = timezone.now().date() - timedelta(days=30)

    qs = (
        ClinicVisit.objects.filter(school=school, visit_date__date__gte=since)
        .values("visit_date__date")
        .annotate(count=Count("id"), sent_home=Count("id", filter=Q(is_sent_home=True)))
        .order_by("visit_date__date")
    )

    labels = [r["visit_date__date"].strftime("%d/%m") for r in qs]
    visits = [r["count"] for r in qs]
    sent_home = [r["sent_home"] for r in qs]

    return JsonResponse(
        {
            "labels": labels,
            "datasets": [
                {
                    "label": "إجمالي الزيارات",
                    "data": visits,
                    "borderColor": brand.STATUS_DANGER,
                    "fill": False,
                    "tension": 0.3,
                },
                {
                    "label": "أُرسل للمنزل",
                    "data": sent_home,
                    "borderColor": brand.STATUS_WARNING,
                    "fill": False,
                    "tension": 0.3,
                },
            ],
        }
    )


# ════════════════════════════════════════════════════════════════════
# ✅ 10 KPIs من Ct.zip — مُضافة في v5
# الهدف: بناء لوحة مؤشرات الأداء الرئيسية (SchoolOS SWOT خطوة شهر 1)
# ════════════════════════════════════════════════════════════════════


@login_required
@capability_required("analytics.school")
def kpi_dashboard(request):
    """لوحة KPIs العشرة — للمدير فقط"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    return render(
        request,
        "analytics/kpi_dashboard.html",
        {
            "school": school,
            "year": year,
            "subtitle": f"{getattr(school, 'name', '') or 'المدرسة'} — {year}",
        },
    )


@login_required
@capability_required("analytics.school")
@cache_page(300)
@vary_on_cookie
def api_kpis_all(request):
    """JSON: 10 KPIs — يُعيد بيانات KPIService.compute()"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    data = KPIService.compute(school, year)

    # Serialize school to string for JSON
    return JsonResponse(
        {
            "kpis": data["kpis"],
            "school": str(data["school"]),
            "year": data["year"],
            "as_of": str(data["generated_at"]),
            "summary": data["summary"],
        }
    )


# ── تقرير KPIs الشهري — PDF فوري ────────────────────────────────────


@login_required
@capability_required("analytics.school")
def kpi_monthly_pdf(request):
    """PDF: تقرير KPIs الشهري"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    preview = request.GET.get("preview") == "1"
    paper = request.GET.get("paper", "A4")
    data = KPIService.compute(school, year)

    plan_domains = OperationalDomain.objects.filter(school=school, academic_year=year).order_by(
        "order"
    )
    red_kpis = [
        k for k in data["kpis"].values() if k.get("traffic") == "red" and k.get("value") is not None
    ]
    ctx = {**data, "plan_domains": plan_domains, "red_kpis": red_kpis, "paper_size": paper}

    from core.audit_export import log_export

    log_export(request, "analytics.kpi_monthly_pdf", object_repr=f"KPIs — {data['month_label']}")

    if preview:
        return render(request, "analytics/kpi_monthly_report.html", ctx)

    html = render_to_string("analytics/kpi_monthly_report.html", ctx, request=request)
    return render_pdf(html, f"kpi_{school.code}_{data['month_label']}.pdf", paper_size=paper)
