import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.permissions import role_required
from core.models.access import ALL_STAFF_ROLES
from library.models import BookBorrowing
from operations.models import (
    AbsenceAlert,
    CompensatorySession,
    Session,
    StudentAttendance,
    TeacherAbsence,
    TeacherSwap,
)
from transport.models import BusRoute, SchoolBus


# ─────────────────────────────────────────────────────────────────────
# Private context builders — called from dashboard() dispatcher
# ─────────────────────────────────────────────────────────────────────


def _get_student_ctx(user, school, today):
    """بيانات لوحة تحكم الطالب: حضور + حصص اليوم + نتائج سنوية."""
    from core.models import StudentEnrollment

    year = settings.CURRENT_ACADEMIC_YEAR

    # حضور الطالب (aggregate واحد)
    att = StudentAttendance.objects.filter(school=school, student=user).aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
    )
    present = att["present"]
    absent = att["absent"]
    late = att["late"]
    total = present + absent + late
    att_pct = round(present / total * 100) if total else 100

    # حصص اليوم عبر فصل الطالب
    enrollment = (
        StudentEnrollment.objects.filter(student=user, is_active=True)
        .select_related("class_group")
        .first()
    )
    student_sessions = []
    if enrollment and enrollment.class_group:
        student_sessions = (
            Session.objects.filter(school=school, class_group=enrollment.class_group, date=today)
            .select_related("subject", "teacher")
            .order_by("start_time")
        )

    # نتائج سنوية (aggregate واحد بدل 3 queries)
    results_stats = AnnualSubjectResult.objects.filter(
        student=user, school=school, academic_year=year
    ).aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(status="pass")),
        failed=Count("id", filter=Q(status="fail")),
    )

    return {
        "view_type": "student",
        "student_att_pct": att_pct,
        "student_present": present,
        "student_absent": absent,
        "student_late": late,
        "student_sessions": student_sessions,
        "class_group": enrollment.class_group if enrollment else None,
        "student_subjects_total": results_stats["total"],
        "student_passed": results_stats["passed"],
        "student_failed": results_stats["failed"],
    }


def _get_director_ctx(school, today):
    """بيانات لوحة تحكم الإدارة: حصص + حضور + تقييمات + سلوك + عيادة + مكتبة + عمليات."""
    year = settings.CURRENT_ACADEMIC_YEAR
    yesterday = today - datetime.timedelta(days=1)

    # حصص اليوم — aggregate واحد
    session_stats = Session.objects.filter(school=school, date=today).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status="completed")),
        in_progress=Count("id", filter=Q(status="in_progress")),
    )

    # حضور اليوم — aggregate واحد
    att = StudentAttendance.objects.filter(school=school, session__date=today).aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
    )
    present = att["present"]
    absent = att["absent"]
    total_att = present + absent + att["late"]
    att_pct = round(present / total_att * 100) if total_att else 0

    # حضور الأمس للمقارنة — aggregate واحد
    att_y = StudentAttendance.objects.filter(school=school, session__date=yesterday).aggregate(
        present_y=Count("id", filter=Q(status="present")),
        absent_y=Count("id", filter=Q(status="absent")),
        late_y=Count("id", filter=Q(status="late")),
    )
    present_y = att_y["present_y"]
    absent_y = att_y["absent_y"]
    total_y = present_y + absent_y + att_y["late_y"]
    att_pct_y = round(present_y / total_y * 100) if total_y else None
    att_delta = att_pct - att_pct_y if att_pct_y is not None else None
    absent_delta = absent - absent_y if total_y else None

    alerts = (
        AbsenceAlert.objects.filter(school=school, status="pending")
        .select_related("student")
        .order_by("-created_at")[:5]
    )

    # إحصائيات التقييمات — aggregate واحد
    annual = AnnualSubjectResult.objects.filter(school=school, academic_year=year).aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(status="pass")),
        failed=Count("id", filter=Q(status="fail")),
    )
    total_annual = annual["total"]
    passed_annual = annual["passed"]
    failed_annual = annual["failed"]
    pass_pct = round(passed_annual / total_annual * 100) if total_annual else 0
    failing_count = (
        AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
        .values("student")
        .distinct()
        .count()
    )
    incomplete_setups = (
        SubjectClassSetup.objects.filter(school=school, academic_year=year, is_active=True)
        .exclude(packages__isnull=False)
        .count()
    )

    # سلوك — aggregate واحد
    behavior = BehaviorInfraction.objects.filter(school=school).aggregate(
        monthly=Count("id", filter=Q(date__month=today.month, date__year=today.year)),
        critical=Count("id", filter=Q(level__gte=3)),
    )

    # عيادة — aggregate واحد
    clinic = ClinicVisit.objects.filter(school=school, visit_date__date=today).aggregate(
        total=Count("id"),
        sent_home=Count("id", filter=Q(is_sent_home=True)),
    )

    library_overdue = BookBorrowing.objects.filter(
        book__school=school, status="OVERDUE"
    ).count()

    pending_swaps = TeacherSwap.objects.filter(
        school=school, status__in=["accepted_b", "pending_coordinator", "pending_vp"]
    ).count()
    pending_comp = CompensatorySession.objects.filter(school=school, status="pending").count()
    absent_teachers_today = TeacherAbsence.objects.filter(school=school, date=today).count()

    return {
        "view_type": "director",
        "sessions_today": session_stats["total"],
        "completed": session_stats["completed"],
        "in_progress": session_stats["in_progress"],
        "present": present,
        "absent": absent,
        "late": att["late"],
        "attendance_pct": att_pct,
        "att_delta": att_delta,
        "absent_delta": absent_delta,
        "total_students": total_att,
        "alerts": alerts,
        "total_annual": total_annual,
        "passed_annual": passed_annual,
        "failed_annual": failed_annual,
        "pass_pct": pass_pct,
        "failing_count": failing_count,
        "year": year,
        "incomplete_setups": incomplete_setups,
        "behavior_monthly": behavior["monthly"],
        "behavior_critical": behavior["critical"],
        "clinic_today": clinic["total"],
        "clinic_sent_home": clinic["sent_home"],
        "library_overdue": library_overdue,
        "pending_swaps": pending_swaps,
        "pending_comp": pending_comp,
        "absent_teachers_today": absent_teachers_today,
    }


