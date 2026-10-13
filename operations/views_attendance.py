"""operations/views_attendance.py — views الحضور والحصص اليومية."""

import logging
from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.formats import date_format

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required

from .day_attendance import is_recorder
from .models import Session
from .services import ScheduleService, SubstituteService, class_grid

logger = logging.getLogger(__name__)


@login_required
@capability_required("schedule.day")
def schedule(request):
    """جدول حصص المعلم اليوم"""
    school = request.user.get_school()
    today = request.GET.get("date", timezone.localdate().isoformat())
    try:
        selected_date = date.fromisoformat(today)
    except ValueError:
        selected_date = timezone.localdate()

    # ── تأكد من وجود حصص للتاريخ المختار (أي تاريخ) ──
    ScheduleService.ensure_sessions_for_date(school, selected_date)

    # ── القيادة (مدير/نائب) تشاهد كل حصص المدرسة — المعلم يشاهد حصصه فقط ──
    is_leader = request.user.is_leadership()
    if is_leader:
        sessions = (
            Session.objects.filter(school=school, date=selected_date)
            .select_related("class_group", "subject", "teacher")
            .order_by("start_time")
        )
        # ── فلاتر ذكية للقيادة ──
        teacher_filter = request.GET.get("teacher", "")
        class_filter = request.GET.get("class", "")
        status_filter = request.GET.get("status", "")
        period_filter = request.GET.get("period", "")
        show_all = request.GET.get("all", "")
        if teacher_filter:
            sessions = sessions.filter(teacher_id=teacher_filter)
        if class_filter:
            sessions = sessions.filter(class_group_id=class_filter)
        if status_filter:
            sessions = sessions.filter(status=status_filter)
        elif not show_all:
            # ── افتراضياً: فقط الحصص التي تحتاج تسجيل حضور ──
            sessions = sessions.exclude(status="completed")
        if period_filter.isdigit():
            # رقمُ الحصّة محفوظٌ فيها: كان يُستنتج من أوقات الجدول، فيخطئ بين الطوابق والخميس.
            sessions = sessions.filter(period_number=int(period_filter))
        # إحصائيات سريعة
        all_count = Session.objects.filter(school=school, date=selected_date).count()
        completed_count = Session.objects.filter(
            school=school, date=selected_date, status="completed"
        ).count()
    else:
        sessions = (
            Session.objects.filter(school=school, teacher=request.user, date=selected_date)
            .select_related("class_group", "subject")
            .order_by("start_time")
        )
        teacher_filter = class_filter = status_filter = period_filter = show_all = ""
        all_count = completed_count = 0

    now = timezone.localtime().time()
    next_session = next(
        (s for s in sessions if s.start_time >= now and s.status == "scheduled"), None
    )

    # ── بيانات الفلاتر (للقيادة فقط) ──
    filter_teachers = []
    filter_classes = []
    if is_leader:
        from core.models.access import Membership

        filter_teachers = (
            Membership.objects.filter(
                school=school,
                is_active=True,
                role__name__in=("teacher", "coordinator", "ese_teacher"),
            )
            .select_related("user")
            .order_by("user__full_name")
        )
        from core.models.academic import ClassGroup

        filter_classes = ClassGroup.objects.filter(
            school=school, academic_year=academic_year_for_school(school), is_active=True
        ).in_school_order()

    open_count = all_count - completed_count
    date_label = f"{selected_date:%d/%m/%Y}"
    return render(
        request,
        "teacher/schedule.html",
        {
            # سطرُ الترويسة: التاريخُ مرّةً — كان فيها وفي شارةٍ بجوارها.
            "date_label": date_label,
            "teacher_subtitle": f"{request.user.full_name} · {date_label}",
            "open_count": open_count,
            # ما بقي بلا إنهاءٍ ينبّه، والصفرُ أخضر.
            "open_tone": "orange" if open_count else "green",
            "sessions": sessions,
            # الإشغالُ والتعويضُ والتبديلُ تكتب `original_teacher`؛ فيُعرف الأوّلان بسجلّيهما.
            **SubstituteService.moved_marks(sessions),
            "selected_date": selected_date,
            "today": timezone.localdate(),
            "next_session": next_session,
            "user_role": request.user.get_role(),
            # الرصدُ لمشرف الجناح: المعلّمُ يرى «عرض الحضور» لا «تسجيل».
            "is_recorder": is_recorder(request.user),
            "is_leader": is_leader,
            "teacher_filter": teacher_filter,
            "class_filter": class_filter,
            "status_filter": status_filter,
            "period_filter": period_filter,
            "show_all": show_all,
            "all_count": all_count,
            "completed_count": completed_count,
            "filter_teachers": filter_teachers,
            "filter_classes": filter_classes,
        },
    )


@login_required
@capability_required("attendance.mark")
def attendance_view(request, session_id):
    """رابطُ حصّةٍ قديم: يفتح جدولَ شعبتها بتاريخها — الجدولُ هو واجهةُ الرصد الوحيدة (أمرُ المالك 2026-10-09)."""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    target = class_grid.redirect_target(request.user, session)
    if target is None:
        return HttpResponse("<p dir='rtl'>غير مسموح — هذه الحصة ليست لك.</p>", status=403)
    return redirect(target)


@login_required
@capability_required("operations.daily_absence")
def daily_report(request):
    """غيابُ اليوم — طالبٌ في سطرٍ لأيّ تاريخ، ووسمُ الوزارة لمن غاب الأولى والثانية.

    حلّ محلَّ «سجلّات الحضور والغياب» (قرارُ 2026-09-13)، وبقي اسمُ المسار كما هو
    كي لا ينكسر رابطٌ محفوظ. والمنسّقُ لقسمه كما كان، والمشرفُ لطلبة جناحه بقيدهم
    الجاري (قرارُ 2026-09-15) — لا بشعبة الحصّة ولا بمعلّمها.
    """
    from core.permissions import get_department_teacher_ids
    from operations.daily_absence import daily_report as build
    from wings.scope import student_scope_for

    school = request.user.get_school()
    try:
        report_date = date.fromisoformat(request.GET.get("date") or "")
    except ValueError:
        report_date = timezone.localdate()
    ScheduleService.ensure_sessions_for_date(school, report_date)

    scope = student_scope_for(request)
    report = build(
        school,
        report_date,
        teacher_ids=get_department_teacher_ids(request.user),
        student_ids=scope.student_ids() if scope.is_wing_bound else None,
    )
    subtitle = f"{school.name} · {date_format(report_date, 'l d/m/Y')}"
    if scope.is_wing_bound:
        subtitle = f"{subtitle} · طلبةُ جناحك"
    return render(
        request,
        "operations/daily_absence.html",
        {
            "report": report,
            "subtitle": subtitle,
        },
    )
