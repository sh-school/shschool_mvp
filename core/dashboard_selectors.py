"""core/dashboard_selectors.py — قراءةُ سياق لوحة التحكّم لكل دور، بلا `request`.

طبقةُ قراءةٍ (selectors) لا عرض: حارسُ الطبقات (`tests/layering_ratchet.py`)
يسقف كلَّ دالّةٍ في ملفّ عروضٍ بستّين سطراً وخمسة استدعاءات ORM — وكانت
`core/views_dashboard.py::dashboard` أثقلَ عرضٍ في المشروع (188 استدعاءَ
ORM، محسوبةً من دوالّ السياق التي يستدعيها). فُصلت هذه الدوالّ إلى هنا —
كانت أصلاً بلا اقترانٍ بـ`request` (تأخذ `user, school, today` صراحةً)،
فالنقل نسخٌ لا إعادةَ كتابة.

هذا الفصل لا يُصلح استيراد `core` من ستّ وحداتٍ نازلة (assessments،
behavior، clinic، library، operations، transport) — الملفّ لا يزال في core،
والاستيراداتُ تنتقل معه. ذلك قرارٌ معماريٌّ أوسع (البند 9) منفصلٌ عن هذا.
"""

import datetime
from collections.abc import Iterable
from typing import Any

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.academic_calendar import academic_year_for_school, academic_year_window
from core.capabilities import has_capability
from core.domain.attendance import attendance_rate
from core.models.academic import StudentEnrollment, grade_order
from core.permissions import SCHEDULE_BROWSE, get_department_teacher_ids
from core.verdict_read import failing_statuses, passing_statuses
from library.models import BookBorrowing
from operations.models import (
    AbsenceAlert,
    ClassExit,
    CompensatorySession,
    DailyExitTally,
    Session,
    StudentAttendance,
    TeacherAbsence,
    TeacherSwap,
)
from transport.models import BusRoute, SchoolBus

# قيادة المدرسة — لوحة KPI الشاملة
DIRECTOR_ROLES = {"principal", "vice_admin", "vice_academic"}

# معلمون وكوادر تدريسية — حصص اليوم + طلبات التبديل
TEACHER_ROLES = {
    "teacher",
    "coordinator",
    "ese_teacher",
    "e_projects_coordinator",
    "specialist",
    "teacher_assistant",
    "ese_assistant",
}

# أخصائيون اجتماعيون ونفسيون ومرشدون أكاديميون
SPECIALIST_SOCIAL_ROLES = {"social_worker", "psychologist", "academic_advisor"}

# معالجو النطق والعلاج الوظائفي
THERAPIST_ROLES = {"speech_therapist", "occupational_therapist"}

# إداريون تشغيليون (بصلاحيات مقيّدة)
ADMIN_OPS_ROLES = {"admin", "admin_supervisor", "secretary", "receptionist"}

# خدمات الدعم (عيادة + مكتبة + تقنية)
SERVICE_ROLES = {"nurse", "librarian", "it_technician"}

# النقل المدرسي
TRANSPORT_ROLES = {"transport_officer", "bus_supervisor"}

DIRECTOR_TITLES = {
    "vice_admin": "لوحة النائب الإداريّ",
    "vice_academic": "لوحة النائب الأكاديميّ",
}


def get_student_ctx(user, school, today):
    """بيانات لوحة تحكم الطالب: حضور + حصص اليوم + نتائج سنوية."""
    from core.models import StudentEnrollment

    year = academic_year_for_school(school)

    # حضور الطالب (aggregate واحد) — العامَ الدراسيَّ الجاري وحده: العنوان «حضوري هذا العام»،
    # وبلا النافذة كان الرقم تراكمياً لكلّ الأعوام. (W-20261008-001 · البند 2)
    att_rows = StudentAttendance.objects.filter(school=school, student=user)
    window = academic_year_window(school, today)
    if window:
        att_rows = att_rows.filter(session__date__range=window)
    att = att_rows.aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
    )
    present = att["present"]
    absent = att["absent"]
    late = att["late"]
    total = present + absent + late
    att_pct = attendance_rate(present, total, empty=100)

    # حصص اليوم عبر فصل الطالب
    enrollment = StudentEnrollment.objects.current_of(user)
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
        passed=Count("id", filter=Q(status__in=passing_statuses())),
        failed=Count("id", filter=Q(status__in=failing_statuses())),
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