def _get_teacher_ctx(user, school, today, role):
    """بيانات لوحة تحكم المعلم والمنسق: حصص اليوم + الإعدادات + طلبات التبديل."""
    year = settings.CURRENT_ACADEMIC_YEAR

    sessions = (
        Session.objects.filter(school=school, teacher=user, date=today)
        .select_related("class_group", "subject")
        .order_by("start_time")
    )
    now = timezone.now().time()
    next_session = next(
        (s for s in sessions if s.start_time >= now and s.status == "scheduled"), None
    )
    my_setups = (
        SubjectClassSetup.objects.filter(
            school=school, teacher=user, academic_year=year, is_active=True
        )
        .select_related("subject", "class_group")
        .order_by("class_group__grade", "subject__name_ar")
    )
    my_pending_swaps = TeacherSwap.objects.filter(
        school=school, teacher_b=user, status="pending_b"
    ).count()

    ctx = {
        "view_type": "teacher",
        "sessions": sessions,
        "next_session": next_session,
        "my_setups": my_setups,
        "my_pending_swaps": my_pending_swaps,
    }

    if role == "coordinator":
        ctx["view_type"] = "coordinator"
        ctx["coord_pending_swaps"] = TeacherSwap.objects.filter(
            school=school, status__in=["accepted_b", "pending_coordinator"]
        ).count()
        ctx["coord_pending_comp"] = CompensatorySession.objects.filter(
            school=school, status="pending"
        ).count()
        ctx["coord_absent_today"] = TeacherAbsence.objects.filter(
            school=school, date=today
        ).count()

    return ctx


# ─────────────────────────────────────────────────────────────────────
# Context builders — v7 roles
# ─────────────────────────────────────────────────────────────────────


def _get_specialist_social_ctx(user, school, today):
    """
    سياق الأخصائيين الاجتماعيين والنفسيين والمرشدين الأكاديميين.
    يُركّز على: الغياب المتكرر + مخالفات السلوك + حالات الطلاب.
    """
    from core.models import StudentEnrollment

    year = settings.CURRENT_ACADEMIC_YEAR

    # طلاب الغياب المتكرر (أكثر من 3 أيام هذا الشهر)
    month_start = today.replace(day=1)
    chronic_absent = (
        StudentAttendance.objects.filter(
            school=school,
            status="absent",
            session__date__gte=month_start,
        )
        .values("student_id")
        .annotate(absent_count=Count("id"))
        .filter(absent_count__gte=3)
        .count()
    )

    # آخر 5 تنبيهات غياب
    recent_alerts = (
        AbsenceAlert.objects.filter(school=school, status="pending")
        .select_related("student")
        .order_by("-created_at")[:5]
    )

    # مخالفات سلوكية هذا الشهر
    behavior_monthly = BehaviorInfraction.objects.filter(
        school=school,
        date__gte=month_start,
    ).count()

    # مخالفات خطرة (مستوى 3+)
    behavior_critical = BehaviorInfraction.objects.filter(
        school=school, level__gte=3
    ).count()

    # نتائج الطلاب — راسبون
    failing_students = (
        AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
        .values("student")
        .distinct()
        .count()
    )

    return {
        "view_type": "specialist_social",
        "chronic_absent": chronic_absent,
        "recent_alerts": recent_alerts,
        "behavior_monthly": behavior_monthly,
        "behavior_critical": behavior_critical,
        "failing_students": failing_students,
        "year": year,
    }


