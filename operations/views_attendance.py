"""operations/views_attendance.py — views الحضور والحصص اليومية."""

import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required
from core.models import StudentEnrollment

from .day_attendance import can_record, is_recorder, recorded_by_supervisor
from .models import Session, StudentAttendance
from .services import AttendanceService, ScheduleService, SubstituteService

logger = logging.getLogger(__name__)

#: لونُ شارة الحضور وحدِّ خليّته — ربطٌ مغلق: حالةٌ لا يعرفها يأخذ الرماديّ.
#: كان القالبُ يكتب `status-{{ status }}` فتصير الحالةُ اسمَ صنفٍ لا تعريفَ له
#: (`status-present`، `status-unmarked`)، ويكتب المعذورَ `status-purple` غيرَ المعرَّف.
ATTENDANCE_TONES = {
    "present": "success",
    "absent": "danger",
    "late": "warning",
    "excused": "info",
}


def attendance_tone(status: str) -> str:
    return ATTENDANCE_TONES.get(status, "gray")


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

    now = timezone.now().time()
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


def _session_heading(session) -> dict:
    """عنوانُ صفحة الحضور وسطرُها — نصٌّ مركّبٌ يُبنى هنا لا في الترويسة."""
    subject = (session.subject.name_ar if session.subject else "") or "حصة"
    return {
        "page_title": f"{subject} — {session.class_group}",
        "session_label": f"{session.date:%d/%m/%Y} · {session.start_time:%H:%M}",
    }


