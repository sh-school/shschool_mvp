"""operations/views_attendance.py — views الحضور والحصص اليومية."""

import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import StudentEnrollment
from core.permissions import role_required

from .models import Session, StudentAttendance
from .services import AttendanceService, ScheduleService

logger = logging.getLogger(__name__)

_REPORT_ROLES = {"principal", "vice_academic", "vice_admin", "coordinator", "admin_supervisor", "admin"}


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher",
               "ese_teacher", "academic_advisor", "admin_supervisor", "student", "parent")
def schedule(request):
    """جدول حصص المعلم اليوم"""
    school = request.user.get_school()
    today = request.GET.get("date", timezone.now().date().isoformat())
    try:
        selected_date = date.fromisoformat(today)
    except ValueError:
        selected_date = timezone.now().date()

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
        if teacher_filter:
            sessions = sessions.filter(teacher_id=teacher_filter)
        if class_filter:
            sessions = sessions.filter(class_group_id=class_filter)
        if status_filter:
            sessions = sessions.filter(status=status_filter)
        if period_filter:
            sessions = sessions.filter(period_number=period_filter)
    else:
        sessions = (
            Session.objects.filter(school=school, teacher=request.user, date=selected_date)
            .select_related("class_group", "subject")
            .order_by("start_time")
        )
        teacher_filter = class_filter = status_filter = period_filter = ""

    now = timezone.now().time()
    next_session = None
    for s in sessions:
        if s.start_time >= now and s.status == "scheduled":
            next_session = s
            break

    # ── بيانات الفلاتر (للقيادة فقط) ──
    filter_teachers = []
    filter_classes = []
    if is_leader:
        from core.models.access import Membership
        filter_teachers = (
            Membership.objects.filter(
                school=school, is_active=True, role__name__in=("teacher", "coordinator", "ese_teacher"),
            ).select_related("user").order_by("user__full_name")
        )
        from core.models.academic import ClassGroup
        filter_classes = (
            ClassGroup.objects.filter(school=school, is_active=True)
            .order_by("grade", "section")
        )

    return render(request, "teacher/schedule.html", {
        "sessions": sessions,
        "selected_date": selected_date,
        "today": timezone.now().date(),
        "next_session": next_session,
        "user_role": request.user.get_role(),
        "is_leader": is_leader,
        "teacher_filter": teacher_filter,
        "class_filter": class_filter,
        "status_filter": status_filter,
        "period_filter": period_filter,
        "filter_teachers": filter_teachers,
        "filter_classes": filter_classes,
    })


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator",
               "teacher", "ese_teacher", "admin_supervisor")
def attendance_view(request, session_id):
    """صفحة تسجيل الحضور لحصة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    if request.user != session.teacher and not request.user.is_admin() and not request.user.is_leadership():
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
        {"student": e.student, "attendance": existing.get(e.student.id),
         "status": existing.get(e.student.id).status if existing.get(e.student.id) else "present"}
        for e in enrollments
    ]
    summary = AttendanceService.get_session_summary(session)
    view_mode = request.GET.get("view", "list")
    template = "teacher/attendance_grid.html" if view_mode == "grid" else "teacher/attendance.html"

    return render(request, template, {
        "session": session,
        "students_data": students_data,
        "summary": summary,
        "existing_count": len(existing),
        "view_mode": view_mode,
    })


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator",
               "teacher", "ese_teacher", "admin_supervisor")
@require_POST
def mark_single(request, session_id):
    """HTMX: تسجيل حضور طالب واحد"""
    from core.models import CustomUser

    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    student_id = request.POST.get("student_id")
    status = request.POST.get("status", "present")
    excuse_type = request.POST.get("excuse_type", "")
    excuse_notes = request.POST.get("excuse_notes", "")

    if status not in ("present", "absent", "late", "excused"):
        return HttpResponse("حالة غير صالحة", status=400)

    student = get_object_or_404(CustomUser, id=student_id)
    att, _ = AttendanceService.mark_attendance(
        session=session, student=student, status=status,
        excuse_type=excuse_type, excuse_notes=excuse_notes, marked_by=request.user,
    )
    summary = AttendanceService.get_session_summary(session)
    view_mode = request.POST.get("view", "list")
    partial_template = (
        "teacher/partials/grid_cell.html" if view_mode == "grid"
        else "teacher/partials/student_row.html"
    )
    return render(request, partial_template, {
        "student": student, "attendance": att, "status": att.status,
        "session": session, "summary": summary,
    })


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator",
               "teacher", "ese_teacher", "admin_supervisor")
@require_POST
def mark_all_present(request, session_id):
    """HTMX: الكل حاضر بضغطة واحدة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    if request.user != session.teacher and not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    AttendanceService.bulk_mark_all_present(session, marked_by=request.user)
    enrollments = (
        StudentEnrollment.objects.filter(class_group=session.class_group, is_active=True)
        .select_related("student").order_by("student__full_name")
    )
    existing = {
        a.student_id: a
        for a in StudentAttendance.objects.filter(session=session).select_related("student")
    }
    students_data = [
        {"student": e.student, "attendance": existing.get(e.student_id),
         "status": existing.get(e.student_id).status if existing.get(e.student_id) else "unmarked"}
        for e in enrollments
    ]
    summary = AttendanceService.get_session_summary(session)
    view_mode = request.POST.get("view", "list")
    partial_template = (
        "teacher/partials/grid_container.html" if view_mode == "grid"
        else "teacher/partials/students_list.html"
    )
    return render(request, partial_template,
                  {"students_data": students_data, "session": session, "summary": summary})


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator",
               "teacher", "ese_teacher", "admin_supervisor")
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator",
               "teacher", "ese_teacher", "admin_supervisor")
def session_summary(request, session_id):
    """ملخص الحصة — HTMX partial"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    summary = AttendanceService.get_session_summary(session)
    return render(request, "teacher/partials/summary_widget.html",
                  {"session": session, "summary": summary})


@login_required
@role_required(_REPORT_ROLES)
def daily_report(request):
    """تقرير الغياب اليومي — للمدير والمنسق"""
    from django.db.models import Count

    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    selected = request.GET.get("date", timezone.now().date().isoformat())
    try:
        report_date = date.fromisoformat(selected)
    except ValueError:
        report_date = timezone.now().date()

    # ── تأكد من وجود حصص لتاريخ التقرير ──
    ScheduleService.ensure_sessions_for_date(school, report_date)

    absences = (
        StudentAttendance.objects.filter(
            school=school, session__date=report_date, status__in=["absent", "late"],
        )
        .select_related("student", "session__class_group")
        .order_by("session__class_group__grade", "student__full_name")
    )
    sessions = Session.objects.filter(school=school, date=report_date).select_related("teacher")

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        absences = absences.filter(session__teacher_id__in=dept_ids)
        sessions = sessions.filter(teacher_id__in=dept_ids)

    att_qs = StudentAttendance.objects.filter(school=school, session__date=report_date)
    if dept_ids is not None:
        att_qs = att_qs.filter(session__teacher_id__in=dept_ids)
    summary = att_qs.values("status").annotate(count=Count("id"))
    stats = {s["status"]: s["count"] for s in summary}
    total = sum(stats.values())
    present_pct = round(stats.get("present", 0) / total * 100) if total else 0

    return render(request, "admin/daily_report.html", {
        "absences": absences,
        "report_date": report_date,
        "sessions": sessions,
        "stats": stats,
        "total": total,
        "present_pct": present_pct,
    })