def _get_therapist_ctx(user, school, today):
    """
    سياق المعالجين: أخصائي النطق + أخصائي العلاج الوظائفي.
    يُركّز على: جلسات اليوم + الطلاب المحالين + إحصائيات الأسبوع.
    """
    sessions_today = (
        Session.objects.filter(school=school, teacher=user, date=today)
        .select_related("class_group", "subject")
        .order_by("start_time")
    )
    now = timezone.now().time()
    next_session = next(
        (s for s in sessions_today if s.start_time >= now and s.status == "scheduled"),
        None,
    )
    total_today = sessions_today.count()
    completed_today = sessions_today.filter(status="completed").count()

    # إحصائيات الأسبوع — مفيدة لمتابعة التقدم
    week_start = today - datetime.timedelta(days=today.weekday())
    week_sessions = Session.objects.filter(
        school=school, teacher=user,
        date__gte=week_start, date__lte=today,
    )
    week_total = week_sessions.count()
    week_completed = week_sessions.filter(status="completed").count()

    # عدد الفصول/الشُّعب الفريدة التي يعمل معها المعالج
    unique_groups = sessions_today.values("class_group").distinct().count()

    return {
        "view_type": "therapist",
        "sessions_today": sessions_today,
        "next_session": next_session,
        "total_sessions_today": total_today,
        "completed_sessions_today": completed_today,
        "week_total": week_total,
        "week_completed": week_completed,
        "unique_groups_today": unique_groups,
    }


def _get_activities_ctx(user, school, today):
    """
    سياق منسق الأنشطة.
    يُركّز على: الأنشطة الجارية + مشاركة الطلاب + السلوك.
    """
    from student_affairs.models import StudentActivity

    month_start = today.replace(day=1)
    year = getattr(settings, "CURRENT_ACADEMIC_YEAR", "2025-2026")

    behavior_monthly = BehaviorInfraction.objects.filter(
        school=school,
        date__gte=month_start,
    ).count()

    # حصص اليوم لمنسق الأنشطة (إذا كانت مُعيَّنة)
    sessions_today = (
        Session.objects.filter(school=school, teacher=user, date=today)
        .select_related("class_group", "subject")
        .order_by("start_time")
    )

    # أنشطة هذا العام الدراسي
    activities_year = StudentActivity.objects.filter(
        school=school, academic_year=year,
    )
    activities_total = activities_year.count()
    activities_this_month = activities_year.filter(date__gte=month_start).count()
    students_participating = activities_year.values("student").distinct().count()

    return {
        "view_type": "activities",
        "sessions_today": sessions_today,
        "behavior_monthly": behavior_monthly,
        "activities_total": activities_total,
        "activities_this_month": activities_this_month,
        "students_participating": students_participating,
    }


def _get_admin_ops_ctx(user, school, today, role):
    """
    سياق الإداريين: admin + admin_supervisor + secretary + receptionist.
    يُركّز على: المهام الإدارية + الإشعارات + حضور الموظفين.
    """
    absent_teachers = TeacherAbsence.objects.filter(school=school, date=today).count()

    pending_swaps = TeacherSwap.objects.filter(
        school=school, status__in=["pending_b", "accepted_b", "pending_coordinator"]
    ).count()
    pending_comp = CompensatorySession.objects.filter(school=school, status="pending").count()

    recent_alerts = (
        AbsenceAlert.objects.filter(school=school, status="pending")
        .select_related("student")
        .order_by("-created_at")[:5]
    )

    return {
        "view_type": "admin_ops",
        "admin_role": role,
        "absent_teachers_today": absent_teachers,
        "pending_swaps": pending_swaps,
        "pending_comp": pending_comp,
        "recent_alerts": recent_alerts,
    }