@login_required
@capability_required("attendance.mark")
def attendance_view(request, session_id):
    """صفحة تسجيل الحضور لحصة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    if (
        request.user != session.teacher
        and not request.user.is_admin()
        and not request.user.is_leadership()
    ):
        return HttpResponse("<p dir='rtl'>غير مسموح — هذه الحصة ليست لك.</p>", status=403)

    enrollments = (
        StudentEnrollment.objects.filter(class_group=session.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )
    existing = {
        att.student_id: att
        for att in StudentAttendance.objects.filter(session=session).select_related("student")
    }
    students_data = [
        {
            "student": e.student,
            "attendance": existing.get(e.student.id),
            "status": existing.get(e.student.id).status
            if existing.get(e.student.id)
            else "present",
        }
        for e in enrollments
    ]
    for row in students_data:
        row["tone"] = attendance_tone(row["status"])
    summary = AttendanceService.get_session_summary(session)
    from .class_exit import exits_of_session

    exits = exits_of_session(session)
    if not can_record(request.user, session):
        # اطّلاعٌ لا رصد: يرى المعلّمُ ما رصده مشرفُ الجناح، ولا زرَّ يكتب —
        # إلّا نقرةَ «دخل متأخّراً» لصاحب الحصّة (قرارُ 2026-09-13).
        return render(
            request,
            "teacher/attendance_readonly.html",
            {
                "session": session,
                "can_tap_late": request.user == session.teacher,
                "exits": exits,
                "out_now": sum(1 for cur, _ in exits.values() if cur is not None),
                "students_data": [
                    {
                        **row,
                        "status": row["status"] if row["attendance"] else "unmarked",
                        "tap_minutes": (
                            row["attendance"].late_minutes
                            if row["attendance"] and row["attendance"].source == "teacher_late"
                            else None
                        ),
                        "exit": exits.get(row["student"].id, (None, []))[0],
                        "exit_count": len(exits.get(row["student"].id, (None, []))[1]),
                    }
                    for row in students_data
                ],
                "summary": summary,
                "recorded": bool(existing),
                **_session_heading(session),
            },
        )
    view_mode = request.GET.get("view", "list")
    template = "teacher/attendance_grid.html" if view_mode == "grid" else "teacher/attendance.html"

    return render(
        request,
        template,
        {
            "session": session,
            "students_data": students_data,
            "summary": summary,
            "existing_count": len(existing),
            "view_mode": view_mode,
            **_session_heading(session),
        },
    )


@login_required
@capability_required("attendance.mark")
@require_POST
def mark_single(request, session_id):
    """HTMX: تسجيل حضور طالب واحد

    المقيَّدُ بجناحه لا يرصد إلّا حصّةَ شعبةٍ من شُعب جناحه، وما عداها 404 (قرارُ
    2026-09-15). والطالبُ من قيد شعبة الحصّة لكلّ من يرصد — لا أيُّ حسابٍ في المنصّة.
    """
    from core.models import CustomUser
    from wings.scope import student_scope_for

    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    student_scope_for(request).require_class(session.class_group_id)
    student_id = request.POST.get("student_id")
    status = request.POST.get("status", "present")
    excuse_type = request.POST.get("excuse_type", "")
    excuse_notes = request.POST.get("excuse_notes", "")

    if status not in ("present", "absent", "late", "excused"):
        return HttpResponse("حالة غير صالحة", status=400)

    student = get_object_or_404(
        CustomUser,
        id=student_id,
        enrollments__class_group=session.class_group,
        enrollments__is_active=True,
    )
    # الرصدُ لمشرف الجناح (قرارُ المدير) — والمعلّمُ لا يرصد في شُعب الأجنحة،
    # وما رصده المشرفُ لا يُكتب فوقه إلّا من أهل الرصد.
    if not can_record(request.user, session) or (
        not is_recorder(request.user) and recorded_by_supervisor(session, student)
    ):
        return HttpResponse("الرصدُ لمشرف الجناح.", status=403)
    att, _ = AttendanceService.mark_attendance(
        session=session,
        student=student,
        status=status,
        excuse_type=excuse_type,
        excuse_notes=excuse_notes,
        marked_by=request.user,
    )
    summary = AttendanceService.get_session_summary(session)
    view_mode = request.POST.get("view", "list")
    partial_template = (
        "teacher/partials/grid_cell.html"
        if view_mode == "grid"
        else "teacher/partials/student_row.html"
    )
    return render(
        request,
        partial_template,
        {
            "student": student,
            "attendance": att,
            "status": att.status,
            "tone": attendance_tone(att.status),
            "session": session,
            "summary": summary,
        },
    )


@login_required
@capability_required("attendance.mark")
@require_POST
def mark_late_tap(request, session_id):
    """HTMX: نقرةُ المعلّم «دخل متأخّراً» — النظامُ يسجّل الوقت (قرارُ 2026-09-13).

    للمعلّم في شُعب الأجنحة حيث لا يرصد: المشرفُ يصل بعد بدء الحصّة فلا يرى من دخل
    قبله متأخّراً، والمعلّمُ يراه. النقرةُ لا تكتب فوق رصد المشرف.
    """
    from core.models import CustomUser

    from .period_register import tap_late

    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    if request.user != session.teacher and not request.user.is_leadership():
        return HttpResponse("هذه الحصّة ليست لك.", status=403)
    student = get_object_or_404(
        CustomUser,
        id=request.POST.get("student_id"),
        enrollments__class_group=session.class_group,
        enrollments__is_active=True,
    )
    minutes = tap_late(session, student, by=request.user)
    return render(
        request,
        "teacher/partials/late_tap.html",
        {"session": session, "student": student, "minutes": minutes, "tapped": True},
    )


def _own_session_or_403(request, session_id):
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    if request.user != session.teacher and not request.user.is_leadership():
        return session, HttpResponse("هذه الحصّة ليست لك.", status=403)
    return session, None


def _enrolled_student(request, session):
    from core.models import CustomUser

    return get_object_or_404(
        CustomUser,
        id=request.POST.get("student_id"),
        enrollments__class_group=session.class_group,
        enrollments__is_active=True,
    )


def _exit_cell(request, session, student):
    from .class_exit import open_exit

    return render(
        request,
        "teacher/partials/exit_tap.html",
        {"session": session, "student": student, "current": open_exit(session, student)},
    )


@login_required
@capability_required("attendance.mark")
@require_POST
def mark_exit(request, session_id):
    """HTMX: نقرةُ «خرج بإذن» — بوجهةٍ، والنظامُ يسجّل لحظتَها (قرارُ 2026-09-13)."""
    from .class_exit import leave

    session, denied = _own_session_or_403(request, session_id)
    if denied:
        return denied
    student = _enrolled_student(request, session)
    leave(session, student, request.POST.get("destination", "restroom"), by=request.user)
    return _exit_cell(request, session, student)


@login_required
@capability_required("attendance.mark")
@require_POST
def mark_return(request, session_id):
    """HTMX: نقرةُ «عاد» — تُغلق الخروجَ بلحظتها."""
    from .class_exit import come_back

    session, denied = _own_session_or_403(request, session_id)
    if denied:
        return denied
    student = _enrolled_student(request, session)
    come_back(session, student, by=request.user)
    return _exit_cell(request, session, student)


@login_required
@capability_required("attendance.mark")
@require_POST
def undo_late_tap_view(request, session_id):
    """HTMX: تراجعُ المعلّم عن «دخل الآن» — نقرةٌ على طالبٍ آخر (ما لم يثبّت المشرف)."""
    from .undo import undo_late_tap

    session, denied = _own_session_or_403(request, session_id)
    if denied:
        return denied
    student = _enrolled_student(request, session)
    undo_late_tap(request, session, student)
    return render(
        request,
        "teacher/partials/late_tap.html",
        {"session": session, "student": student, "tapped": False},
    )


@login_required
@capability_required("attendance.mark")
@require_POST
def cancel_exit_view(request, session_id):
    """HTMX: إلغاءُ «خرج بإذن» المفتوح — لا «عاد»: الإلغاءُ لا يترك دقائق."""
    from .undo import cancel_exit

    session, denied = _own_session_or_403(request, session_id)
    if denied:
        return denied
    student = _enrolled_student(request, session)
    cancel_exit(request, session, student)
    return _exit_cell(request, session, student)


@login_required
@capability_required("attendance.mark")
@require_POST
def mark_all_present(request, session_id):
    """HTMX: الكل حاضر بضغطة واحدة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    if request.user != session.teacher and not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    if not can_record(request.user, session):
        return HttpResponse("الرصدُ لمشرف الجناح.", status=403)

    AttendanceService.bulk_mark_all_present(session, marked_by=request.user)
    enrollments = (
        StudentEnrollment.objects.filter(class_group=session.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )
    existing = {
        a.student_id: a
        for a in StudentAttendance.objects.filter(session=session).select_related("student")
    }
    students_data = [
        {
            "student": e.student,
            "attendance": existing.get(e.student_id),
            "status": existing.get(e.student_id).status
            if existing.get(e.student_id)
            else "unmarked",
        }
        for e in enrollments
    ]
    for row in students_data:
        row["tone"] = attendance_tone(row["status"])
    summary = AttendanceService.get_session_summary(session)
    view_mode = request.POST.get("view", "list")
    partial_template = (
        "teacher/partials/grid_container.html"
        if view_mode == "grid"
        else "teacher/partials/students_list.html"
    )
    return render(
        request,
        partial_template,
        {"students_data": students_data, "session": session, "summary": summary},
    )


@login_required
@capability_required("attendance.mark")
@require_POST
def complete_session(request, session_id):
    """إنهاء الحصة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    AttendanceService.complete_session(session)
    messages.success(
        request,
        f"تم إنهاء الحصة بنجاح. الحضور: {session.present_count}/{session.attendance_count}",
    )
    return redirect("teacher_schedule")


@login_required
@capability_required("attendance.mark")
def session_summary(request, session_id):
    """ملخص الحصة — HTMX partial"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    summary = AttendanceService.get_session_summary(session)
    return render(
        request, "teacher/partials/summary_widget.html", {"session": session, "summary": summary}
    )


@login_required
@capability_required("operations.reports")
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
