import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from core import dashboard_selectors
from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required, has_capability
from core.dashboard_presentation import present
from core.domain.attendance import attendance_rate, percent
from core.models.academic import Wing
from core.models.school import School
from operations.selectors import (
    attendance_status_counts,
    chronic_absentee_count,
    class_sessions_on,
    pending_absence_alerts,
    pending_compensatory_count,
    pending_excuse_count,
    session_status_counts,
    swap_count,
    teacher_absence_count,
    teacher_sessions_between,
    teacher_sessions_on,
)
from transport.models import BusRoute, SchoolBus

# ─────────────────────────────────────────────────────────────────────
# Private context builders — called from dashboard() dispatcher
# ─────────────────────────────────────────────────────────────────────


def _get_student_ctx(user, school, today):
    """بيانات لوحة تحكم الطالب: حضور + حصص اليوم + نتائج سنوية."""
    from core.models import StudentEnrollment

    year = academic_year_for_school(school)
    att = attendance_status_counts(school, student=user)
    present, absent, late = att["present"], att["absent"], att["late"]
    enrollment = StudentEnrollment.objects.current_of(user)
    has_class = bool(enrollment and enrollment.class_group)
    results = dashboard_selectors.annual_result_counts(school, year, student=user)

    return {
        "view_type": "student",
        "student_att_pct": attendance_rate(present, present + absent + late, empty=100),
        "student_present": present,
        "student_absent": absent,
        "student_late": late,
        # حصصُ اليوم عبر فصل الطالب.
        "student_sessions": class_sessions_on(school, enrollment.class_group, today)
        if has_class
        else [],
        "class_group": enrollment.class_group if enrollment else None,
        "student_subjects_total": results["total"],
        "student_passed": results["passed"],
        "student_failed": results["failed"],
    }


#: طلباتُ التبديل التي تنتظر الإدارةَ أو المنسّق — وما ينتظر المعلّمَ الثاني ليس منها.
_DIRECTOR_SWAP_STATUSES = ("accepted_b", "pending_coordinator", "pending_vp")


def _attendance_day(school: School, day: datetime.date) -> tuple[dict[str, int], int]:
    """(عدّادُ الحضور، مقامُه) ليومٍ — المقامُ الحاضرُ والغائبُ والمتأخّرُ دون المعذور."""
    att = attendance_status_counts(school, session__date=day)
    return att, att["present"] + att["absent"] + att["late"]


def _get_director_ctx(school, today):
    """بيانات لوحة تحكم الإدارة: حصص + حضور + تقييمات + سلوك + عيادة + مكتبة + عمليات."""
    year = academic_year_for_school(school)
    sessions = session_status_counts(school, today)
    att, total_att = _attendance_day(school, today)
    att_y, total_y = _attendance_day(school, today - datetime.timedelta(days=1))
    att_pct = attendance_rate(att["present"], total_att)
    att_pct_y = attendance_rate(att_y["present"], total_y, empty=None)
    annual = dashboard_selectors.annual_result_counts(school, year)

    return {
        "view_type": "director",
        "sessions_today": sessions["total"],
        "completed": sessions["completed"],
        "in_progress": sessions["in_progress"],
        "present": att["present"],
        "absent": att["absent"],
        "late": att["late"],
        "attendance_pct": att_pct,
        # الفرقُ عن الأمس — ولا فرقَ حين لا رصدَ أمس.
        "att_delta": att_pct - att_pct_y if att_pct_y is not None else None,
        "absent_delta": att["absent"] - att_y["absent"] if total_y else None,
        "total_students": total_att,
        "alerts": pending_absence_alerts(school, order="-created_at", limit=5),
        "total_annual": annual["total"],
        "passed_annual": annual["passed"],
        "failed_annual": annual["failed"],
        "pass_pct": percent(annual["passed"], annual["total"]),
        "failing_count": dashboard_selectors.failing_student_count(school, year),
        "year": year,
        "incomplete_setups": dashboard_selectors.incomplete_setup_count(school, year),
        **dashboard_selectors.behaviour_month_and_critical(school, today),
        **dashboard_selectors.clinic_counts_on(school, today),
        "library_overdue": dashboard_selectors.loan_count(school, status="OVERDUE"),
        "pending_swaps": swap_count(school, *_DIRECTOR_SWAP_STATUSES),
        "pending_comp": pending_compensatory_count(school),
        "absent_teachers_today": teacher_absence_count(school, today),
    }


def _next_scheduled(sessions):
    """أوّلُ حصّةٍ مجدولةٍ لم يحن وقتُها بعد — أو `None`."""
    now = timezone.now().time()
    return next((s for s in sessions if s.start_time >= now and s.status == "scheduled"), None)