def _get_transport_ctx(user, school, today):
    """
    سياق مسؤول النقل + مشرف الحافلة.
    يُركّز على: الحافلات النشطة + المسارات.
    """
    active_buses = SchoolBus.objects.filter(school=school, is_active=True).count()
    total_routes = BusRoute.objects.filter(school=school).count()

    return {
        "view_type": "transport_mgmt",
        "active_buses": active_buses,
        "total_routes": total_routes,
    }


def _get_service_ctx(user, school, today, role):
    """
    سياق أدوار الخدمة الداعمة: nurse + librarian + it_technician.
    يجلب البيانات المناسبة لكل دور.
    """
    ctx = {"view_type": "service", "service_role": role}

    if role == "nurse":
        clinic = ClinicVisit.objects.filter(school=school, visit_date__date=today).aggregate(
            total=Count("id"),
            sent_home=Count("id", filter=Q(is_sent_home=True)),
        )
        ctx["clinic_today"] = clinic["total"]
        ctx["clinic_sent_home"] = clinic["sent_home"]

    elif role == "librarian":
        ctx["library_overdue"] = BookBorrowing.objects.filter(
            book__school=school, status="OVERDUE"
        ).count()
        ctx["library_today"] = BookBorrowing.objects.filter(
            book__school=school,
            borrow_date=today,
        ).count()

    elif role == "it_technician":
        from core.models.user import CustomUser

        ctx["active_users"] = CustomUser.objects.filter(
            is_active=True, memberships__school=school,
        ).distinct().count()
        ctx["total_users"] = CustomUser.objects.filter(
            memberships__school=school,
        ).distinct().count()

    return ctx


# ─────────────────────────────────────────────────────────────────────
# Main view — clean dispatcher
# ─────────────────────────────────────────────────────────────────────

# قيادة المدرسة — لوحة KPI الشاملة
_DIRECTOR_ROLES = {"principal", "vice_admin", "vice_academic"}

# معلمون وكوادر تدريسية — حصص اليوم + طلبات التبديل
_TEACHER_ROLES = {
    "teacher", "coordinator", "ese_teacher", "specialist",
    "teacher_assistant", "ese_assistant",
}

# أخصائيون اجتماعيون ونفسيون ومرشدون أكاديميون
_SPECIALIST_SOCIAL_ROLES = {"social_worker", "psychologist", "academic_advisor"}

# معالجو النطق والعلاج الوظائفي
_THERAPIST_ROLES = {"speech_therapist", "occupational_therapist"}

# إداريون تشغيليون (بصلاحيات مقيّدة)
_ADMIN_OPS_ROLES = {"admin", "admin_supervisor", "secretary", "receptionist"}

# خدمات الدعم (عيادة + مكتبة + تقنية)
_SERVICE_ROLES = {"nurse", "librarian", "it_technician"}

# النقل المدرسي
_TRANSPORT_ROLES = {"transport_officer", "bus_supervisor"}


@login_required
@role_required(ALL_STAFF_ROLES | {"student", "parent"})
def dashboard(request):
    """لوحة التحكم الرئيسية — موزّع يعيد التوجيه أو يبني السياق حسب الدور."""
    user = request.user
    school = user.get_school()
    role = user.get_role()

    if not school:
        return HttpResponseForbidden("<h2 dir='rtl'>لم يتم تعيينك في أي مدرسة</h2>")

    # ولي الأمر → بوابته المخصصة
    if role == "parent":
        return redirect("parent_dashboard")

    today = timezone.now().date()
    ctx = {"today": today, "school": school}

    if role == "student":
        ctx.update(_get_student_ctx(user, school, today))
    elif user.is_superuser or role in _DIRECTOR_ROLES:
        ctx.update(_get_director_ctx(school, today))
    elif role in _TEACHER_ROLES:
        ctx.update(_get_teacher_ctx(user, school, today, role))
    elif role in _SPECIALIST_SOCIAL_ROLES:
        ctx.update(_get_specialist_social_ctx(user, school, today))
    elif role in _THERAPIST_ROLES:
        ctx.update(_get_therapist_ctx(user, school, today))
    elif role == "activities_coordinator":
        ctx.update(_get_activities_ctx(user, school, today))
    elif role in _ADMIN_OPS_ROLES:
        ctx.update(_get_admin_ops_ctx(user, school, today, role))
    elif role in _TRANSPORT_ROLES:
        ctx.update(_get_transport_ctx(user, school, today))
    elif role in _SERVICE_ROLES:
        ctx.update(_get_service_ctx(user, school, today, role))
    else:
        ctx["view_type"] = "other"

    return render(request, "dashboard/main.html", ctx)