def get_director_ctx(school, today):
    """بيانات لوحة تحكم الإدارة: حصص + حضور + تقييمات + سلوك + عيادة + مكتبة + عمليات."""
    year = academic_year_for_school(school)
    # غيابُ اليوم بطلابٍ مميَّزين بحكم `_judge` يأتي من قسم «day» الذي تسجّله وحدةُ operations (dashboard_registry) — لا استيرادَ نازلاً هنا.
    # عدّادٌ لا أسماء (D-171م: لوحةُ المدير أرقامٌ ورابطٌ إلى الشاشة المحروسة) —
    # فالأسماءُ تُفتح في «متابعة الحضور» بقدرتها `student_affairs.follow_up`.
    alerts_count = AbsenceAlert.objects.filter(school=school, status="pending").count()

    # إحصائيات التقييمات — aggregate واحد
    annual = AnnualSubjectResult.objects.filter(school=school, academic_year=year).aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(status__in=passing_statuses())),
        failed=Count("id", filter=Q(status__in=failing_statuses())),
    )
    total_annual = annual["total"]
    passed_annual = annual["passed"]
    failed_annual = annual["failed"]
    pass_pct = round(passed_annual / total_annual * 100) if total_annual else 0
    failing_count = (
        AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status__in=failing_statuses()
        )
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

    library_overdue = BookBorrowing.objects.filter(book__school=school).late().count()

    pending_swaps = TeacherSwap.objects.filter(
        school=school, status__in=["accepted_b", "pending_coordinator", "pending_vp"]
    ).count()
    pending_comp = CompensatorySession.objects.filter(school=school, status="pending").count()
    absent_teachers_today = TeacherAbsence.objects.filter(school=school, date=today).count()

    return {
        "view_type": "director",
        "alerts_count": alerts_count,
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


def get_teacher_ctx(user, school, today, role):
    """بيانات لوحة تحكم المعلم والمنسق: حصص اليوم + الإعدادات + طلبات التبديل."""
    year = academic_year_for_school(school)

    sessions = (
        Session.objects.filter(school=school, teacher=user, date=today)
        .select_related("class_group", "subject")
        .order_by("start_time")
    )
    # حصصُ أعمدة جدول الشعبة مؤقّتةٌ بـ`Session.teacher` مُسنَدٍ حتميّ (W-20261006-005): ليست «حصصي» ولا «حصّتي التالية» لمن نُسبت إليه.
    sessions = sessions.exclude(provisional=True)
    # بتوقيت المدرسة (Asia/Qatar) لا UTC: `now()` يعطي UTC فتنحرف «الحصّة التالية» ثلاث ساعات (W-20261010-047).
    now = timezone.localtime().time()
    next_session = next(
        (s for s in sessions if s.start_time >= now and s.status == "scheduled"), None
    )
    my_setups = (
        SubjectClassSetup.objects.filter(
            school=school, teacher=user, academic_year=year, is_active=True
        )
        .select_related("subject", "class_group")
        .order_by(grade_order("class_group__grade"), "subject__name_ar")
    )
    my_pending_swaps = TeacherSwap.objects.filter(
        school=school, teacher_b=user, status="pending_b"
    ).count()

    # `weekly_schedule` بلا وسائط تعرض الجدولَ العامّ (كلُّ المعلّمين) لمن
    # يتصفّح غيرَه (`SCHEDULE_BROWSE`، ومنهم المنسّق ومسؤولُ التعليم
    # الإلكترونيّ) — لا جدولَه هو. فبطاقةُ «جدولي» هنا تُصرَّح بوسائطها صراحةً
    # (`view=teacher&teacher=<هو>`) لا الافتراض، وتبقى «الجدول العامّ» متاحةً
    # منفصلةً لمن يملك حقَّ تصفّح غيره (قرارُ المالك 2026-09-23).
    my_weekly_schedule_url = f"{reverse('weekly_schedule')}?view=teacher&teacher={user.id}"
    general_schedule_url = reverse("weekly_schedule") if role in SCHEDULE_BROWSE else ""

    # شُعبُ بطاقة «شُعبي للرصد»: المصدرُ نفسُه الذي تعرضه `grid_classes` بلا قائمةٍ ثانية، مرتَّبةً رقميّاً بالصفّ ثمّ الشعبة (7/1 ثمّ 12/2).
    from operations.services.class_grid import classes_for

    shobi_classes = sorted(classes_for(user, school), key=lambda c: c.school_order)

    # ملاحظةُ «مؤقّتاً إلى حين اعتماد الجدول» تتبع الجدولَ المعتمَدَ فعلاً (توليدٌ بحالة «معتمد» لعام المدرسة) لا المفتاحَ اليدويَّ وحدَه.
    from operations.models import ScheduleGeneration

    schedule_approved = ScheduleGeneration.objects.filter(
        school=school, academic_year=year, status="approved"
    ).exists()

    ctx = {
        "view_type": "teacher",
        "shobi_classes": shobi_classes,
        "schedule_approved": schedule_approved,
        "sessions": sessions,
        "next_session": next_session,
        "my_setups": my_setups,
        "my_pending_swaps": my_pending_swaps,
        "my_weekly_schedule_url": my_weekly_schedule_url,
        "general_schedule_url": general_schedule_url,
        "my_students": _my_students_ctx(user, school, today, sessions),
    }

    if role == "coordinator":
        ctx["view_type"] = "coordinator"
        ctx["coord_pending_swaps"] = TeacherSwap.objects.filter(
            school=school, status__in=["accepted_b", "pending_coordinator"]
        ).count()
        ctx["coord_pending_comp"] = CompensatorySession.objects.filter(
            school=school, status="pending"
        ).count()
        # يعدّ غائبي قسمه وحده: القائمةُ التي تفتحها النقرةُ محصورةٌ في قسمه، وكان
        # العدّادُ يعدّ المدرسةَ كلَّها فيقول «5» وتفتح صفّين.
        absent_today = TeacherAbsence.objects.filter(school=school, date=today)
        dept_ids = get_department_teacher_ids(user)
        if dept_ids is not None:
            absent_today = absent_today.filter(teacher_id__in=dept_ids)
        ctx["coord_absent_today"] = absent_today.count()

    return ctx


def _my_students_ctx(
    user: Any, school: Any, today: datetime.date, sessions: Iterable[Any]
) -> dict[str, int | None]:
    """«طلابي» (W-20261010-040، D-335م): أعدادٌ مجمَّعة لطلاب شعب المعلّم في جدوله اليوم — لا اسمَ طالبٍ ولا ترتيبَ ولا مقارنة.

    الشعبُ من حصص اليوم المحمَّلة أصلاً (`sessions` قُيِّم قبلَ هذا فلا استعلامَ لها)، والطلابُ استعلامٌ فرعيٌّ لا قائمةٌ في الذاكرة:
    فاستعلامان ثابتان مهما بلغ عددُ الشعب والطلاب. صفرٌ منهما حين لا حصصَ اليوم.

    `exit_total` مجموعُ `DailyExitTally.exit_count` اليوم (يشمل الخروجَ الطبّيّ: خرج بإذن لا مخالفة، D-251م)، و`out_now` عددُ الطلاب
    ذوي خروجٍ مفتوحٍ اليومَ (`ClassExit.returned_at` فارغ؛ وما أغلقه الجرسُ بلا عودة له `returned_at` فلا يدخل). وكلاهما `None` لمن لا يملك
    قدرةَ رصد الحصّة (الدالّةُ مشتركةٌ مع المنسّق، D-171م). وعدّادُ الإشعارات ليس هنا: لا قيمةَ له في سياق اللوحة اليوم، وقراءتُه من `core`
    استيرادٌ نازلٌ إلى `notifications` يرفضه حارسُ الطبقات؛ والجرسُ يجلبه من مسار `api/unread-count/`.
    """
    block: dict[str, int | None] = {"exit_total": None, "out_now": None}
    if not has_capability(user, "attendance.mark"):
        return block
    group_ids = {s.class_group_id for s in sessions}
    block["exit_total"] = block["out_now"] = 0
    if not group_ids:
        return block
    students = StudentEnrollment.objects.filter(
        class_group_id__in=group_ids, class_group__school=school, is_active=True
    ).values("student_id")
    block["exit_total"] = (
        DailyExitTally.objects.filter(school=school, date=today, student_id__in=students).aggregate(
            total=Sum("exit_count")
        )["total"]
        or 0
    )
    block["out_now"] = (
        ClassExit.objects.filter(
            school=school, left_at__date=today, returned_at__isnull=True, student_id__in=students
        )
        .values("student_id")
        .distinct()
        .count()
    )
    return block


def get_specialist_social_ctx(user, school, today):
    """
    سياق الأخصائيين الاجتماعيين والنفسيين والمرشدين الأكاديميين.
    يُركّز على: الغياب المتكرر + مخالفات السلوك + حالات الطلاب.
    """

    year = academic_year_for_school(school)

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
    behavior_critical = BehaviorInfraction.objects.filter(school=school, level__gte=3).count()

    # نتائج الطلاب — راسبون
    failing_students = (
        AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status__in=failing_statuses()
        )
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


def get_therapist_ctx(user, school, today):
    """
    سياق المعالجين: أخصائي النطق + أخصائي العلاج الوظائفي.
    يُركّز على: جلسات اليوم + الطلاب المحالين + إحصائيات الأسبوع.
    """
    sessions_today = (
        Session.objects.filter(school=school, teacher=user, date=today)
        .select_related("class_group", "subject")
        .order_by("start_time")
    )
    # بتوقيت المدرسة (Asia/Qatar) لا UTC: `now()` يعطي UTC فتنحرف «الحصّة التالية» ثلاث ساعات (W-20261010-047).
    now = timezone.localtime().time()
    next_session = next(
        (s for s in sessions_today if s.start_time >= now and s.status == "scheduled"),
        None,
    )
    total_today = sessions_today.count()
    completed_today = sessions_today.filter(status="completed").count()

    # إحصائيات الأسبوع — مفيدة لمتابعة التقدم
    # الأسبوعُ المدرسيّ يبدأ الأحد لا الاثنين: weekday() تُرقّم الاثنين صفراً،
    # فحساب «أوّل الأسبوع» بها مباشرةً كان يرجع لاثنين الأسبوع السابق. أضيفت
    # فروةُ يومٍ واحد (Sun=6 → 0) قبل القسمة، فصار الأحدُ نفسُه بدايةَ أسبوعه.
    days_since_sunday = (today.weekday() + 1) % 7
    week_start = today - datetime.timedelta(days=days_since_sunday)
    week_sessions = Session.objects.filter(
        school=school,
        teacher=user,
        date__gte=week_start,
        date__lte=today,
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


def get_activities_ctx(user, school, today):
    """
    سياق منسق الأنشطة.
    يُركّز على: الأنشطة الجارية + مشاركة الطلاب + السلوك.
    """
    from student_affairs.models import StudentActivity

    month_start = today.replace(day=1)
    year = academic_year_for_school(school)

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
        school=school,
        academic_year=year,
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


def get_admin_ops_ctx(user, school, today, role):
    """
    سياق الإداريين: admin + admin_supervisor + secretary + receptionist.
    يُركّز على: المهام الإدارية + الإشعارات + حضور الموظفين.
    """
    # كلُّ عدّادٍ بقدرة وجهته (W-20261003-030): رقمٌ يُعرض لمن لا تُفتح له شاشتُه
    # كشفٌ بلا مسوّغ — فيغيب (None) ويُخفيه القالب، ولا يُنفَّذ له استعلام.
    absent_teachers: int | None = None
    if has_capability(user, "operations.reports"):
        absent_teachers = TeacherAbsence.objects.filter(school=school, date=today).count()

    pending_swaps: int | None = None
    pending_comp: int | None = None
    if has_capability(user, "schedule.view"):
        pending_swaps = TeacherSwap.objects.filter(
            school=school, status__in=["pending_b", "accepted_b", "pending_coordinator"]
        ).count()
        pending_comp = CompensatorySession.objects.filter(school=school, status="pending").count()

    # قائمةُ الأسماء بقدرتها المخصّصة لها وحدَها (قرارُ المالك 2026-10-03)، لا بـ`follow_up`
    # التي تفتح ملفّاتِ الطلبة؛ وتنبيهاتُ المشرف لطلبة جناحه وحدَهم (قرارُ 2026-09-15).
    recent_alerts: Iterable[AbsenceAlert] = []
    if has_capability(user, "dashboard.absence_alert_names"):
        from wings.scope import student_scope

        recent_alerts = (
            student_scope(user, school)
            .narrow(AbsenceAlert.objects.filter(school=school, status="pending"), "student_id")
            .select_related("student")
            .order_by("-created_at")[:5]
        )

    ctx = {
        "view_type": "admin_ops",
        "admin_role": role,
        "absent_teachers_today": absent_teachers,
        "pending_swaps": pending_swaps,
        "pending_comp": pending_comp,
        "recent_alerts": recent_alerts,
    }
    if role == "admin_supervisor":
        ctx.update(supervisor_record_ctx(user, school, today))
    return ctx


def supervisor_record_ctx(user, school, today):
    """رصدُ الغياب في رأس لوحة مشرف الجناح — فهو عملُه الأوّل كلَّ صباح.

    كان الرابطُ في القائمة وحدَها، ولوحتُه التي يفتحها أوّلَ الدخول لا تذكر
    الرصدَ أصلاً: عملُه اليوميُّ الرئيسيُّ غائبٌ عن صفحته الرئيسيّة.
    """
    from core.dashboard_presentation import chunk_for_grid
    from core.dashboard_registry import dashboard_section_context
    from operations.school_days import school_day
    from operations.services import ScheduleService
    from wings.services import holds_school_wide, record_panels, supervisor_watchlist

    year = academic_year_for_school(school)
    day = school_day(school, today)
    watchlist = supervisor_watchlist(user, school, year, today)
    ctx = {
        "record_panels": [],
        "day": today,
        # والإجازةُ من تقويم الوزارة لا من الأسبوع وحدَه: ثلاثاءُ الإجازة كان يُعرض
        # يومَ دوامٍ وكلُّ شُعبه «لم تُرصد».
        "school_day": day,
        # ما ينتظره اليوم: إخطارُ أولياء الأمور، ومن عند العتبات (لوحتُه v1).
        **watchlist,
        # يومٌ سيّئُ الحضور يطيل القائمة عموداً واحداً — عمودان يقلّصان الطول.
        "awaiting_contact_cols": chunk_for_grid(watchlist["awaiting_contact"], 2),
        "at_gates_cols": chunk_for_grid(watchlist["at_gates"], 2),
    }
    # حاصرُ الغياب العامّ يرى الأجنحةَ الخمسة في «رصد الغياب» (أمرُ المالك 2026-10-06): لا بطاقاتِ أجنحةٍ مكدّسةً في رئيسيّته.
    ctx["school_wide"] = holds_school_wide(user)
    # عدّادُ العتبات فقط (لا قائمةُ أسماء): الإخطارُ انتقل إلى كاتب الغياب (D-245م/D-246م) — يُعرض عدداً ورابطاً.
    ctx["gates_count"] = len(watchlist["at_gates"])
    ctx.update(dashboard_section_context("supervisor", user, school, today))
    if day.is_open and not ctx["school_wide"]:
        # الحصصُ تُولَّد إن لم تكن — وإلّا بدت الشُّعبُ «بلا حصص» صباحاً.
        ScheduleService.ensure_sessions_for_date(school, today)
        ctx["record_panels"] = record_panels(user, school, year, today)
    return ctx


def get_transport_ctx(user, school, today):
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


def get_service_ctx(user, school, today, role):
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
        ctx["library_overdue"] = BookBorrowing.objects.filter(book__school=school).late().count()
        ctx["library_today"] = BookBorrowing.objects.filter(
            book__school=school,
            borrow_date=today,
        ).count()

    elif role == "it_technician":
        from core.models.user import CustomUser

        ctx["active_users"] = (
            CustomUser.objects.filter(
                is_active=True,
                memberships__school=school,
            )
            .distinct()
            .count()
        )
        ctx["total_users"] = (
            CustomUser.objects.filter(
                memberships__school=school,
            )
            .distinct()
            .count()
        )

    return ctx