def _get_teacher_ctx(user, school, today, role):
    """بيانات لوحة تحكم المعلم والمنسق: حصص اليوم + الإعدادات + طلبات التبديل."""
    sessions = teacher_sessions_on(school, user, today)
    ctx = {
        "view_type": "teacher",
        "sessions": sessions,
        "next_session": _next_scheduled(sessions),
        "my_setups": dashboard_selectors.teacher_setups(
            school, user, academic_year_for_school(school)
        ),
        "my_pending_swaps": swap_count(school, "pending_b", teacher_b=user),
    }

    if role == "coordinator":
        ctx["view_type"] = "coordinator"
        ctx["coord_pending_swaps"] = swap_count(school, "accepted_b", "pending_coordinator")
        ctx["coord_pending_comp"] = pending_compensatory_count(school)
        ctx["coord_absent_today"] = teacher_absence_count(school, today)

    return ctx


# ─────────────────────────────────────────────────────────────────────
# Context builders — v7 roles
# ─────────────────────────────────────────────────────────────────────


def _get_specialist_social_ctx(user, school, today):
    """
    سياق الأخصائيين الاجتماعيين والنفسيين والمرشدين الأكاديميين.
    يُركّز على: الغياب المتكرر + مخالفات السلوك + حالات الطلاب.
    """
    year = academic_year_for_school(school)
    month_start = today.replace(day=1)

    return {
        "view_type": "specialist_social",
        # طلابُ الغياب المتكرّر: ثلاثُ مرّاتٍ فأكثر هذا الشهر.
        "chronic_absent": chronic_absentee_count(school, month_start, min_days=3),
        "recent_alerts": pending_absence_alerts(school, order="-created_at", limit=5),
        "behavior_monthly": dashboard_selectors.infractions_since_count(school, month_start),
        # مخالفاتٌ خطرة: المستوى الثالث فأعلى.
        "behavior_critical": dashboard_selectors.critical_infraction_count(school),
        "failing_students": dashboard_selectors.failing_student_count(school, year),
        "year": year,
    }


