# analytics/views.py
"""
لوحة الإحصاءات المتقدمة — SchoolOS V2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تشمل 7 APIs كاملة للرسوم البيانية بـ Chart.js
"""
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Avg, Count, Q, F, Sum, FloatField, Case, When, IntegerField
from django.db.models.functions import TruncDate, TruncMonth, ExtractMonth
from django.utils import timezone
from datetime import timedelta, date

from core.models import (
    CustomUser, ClassGroup, StudentEnrollment, Membership,
    ClinicVisit, HealthRecord, SchoolBus, BehaviorInfraction,
    LibraryBook, BookBorrowing
)
from operations.models import (
    Session, StudentAttendance, TeacherAbsence, SubstituteAssignment
)
from assessments.models import (
    AnnualSubjectResult, StudentSubjectResult,
    SubjectClassSetup, AssessmentPackage
)
from quality.models import OperationalProcedure, OperationalDomain


def _admin_required(request):
    return request.user.is_admin() or request.user.is_superuser


# ── لوحة القيادة الرئيسية ────────────────────────────────────
@login_required
def analytics_dashboard(request):
    """لوحة الإحصاءات المتقدمة للمدير"""
    if not _admin_required(request):
        return HttpResponse("غير مسموح — للمدير فقط", status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    today  = timezone.now().date()

    # ── KPIs الأساسية ─────────────────────────────────────────
    total_students = StudentEnrollment.objects.filter(
        class_group__school=school, class_group__academic_year=year, is_active=True
    ).count()

    total_teachers = Membership.objects.filter(
        school=school, is_active=True, role__name__in=["teacher", "coordinator"]
    ).count()

    # الحضور
    sessions_today = Session.objects.filter(school=school, date=today)
    att_today      = StudentAttendance.objects.filter(session__in=sessions_today)
    present_today  = att_today.filter(status="present").count()
    total_att      = att_today.count()
    att_pct_today  = round(present_today / total_att * 100) if total_att else 0

    # العيادة
    clinic_visits_today = ClinicVisit.objects.filter(
        school=school, visit_date__date=today
    ).count()
    chronic_cases = HealthRecord.objects.filter(
        student__memberships__school=school
    ).exclude(chronic_diseases="").distinct().count()

    # السلوك
    behavior_infractions_month = BehaviorInfraction.objects.filter(
        school=school, date__month=today.month, date__year=today.year
    ).count()
    critical_infractions = BehaviorInfraction.objects.filter(
        school=school, level__in=[3, 4], is_resolved=False
    ).count()

    # النقل
    total_buses = SchoolBus.objects.filter(school=school).count()
    students_on_bus = StudentEnrollment.objects.filter(
        student__bus_routes__bus__school=school, is_active=True
    ).distinct().count()

    # المكتبة
    total_books  = LibraryBook.objects.filter(school=school).count()
    active_loans = BookBorrowing.objects.filter(
        book__school=school, status="BORROWED"
    ).count()
    overdue_books = BookBorrowing.objects.filter(
        book__school=school, status="OVERDUE"
    ).count()

    # الخطة التشغيلية
    total_procs     = OperationalProcedure.objects.filter(school=school, academic_year=year).count()
    completed_procs = OperationalProcedure.objects.filter(
        school=school, academic_year=year, status="Completed"
    ).count()
    plan_pct = round(completed_procs / total_procs * 100) if total_procs else 0

    kpis = {
        "total_students":     total_students,
        "total_teachers":     total_teachers,
        "att_pct_today":      att_pct_today,
        "present_today":      present_today,
        "clinic_today":       clinic_visits_today,
        "chronic_cases":      chronic_cases,
        "behavior_month":     behavior_infractions_month,
        "critical_issues":    critical_infractions,
        "total_buses":        total_buses,
        "bus_students":       students_on_bus,
        "library_books":      total_books,
        "active_loans":       active_loans,
        "overdue_books":      overdue_books,
        "plan_pct":           plan_pct,
        "completed_procs":    completed_procs,
        "total_procs":        total_procs,
    }

    return render(request, "analytics/dashboard.html", {
        "kpis":   kpis,
        "year":   year,
        "school": school,
        "today":  today,
    })


# ── API 1: منحنى الحضور (آخر 30 يوم) ────────────────────────
@login_required
def api_attendance_trend(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    days   = int(request.GET.get("days", 30))
    since  = timezone.now().date() - timedelta(days=days)

    qs = (
        StudentAttendance.objects
        .filter(session__school=school, session__date__gte=since)
        .values("session__date")
        .annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
        )
        .order_by("session__date")
    )

    labels = []
    present_data = []
    absent_data  = []

    for row in qs:
        d = row["session__date"]
        labels.append(d.strftime("%d/%m"))
        pct = round(row["present"] / row["total"] * 100) if row["total"] else 0
        present_data.append(pct)
        absent_data.append(100 - pct)

    return JsonResponse({
        "labels": labels,
        "datasets": [
            {
                "label": "نسبة الحضور %",
                "data": present_data,
                "borderColor": "#16a34a",
                "backgroundColor": "rgba(22,163,74,0.1)",
                "fill": True,
                "tension": 0.3,
            },
            {
                "label": "نسبة الغياب %",
                "data": absent_data,
                "borderColor": "#dc2626",
                "backgroundColor": "rgba(220,38,38,0.1)",
                "fill": True,
                "tension": 0.3,
            }
        ]
    })


# ── API 2: توزيع الدرجات ────────────────────────────────────
@login_required
def api_grades_distribution(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    grades = StudentSubjectResult.objects.filter(
        setup__school=school,
        setup__academic_year=year
    ).values_list("total", flat=True)

    buckets = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "50-59": 0, "أقل من 50": 0}
    for g in grades:
        if g is None:
            continue
        g = float(g)
        if g >= 90:   buckets["90-100"] += 1
        elif g >= 80: buckets["80-89"] += 1
        elif g >= 70: buckets["70-79"] += 1
        elif g >= 60: buckets["60-69"] += 1
        elif g >= 50: buckets["50-59"] += 1
        else:         buckets["أقل من 50"] += 1

    colors = ["#16a34a","#2563eb","#d97706","#ea580c","#7c3aed","#dc2626"]

    return JsonResponse({
        "labels": list(buckets.keys()),
        "datasets": [{
            "label": "عدد الطلاب",
            "data": list(buckets.values()),
            "backgroundColor": colors,
            "borderWidth": 1,
        }]
    })


# ── API 3: مقارنة الفصول الدراسية ───────────────────────────
@login_required
def api_class_comparison(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    classes = (
        StudentSubjectResult.objects
        .filter(setup__school=school, setup__academic_year=year)
        .values("setup__class_group__grade", "setup__class_group__section")
        .annotate(avg=Avg("total"))
        .order_by("setup__class_group__grade", "setup__class_group__section")
    )

    labels = [r["setup__class_group__grade"] + "-" + (r["setup__class_group__section"] or "") for r in classes]
    data   = [round(float(r["avg"]), 1) if r["avg"] else 0 for r in classes]

    return JsonResponse({
        "labels": labels,
        "datasets": [{
            "label": "متوسط الدرجات",
            "data": data,
            "backgroundColor": "rgba(138,21,56,0.7)",
            "borderColor": "#8A1538",
            "borderWidth": 1,
        }]
    })


# ── API 4: مقارنة المواد الدراسية ───────────────────────────
@login_required
def api_subject_comparison(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    subjects = (
        StudentSubjectResult.objects
        .filter(setup__school=school, setup__academic_year=year)
        .values("setup__subject__name_ar")
        .annotate(
            avg=Avg("total"),
            fail_count=Count("id", filter=Q(total__lt=50)),
            total=Count("id"),
        )
        .order_by("-avg")
    )

    labels     = [r["setup__subject__name_ar"] or "—" for r in subjects]
    avg_data   = [round(float(r["avg"]), 1) if r["avg"] else 0 for r in subjects]
    fail_rates = [
        round(r["fail_count"] / r["total"] * 100) if r["total"] else 0
        for r in subjects
    ]

    return JsonResponse({
        "labels": labels,
        "datasets": [
            {
                "label": "متوسط الدرجة",
                "data": avg_data,
                "backgroundColor": "rgba(37,99,235,0.7)",
                "borderColor": "#2563eb",
                "borderWidth": 1,
                "yAxisID": "y",
            },
            {
                "label": "نسبة الرسوب %",
                "data": fail_rates,
                "backgroundColor": "rgba(220,38,38,0.7)",
                "borderColor": "#dc2626",
                "borderWidth": 1,
                "yAxisID": "y1",
                "type": "line",
            }
        ]
    })


# ── API 5: تقدم الخطة التشغيلية (حسب المجال) ───────────────
@login_required
def api_plan_progress(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    domains = OperationalDomain.objects.filter(
        school=school, academic_year=year
    ).order_by("order")

    labels   = []
    complete = []
    pending  = []

    for d in domains:
        total   = d.total_procedures
        done    = d.completed_procedures
        labels.append(d.name[:20])
        complete.append(done)
        pending.append(total - done)

    return JsonResponse({
        "labels": labels,
        "datasets": [
            {
                "label": "مكتمل",
                "data": complete,
                "backgroundColor": "#16a34a",
            },
            {
                "label": "قيد التنفيذ",
                "data": pending,
                "backgroundColor": "#d97706",
            }
        ]
    })


# ── API 6: مخالفات السلوك (آخر 6 أشهر) ─────────────────────
@login_required
def api_behavior_trend(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    today  = timezone.now().date()
    since  = today.replace(day=1) - timedelta(days=150)

    qs = (
        BehaviorInfraction.objects
        .filter(school=school, date__gte=since)
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
        next_year  = cur.year if cur.month < 12 else cur.year + 1
        cur = cur.replace(year=next_year, month=next_month)

    month_names = ["يناير","فبراير","مارس","أبريل","مايو","يونيو",
                   "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
    labels = [month_names[m-1] for _, m in months]

    data_by_level = {1: {}, 2: {}, 3: {}, 4: {}}
    for row in qs:
        key = (row["date__year"], row["date__month"])
        data_by_level[row["level"]][key] = row["count"]

    level_colors = {
        1: ("#16a34a", "بسيطة"),
        2: ("#d97706", "متوسطة"),
        3: ("#ea580c", "جسيمة"),
        4: ("#dc2626", "شديدة الخطورة"),
    }

    datasets = []
    for lvl, (color, label) in level_colors.items():
        datasets.append({
            "label": label,
            "data": [data_by_level[lvl].get(m, 0) for m in months],
            "backgroundColor": color,
        })

    return JsonResponse({"labels": labels, "datasets": datasets})


# ── API 7: الطلاب الراسبون (حسب الفصل) ─────────────────────
@login_required
def api_failing_by_class(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")

    qs = (
        StudentSubjectResult.objects
        .filter(setup__school=school, setup__academic_year=year, total__lt=50)
        .values("setup__class_group__grade", "setup__class_group__section")
        .annotate(fail_count=Count("student", distinct=True))
        .order_by("-fail_count")[:10]
    )

    return JsonResponse({
        "labels": [r["setup__class_group__grade"] + "-" + (r["setup__class_group__section"] or "") for r in qs],
        "datasets": [{
            "label": "طلاب راسبون",
            "data": [r["fail_count"] for r in qs],
            "backgroundColor": "#dc2626",
        }]
    })


# ── API 8: إحصائيات العيادة (آخر 30 يوم) ────────────────────
@login_required
def api_clinic_stats(request):
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    since  = timezone.now().date() - timedelta(days=30)

    qs = (
        ClinicVisit.objects
        .filter(school=school, visit_date__date__gte=since)
        .values("visit_date__date")
        .annotate(count=Count("id"), sent_home=Count("id", filter=Q(is_sent_home=True)))
        .order_by("visit_date__date")
    )

    labels      = [r["visit_date__date"].strftime("%d/%m") for r in qs]
    visits      = [r["count"] for r in qs]
    sent_home   = [r["sent_home"] for r in qs]

    return JsonResponse({
        "labels": labels,
        "datasets": [
            {"label": "إجمالي الزيارات", "data": visits,    "borderColor": "#dc2626", "fill": False, "tension": 0.3},
            {"label": "أُرسل للمنزل",    "data": sent_home, "borderColor": "#d97706", "fill": False, "tension": 0.3},
        ]
    })


# ════════════════════════════════════════════════════════════════════
# ✅ 10 KPIs من Ct.zip — مُضافة في v5
# الهدف: بناء لوحة مؤشرات الأداء الرئيسية (SchoolOS SWOT خطوة شهر 1)
# ════════════════════════════════════════════════════════════════════

@login_required
def kpi_dashboard(request):
    """لوحة KPIs العشرة — للمدير فقط"""
    if not _admin_required(request):
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    return render(request, 'analytics/kpi_dashboard.html', {'school': school, 'year': year})


@login_required
def api_kpis_all(request):
    """
    JSON يحسب 10 KPIs دفعة واحدة.
    بصيغ Ct.zip الرياضية الجاهزة.
    """
    if not _admin_required(request):
        return JsonResponse({}, status=403)

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    today  = timezone.now().date()
    month  = today.month

    kpis = {}

    # ── KPI 1: نسبة حضور الطلبة ─────────────────────────────────
    # هدف: ≥95% | إنذار: <90% | مصدر: Attendance
    sessions_month = Session.objects.filter(school=school, date__month=month, date__year=today.year)
    att_all  = StudentAttendance.objects.filter(session__in=sessions_month)
    present  = att_all.filter(status='present').count()
    total_att = att_all.count()
    kpis['student_attendance_pct'] = {
        'label': 'نسبة حضور الطلبة',
        'value': round(present / total_att * 100, 1) if total_att else 0,
        'target': 95, 'warning': 90, 'unit': '%', 'frequency': 'أسبوعي',
    }

    # ── KPI 2: مخالفات/100 طالب ─────────────────────────────────
    # هدف: ≤3 | إنذار: >5 | مصدر: BehaviorInfraction
    total_students = StudentEnrollment.objects.filter(
        class_group__school=school, class_group__academic_year=year, is_active=True
    ).count()
    infractions_month = BehaviorInfraction.objects.filter(
        school=school, date__month=month, date__year=today.year
    ).count()
    rate_per100 = round(infractions_month / total_students * 100, 2) if total_students else 0
    kpis['infractions_per_100'] = {
        'label': 'مخالفات/100 طالب',
        'value': rate_per100,
        'target': 3, 'warning': 5, 'unit': '', 'frequency': 'شهري',
        'direction': 'lower_better',
    }

    # ── KPI 3: رصد الدرجات في الوقت ─────────────────────────────
    # هدف: ≥98% | تحذير: <95% | مصدر: ExamGradeSheet (إن وُجد)
    try:
        from exam_control.models import ExamGradeSheet
        total_sheets = ExamGradeSheet.objects.filter(schedule__session__school=school).count()
        submitted    = ExamGradeSheet.objects.filter(
            schedule__session__school=school, status='submitted'
        ).count()
        grading_pct  = round(submitted / total_sheets * 100, 1) if total_sheets else 100
    except Exception:
        grading_pct = 100
    kpis['grading_on_time_pct'] = {
        'label': 'رصد الدرجات في الوقت',
        'value': grading_pct,
        'target': 98, 'warning': 95, 'unit': '%', 'frequency': 'فصلي',
    }

    # ── KPI 4: أيام اختبار بلا حوادث ───────────────────────────
    # هدف: 100% | أي حادث = تحقيق
    try:
        from exam_control.models import ExamSession, ExamIncident
        exam_days = ExamSession.objects.filter(school=school).values_list('start_date', flat=True)
        incident_days = ExamIncident.objects.filter(
            session__school=school, severity__gte=2
        ).values_list('incident_time__date', flat=True).distinct()
        clean_days_pct = round(
            (len(set(exam_days) - set(incident_days)) / len(set(exam_days))) * 100, 1
        ) if exam_days else 100
    except Exception:
        clean_days_pct = 100
    kpis['exam_clean_days_pct'] = {
        'label': 'أيام اختبار بلا حوادث',
        'value': clean_days_pct,
        'target': 100, 'warning': 99, 'unit': '%', 'frequency': 'فصلي',
    }

    # ── KPI 5: غياب المعلمين غير المبرر ─────────────────────────
    # هدف: ≤1% | إنذار: >2% | مصدر: TeacherAbsence
    total_teacher_days = Membership.objects.filter(
        school=school, is_active=True, role__name__in=['teacher', 'coordinator']
    ).count() * 20  # تقدير 20 يوم دراسي
    unexcused = TeacherAbsence.objects.filter(
        school=school, date__month=month, date__year=today.year,
        is_excused=False
    ).count()
    teacher_abs_pct = round(unexcused / total_teacher_days * 100, 2) if total_teacher_days else 0
    kpis['teacher_unexcused_absence_pct'] = {
        'label': 'غياب المعلمين غير المبرر',
        'value': teacher_abs_pct,
        'target': 1, 'warning': 2, 'unit': '%', 'frequency': 'شهري',
        'direction': 'lower_better',
    }

    # ── KPI 6: حوادث النقل / 100,000 كم ─────────────────────────
    # هدف: 0 | أي >0 = تحقيق | مصدر: SchoolBus + AuditLog
    kpis['transport_incidents_rate'] = {
        'label': 'حوادث النقل / 100,000 كم',
        'value': 0,  # يُحدَّث عند ربط GPS
        'target': 0, 'warning': 0.1, 'unit': '', 'frequency': 'شهري',
        'direction': 'lower_better',
    }

    # ── KPI 7: استعارة المكتبة / طالب ───────────────────────────
    # هدف: ≥2 | متابعة: <1 | مصدر: BookBorrowing
    borrowings = BookBorrowing.objects.filter(
        book__school=school,
        borrow_date__year=today.year
    ).count()
    borrows_per_student = round(borrowings / total_students, 2) if total_students else 0
    kpis['library_borrows_per_student'] = {
        'label': 'استعارة المكتبة / طالب',
        'value': borrows_per_student,
        'target': 2, 'warning': 1, 'unit': '', 'frequency': 'فصلي',
    }

    # ── KPI 8: مطابقة المقصف للصحة ──────────────────────────────
    # هدف: ≥95% | مصدر: تقارير وزارة الصحة (يدوي)
    kpis['canteen_health_compliance_pct'] = {
        'label': 'مطابقة المقصف للصحة',
        'value': None,  # يُدخَل يدوياً من تقارير وزارة الصحة
        'target': 95, 'warning': 90, 'unit': '%', 'frequency': 'فصلي',
        'note': 'يُدخَل يدوياً من تقارير وزارة الصحة',
    }

    # ── KPI 9: تنفيذ خطط الإخلاء ────────────────────────────────
    # هدف: 100% | مصدر: AuditLog أو يدوي
    kpis['evacuation_plan_execution_pct'] = {
        'label': 'تنفيذ خطط الإخلاء',
        'value': None,  # يُدخَل يدوياً
        'target': 100, 'warning': 99, 'unit': '%', 'frequency': 'فصلي',
        'note': 'يُسجَّل بعد كل تدريب إخلاء',
    }

    # ── KPI 10: ساعات التطوير المهني / معلم ─────────────────────
    # هدف: ≥10 ساعات | تحذير: <6 | مصدر: AuditLog أو يدوي
    kpis['professional_dev_hours'] = {
        'label': 'ساعات التطوير المهني / معلم',
        'value': None,  # يُدخَل من سجلات التطوير
        'target': 10, 'warning': 6, 'unit': 'ساعة', 'frequency': 'فصلي',
        'note': 'يُسجَّل من محاضر ورش التطوير',
    }

    # إضافة ترافيق (🟢🟡🔴) لكل KPI
    for k, v in kpis.items():
        val = v.get('value')
        if val is None:
            v['traffic'] = 'grey'
        else:
            direction = v.get('direction', 'higher_better')
            target  = v['target']
            warning = v['warning']
            if direction == 'higher_better':
                v['traffic'] = 'green' if val >= target else ('yellow' if val >= warning else 'red')
            else:  # lower_better
                v['traffic'] = 'green' if val <= target else ('yellow' if val <= warning else 'red')

    return JsonResponse({'kpis': kpis, 'school': str(school), 'year': year, 'as_of': str(today)})


# ── تقرير KPIs الشهري — PDF فوري ────────────────────────────────────

@login_required
def kpi_monthly_pdf(request):
    """PDF: تقرير KPIs الشهري — يمكن للمدير توليده فوراً"""
    if not _admin_required(request):
        return HttpResponse("غير مسموح", status=403)

    from core.pdf_utils import render_pdf
    from django.template.loader import render_to_string
    from analytics.services import KPIService
    from quality.models import OperationalDomain

    school = request.user.get_school()
    year   = request.GET.get("year", "2025-2026")
    preview = request.GET.get("preview") == "1"

    data         = KPIService.compute(school, year)
    plan_domains = OperationalDomain.objects.filter(
        school=school, academic_year=year
    ).order_by("order")
    red_kpis = [
        kpi for kpi in data["kpis"].values()
        if kpi.get("traffic") == "red" and kpi.get("value") is not None
    ]

    ctx = {**data, "plan_domains": plan_domains, "red_kpis": red_kpis}

    if preview:
        return render(request, "analytics/kpi_monthly_report.html", ctx)

    html = render_to_string("analytics/kpi_monthly_report.html", ctx, request=request)
    return render_pdf(html, f"kpi_{school.code}_{data['month_label']}.pdf")
