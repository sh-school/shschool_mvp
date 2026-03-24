"""
exam_control/views.py  ·  SchoolOS v5
لوحة رئيس الكنترول — تشكيل + إدارة + محاضر + PDF
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    ExamGradeSheet,
    ExamIncident,
    ExamRoom,
    ExamSchedule,
    ExamSession,
    ExamSupervisor,
)


def _can_access(user):
    return user.is_authenticated and (
        user.is_admin()
        or user.is_superuser
        or user.get_role() in ("exam_head", "warden", "principal")
    )


@login_required
def dashboard(request):
    """لوحة القيادة — ملخص كل دورات الاختبار"""
    school = request.user.get_school()
    sessions = (
        ExamSession.objects.filter(school=school)
        .annotate(
            incident_count=Count("incidents"),
            pending_sheets=Count(
                "schedules__grade_sheets", filter=Q(schedules__grade_sheets__status="pending")
            ),
        )
        .order_by("-start_date")
    )
    return render(request, "exam_control/dashboard.html", {"sessions": sessions, "school": school})


@login_required
def session_create(request):
    """إنشاء دورة اختبار جديدة"""
    if not _can_access(request.user):
        return HttpResponseForbidden("غير مسموح")
    if request.method == "POST":
        school = request.user.get_school()
        session = ExamSession.objects.create(
            school=school,
            name=request.POST["name"],
            session_type=request.POST.get("session_type", "final"),
            academic_year=request.POST.get("academic_year", settings.CURRENT_ACADEMIC_YEAR),
            start_date=request.POST["start_date"],
            end_date=request.POST["end_date"],
            created_by=request.user,
        )
        return redirect("exam_control:session_detail", pk=session.pk)
    return render(
        request,
        "exam_control/session_form.html",
        {
            "session_types": ExamSession.SESSION_TYPES,
        },
    )


@login_required
def session_detail(request, pk):
    """تفاصيل دورة الاختبار"""
    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    context = {
        "session": session,
        "rooms": session.rooms.all(),
        "supervisors": session.supervisors.select_related("staff", "room"),
        "schedules": session.schedules.select_related("room", "session").order_by("exam_date", "start_time"),
        "incidents": session.incidents.filter(status="open").count(),
        "pending_sheets": ExamGradeSheet.objects.filter(
            schedule__session=session, status="pending"
        ).count(),
    }
    return render(request, "exam_control/session_detail.html", context)


@login_required
def supervisors(request, pk):
    """تشكيل الكنترول — المحور 1"""
    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    if request.method == "POST":
        from core.models import CustomUser

        staff_id = request.POST.get("staff_id")
        role = request.POST.get("role", "supervisor")
        room_id = request.POST.get("room_id") or None
        staff = get_object_or_404(CustomUser, id=staff_id)
        room = session.rooms.filter(id=room_id).first() if room_id else None
        ExamSupervisor.objects.update_or_create(
            session=session, staff=staff, defaults={"role": role, "room": room}
        )
        return redirect("exam_control:supervisors", pk=pk)

    from core.models import Membership

    staff_list = Membership.objects.filter(school=school, is_active=True).select_related("user")
    context = {
        "session": session,
        "supervisors": session.supervisors.select_related("staff", "room").order_by("role"),
        "staff_list": staff_list,
        "rooms": session.rooms.all(),
        "roles": ExamSupervisor.ROLES,
    }
    return render(request, "exam_control/supervisors.html", context)


@login_required
def schedule(request, pk):
    """جدول الاختبارات"""
    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    if request.method == "POST":
        room = get_object_or_404(ExamRoom, id=request.POST["room_id"], session=session)
        sched = ExamSchedule.objects.create(
            session=session,
            room=room,
            subject=request.POST["subject"],
            grade_level=request.POST["grade_level"],
            exam_date=request.POST["exam_date"],
            start_time=request.POST["start_time"],
            end_time=request.POST["end_time"],
            students_count=request.POST.get("students_count", 0),
        )
        # إنشاء ورقة رصد تلقائياً
        ExamGradeSheet.objects.create(schedule=sched, papers_count=sched.students_count)
        return redirect("exam_control:schedule", pk=pk)

    context = {
        "session": session,
        "schedules": session.schedules.select_related("room").order_by("exam_date", "start_time"),
        "rooms": session.rooms.all(),
    }
    return render(request, "exam_control/schedule.html", context)


@login_required
def incidents(request, pk):
    """قائمة حوادث الاختبار"""
    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    qs = session.incidents.select_related("student", "room", "reported_by").order_by(
        "-incident_time"
    )
    return render(request, "exam_control/incidents.html", {"session": session, "incidents": qs})


@login_required
def incident_add(request, pk):
    """تسجيل حادث جديد — محضر رسمي (الأقسام أ–ز من Template_IncidentReport)"""
    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    if request.method == "POST":
        from core.models import CustomUser

        student_id = request.POST.get("student_id") or None
        student = CustomUser.objects.filter(id=student_id).first() if student_id else None
        room_id = request.POST.get("room_id") or None
        room = session.rooms.filter(id=room_id).first()
        incident = ExamIncident.objects.create(
            session=session,
            room=room,
            student=student,
            reported_by=request.user,
            incident_type=request.POST.get("incident_type", "other"),
            severity=request.POST.get("severity", 1),
            description=request.POST["description"],
            injuries=request.POST.get("injuries", ""),
            action_taken=request.POST.get("action_taken", ""),
            attachments=request.POST.get("attachments", ""),
            recommendations=request.POST.get("recommendations", ""),
        )
        # إذا كانت الحادثة غشاً → ربط بسلوك الطالب تلقائياً
        if incident.incident_type == "cheating" and student:
            from behavior.models import BehaviorInfraction, ViolationCategory

            cat = ViolationCategory.objects.filter(code="D4").first()
            infraction = BehaviorInfraction.objects.create(
                school=school,
                student=student,
                reported_by=request.user,
                violation_category=cat,
                level=4,
                description=f"غش في اختبار: {incident.description[:200]}",
                action_taken=incident.action_taken,
            )
            incident.behavior_link = infraction
            incident.save(update_fields=["behavior_link"])

        return redirect("exam_control:incident_pdf", pk=incident.pk)

    from core.models import StudentEnrollment

    students = StudentEnrollment.objects.filter(
        class_group__school=school, class_group__academic_year=session.academic_year, is_active=True
    ).select_related("student")
    context = {
        "session": session,
        "rooms": session.rooms.all(),
        "incident_types": ExamIncident.TYPES,
        "severity_choices": ExamIncident.SEVERITY,
        "students": students,
    }
    return render(request, "exam_control/incident_form.html", context)


@login_required
def incident_pdf(request, pk):
    """توليد PDF لمحضر الحادثة (الأقسام أ–ز)"""
    from django.template.loader import render_to_string

    from core.pdf_utils import render_pdf

    incident = get_object_or_404(ExamIncident, pk=pk, session__school=request.user.get_school())
    html_str = render_to_string(
        "exam_control/pdf/incident_report.html",
        {
            "incident": incident,
            "generated_at": timezone.now(),
            "generated_by": request.user,
        },
    )
    return render_pdf(html_str, f"incident_{incident.pk}.pdf")


@login_required
def grade_sheets(request, pk):
    """إدارة أوراق الرصد والتصحيح"""
    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    if request.method == "POST":
        sheet_id = request.POST.get("sheet_id")
        new_status = request.POST.get("status")
        if sheet_id and new_status:
            sheet = get_object_or_404(ExamGradeSheet, id=sheet_id, schedule__session=session)
            sheet.status = new_status
            if new_status == "submitted":
                sheet.submitted_at = timezone.now()
            sheet.save(update_fields=["status", "submitted_at"])
        return redirect("exam_control:grade_sheets", pk=pk)

    sheets = (
        ExamGradeSheet.objects.filter(schedule__session=session)
        .select_related("schedule__room", "grader")
        .order_by("schedule__exam_date")
    )
    context = {"session": session, "sheets": sheets, "STATUS": ExamGradeSheet.STATUS}
    return render(request, "exam_control/grade_sheets.html", context)


@login_required
def session_report_pdf(request, pk):
    """تقرير PDF شامل للدورة (ملخص + حوادث + رصد)"""
    from django.template.loader import render_to_string

    from core.pdf_utils import render_pdf

    school = request.user.get_school()
    session = get_object_or_404(ExamSession, pk=pk, school=school)
    html_str = render_to_string(
        "exam_control/pdf/session_report.html",
        {
            "session": session,
            "supervisors": session.supervisors.select_related("staff", "room"),
            "schedules": session.schedules.select_related("room").order_by("exam_date"),
            "incidents": session.incidents.select_related("student", "room").order_by(
                "incident_time"
            ),
            "sheets": ExamGradeSheet.objects.filter(schedule__session=session).select_related(
                "schedule"
            ),
            "generated_at": timezone.now(),
            "generated_by": request.user,
        },
    )
    return render_pdf(html_str, f"exam_session_{session.pk}.pdf")