def _get_therapist_ctx(user, school, today):
    """
    سياق المعالجين: أخصائي النطق + أخصائي العلاج الوظائفي.
    يُركّز على: جلسات اليوم + الطلاب المحالين + إحصائيات الأسبوع.
    """
    sessions_today = teacher_sessions_on(school, user, today)
    total_today = sessions_today.count()
    completed_today = sessions_today.filter(status="completed").count()

    # إحصائيات الأسبوع — مفيدة لمتابعة التقدم
    week_start = today - datetime.timedelta(days=today.weekday())
    week_sessions = teacher_sessions_between(school, user, week_start, today)
    week_total = week_sessions.count()
    week_completed = week_sessions.filter(status="completed").count()

    # عدد الفصول/الشُّعب الفريدة التي يعمل معها المعالج
    unique_groups = sessions_today.values("class_group").distinct().count()

    return {
        "view_type": "therapist",
        "sessions_today": sessions_today,
        "next_session": _next_scheduled(sessions_today),
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
    year = academic_year_for_school(school)

    # أنشطة هذا العام الدراسي
    activities_year = StudentActivity.objects.filter(
        school=school,
        academic_year=year,
    )
    activities_total = activities_year.count()
    activities_this_month = activities_year.filter(date__gte=month_start).count()
    students_participating = activities_year.values("student").distinct().count()

    return {
        "view_type": "activities",
        # حصص اليوم لمنسق الأنشطة (إذا كانت مُعيَّنة)
        "sessions_today": teacher_sessions_on(school, user, today),
        "behavior_monthly": dashboard_selectors.infractions_since_count(school, month_start),
        "activities_total": activities_total,
        "activities_this_month": activities_this_month,
        "students_participating": students_participating,
    }


def _get_admin_ops_ctx(user, school, today, role):
    """
    سياق الإداريين: admin + admin_supervisor + secretary + receptionist.
    يُركّز على: المهام الإدارية + الإشعارات + حضور الموظفين.
    """
    ctx = {
        "view_type": "admin_ops",
        "admin_role": role,
        "absent_teachers_today": teacher_absence_count(school, today),
        "pending_swaps": swap_count(school, "pending_b", "accepted_b", "pending_coordinator"),
        "pending_comp": pending_compensatory_count(school),
        "recent_alerts": pending_absence_alerts(school, order="-created_at", limit=5),
    }
    if role == "admin_supervisor":
        ctx.update(_supervisor_record_ctx(user, school, today))
    return ctx


def _supervisor_record_ctx(user, school, today):
    """رصدُ الغياب في رأس لوحة مشرف الجناح — فهو عملُه الأوّل كلَّ صباح.

    كان الرابطُ في القائمة وحدَها، ولوحتُه التي يفتحها أوّلَ الدخول لا تذكر
    الرصدَ أصلاً: عملُه اليوميُّ الرئيسيُّ غائبٌ عن صفحته الرئيسيّة.
    """
    from operations.bells import day_type_for
    from operations.services import ScheduleService
    from wings.services import record_panels, supervisor_watchlist

    year = academic_year_for_school(school)
    if day_type_for(today):
        # الحصصُ تُولَّد إن لم تكن — وإلّا بدت الشُّعبُ «بلا حصص» صباحاً.
        ScheduleService.ensure_sessions_for_date(school, today)
    return {
        "record_panels": record_panels(user, school, year, today),
        "day": today,
        "is_school_day": bool(day_type_for(today)),
        # ما ينتظره اليوم: إخطارُ أولياء الأمور، ومن عند العتبات (لوحتُه v1).
        **supervisor_watchlist(user, school, year, today),
    }


def _get_transport_ctx(user, school, today):
    """
    سياق مسؤول النقل + مشرف الحافلة.
    يُركّز على: الحافلات النشطة + المسارات.
    """
    # `SchoolBus` لا حقلَ فيه اسمُه `is_active` — حقولُه رقمُ الحافلة والسائقُ
    # والمشرفُ والسعةُ ورقمُ كروة والرابط. وكان الاستعلامُ يطلبه، فتسقط لوحةُ
    # **كلّ** من دورُه نقلٌ بخطأ خادمٍ لا بصفحةٍ ناقصة. ولا يُخترع الحقلُ لإرضاء
    # الاستعلام: الحافلةُ إمّا مسجَّلةٌ في المدرسة أو ليست فيها، ولا حالةَ ثالثة.
    buses = SchoolBus.objects.filter(school=school).count()
    # والمسارُ لا يحمل مدرستَه — يحملها بحافلته. وكان هذا السطرُ يسقط هو أيضاً،
    # لكنّ الاستعلامَ قبله كان يسقط أوّلاً فيحجبه: عطبان متتاليان يُرى أوّلُهما وحدَه.
    total_routes = BusRoute.objects.filter(bus__school=school).count()

    return {
        "view_type": "transport_mgmt",
        "buses_count": buses,
        "total_routes": total_routes,
    }


def _get_service_ctx(user, school, today, role):
    """
    سياق أدوار الخدمة الداعمة: nurse + librarian + it_technician.
    يجلب البيانات المناسبة لكل دور.
    """
    ctx = {"view_type": "service", "service_role": role}

    if role == "nurse":
        ctx.update(dashboard_selectors.clinic_counts_on(school, today))
    elif role == "librarian":
        ctx["library_overdue"] = dashboard_selectors.loan_count(school, status="OVERDUE")
        ctx["library_today"] = dashboard_selectors.loan_count(school, borrow_date=today)
    elif role == "it_technician":
        ctx["active_users"] = dashboard_selectors.school_user_count(school, active_only=True)
        ctx["total_users"] = dashboard_selectors.school_user_count(school, active_only=False)

    return ctx


# ─────────────────────────────────────────────────────────────────────
# Main view — clean dispatcher
# ─────────────────────────────────────────────────────────────────────

# قيادة المدرسة — لوحة KPI الشاملة
_DIRECTOR_ROLES = {"principal", "vice_admin", "vice_academic"}

# معلمون وكوادر تدريسية — حصص اليوم + طلبات التبديل
_TEACHER_ROLES = {
    "teacher",
    "coordinator",
    "ese_teacher",
    "e_projects_coordinator",
    "specialist",
    "teacher_assistant",
    "ese_assistant",
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
@capability_required("dashboard.open")
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

    # بتوقيت المدرسة لا UTC: بين 21:00 و00:00 UTC يختلف اليومان، فكان تكليفُ بديلٍ
    # يبدأ «اليوم» (بتوقيت قطر) لا يُرى في اللوحة (سقوطُ البوّابة عند منتصف الليل 2026-09-14).
    today = timezone.localdate()
    ctx = {"today": today, "school": school}

    if role == "student":
        ctx.update(_get_student_ctx(user, school, today))
    elif user.is_superuser or role in _DIRECTOR_ROLES:
        ctx.update(_get_director_ctx(school, today))
        if has_capability(user, "wings.excuse_after_deadline"):
            # أعذارٌ أرسلها المشرفون بعد مهلة العودة — تنتظر النائبَ (قرارُ 2026-09-14).
            ctx["pending_excuses"] = pending_excuse_count(school)
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
    elif Wing.is_held_by(user, today):
        # بديلُ الجناح من ملاحظي الطلبة وعمّال الخدمات (قرارُ المدير): لا لوحةَ لدوره،
        # ولوحتُه يومَ تكليفه رصدُ جناحه — لا «لم تُفعَّل صلاحيّاتُك».
        ctx["view_type"] = "wing_holder"
        ctx.update(_supervisor_record_ctx(user, school, today))
    else:
        ctx["view_type"] = "other"

    ctx.update(present(ctx))
    return render(request, "dashboard/main.html", ctx)
