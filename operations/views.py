from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import StudentEnrollment

from .models import Session, StudentAttendance, Subject
from .services import AttendanceService


@login_required
def schedule(request):
    """جدول حصص المعلم اليوم"""
    school = request.user.get_school()
    today = request.GET.get("date", timezone.now().date().isoformat())

    from datetime import date

    try:
        selected_date = date.fromisoformat(today)
    except ValueError:
        selected_date = timezone.now().date()

    sessions = (
        Session.objects.filter(
            school=school,
            teacher=request.user,
            date=selected_date,
        )
        .select_related("class_group", "subject")
        .order_by("start_time")
    )

    now = timezone.now().time()
    next_session = None
    for s in sessions:
        if s.start_time >= now and s.status == "scheduled":
            next_session = s
            break

    return render(
        request,
        "teacher/schedule.html",
        {
            "sessions": sessions,
            "selected_date": selected_date,
            "today": timezone.now().date(),
            "next_session": next_session,
        },
    )


@login_required
def attendance_view(request, session_id):
    """صفحة تسجيل الحضور لحصة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    # Only session teacher or admin
    if request.user != session.teacher and not request.user.is_admin():
        return HttpResponse("<p dir='rtl'>غير مسموح — هذه الحصة ليست لك.</p>", status=403)

    enrollments = (
        StudentEnrollment.objects.filter(class_group=session.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    # Get existing attendance
    existing = {att.student_id: att for att in StudentAttendance.objects.filter(session=session)}

    students_data = []
    for e in enrollments:
        att = existing.get(e.student.id)
        students_data.append(
            {
                "student": e.student,
                "attendance": att,
                "status": att.status if att else "present",
            }
        )

    summary = AttendanceService.get_session_summary(session)
    view_mode = request.GET.get("view", "list")  # list | grid

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
        },
    )


@login_required
@require_POST
def mark_single(request, session_id):
    """HTMX: تسجيل حضور طالب واحد"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    from core.models import CustomUser

    student_id = request.POST.get("student_id")
    status = request.POST.get("status", "present")
    excuse_type = request.POST.get("excuse_type", "")
    excuse_notes = request.POST.get("excuse_notes", "")

    if status not in ("present", "absent", "late", "excused"):
        return HttpResponse("حالة غير صالحة", status=400)

    student = get_object_or_404(CustomUser, id=student_id)

    att, created = AttendanceService.mark_attendance(
        session=session,
        student=student,
        status=status,
        excuse_type=excuse_type,
        excuse_notes=excuse_notes,
        marked_by=request.user,
    )

    summary = AttendanceService.get_session_summary(session)

    # Grid mode: أعد خلية الشبكة بدلاً من الصف
    view_mode = request.POST.get("view", "list")
    partial_template = (
        "teacher/partials/grid_cell.html" if view_mode == "grid"
        else "teacher/partials/student_row.html"
    )

    return render(
        request,
        partial_template,
        {
            "student": student,
            "attendance": att,
            "status": att.status,
            "session": session,
            "summary": summary,
        },
    )


@login_required
@require_POST
def mark_all_present(request, session_id):
    """HTMX: الكل حاضر بضغطة واحدة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)

    if request.user != session.teacher and not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    count = AttendanceService.bulk_mark_all_present(session, marked_by=request.user)
    return redirect("attendance", session_id=session_id)


@login_required
@require_POST
def complete_session(request, session_id):
    """إنهاء الحصة"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    AttendanceService.complete_session(session)
    messages.success(
        request, f"تم إنهاء الحصة بنجاح. الحضور: {session.present_count}/{session.attendance_count}"
    )
    return redirect("teacher_schedule")


@login_required
def session_summary(request, session_id):
    """ملخص الحصة — HTMX partial"""
    school = request.user.get_school()
    session = get_object_or_404(Session, id=session_id, school=school)
    summary = AttendanceService.get_session_summary(session)
    return render(
        request, "teacher/partials/summary_widget.html", {"session": session, "summary": summary}
    )


# ── Director Views ──────────────────────────────────────
@login_required
def daily_report(request):
    """تقرير الغياب اليومي للمدير"""
    school = request.user.get_school()
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    from datetime import date

    selected = request.GET.get("date", timezone.now().date().isoformat())
    try:
        report_date = date.fromisoformat(selected)
    except ValueError:
        report_date = timezone.now().date()

    absences = (
        StudentAttendance.objects.filter(
            school=school,
            session__date=report_date,
            status__in=["absent", "late"],
        )
        .select_related("student", "session__class_group")
        .order_by("session__class_group__grade", "student__full_name")
    )

    sessions = Session.objects.filter(school=school, date=report_date)
    from django.db.models import Count

    summary = (
        StudentAttendance.objects.filter(school=school, session__date=report_date)
        .values("status")
        .annotate(count=Count("id"))
    )

    stats = {s["status"]: s["count"] for s in summary}
    total = sum(stats.values())
    present_pct = round(stats.get("present", 0) / total * 100) if total else 0

    return render(
        request,
        "admin/daily_report.html",
        {
            "absences": absences,
            "report_date": report_date,
            "sessions": sessions,
            "stats": stats,
            "total": total,
            "present_pct": present_pct,
        },
    )


# ══════════════════════════════════════════════════════
# المرحلة 2 — الجداول الذكية + نظام البديل
# ══════════════════════════════════════════════════════

from core.models import CustomUser, Membership

from .models import ScheduleSlot, SubstituteAssignment, TeacherAbsence
from .services import ScheduleService, SubstituteService

# ── الجدول الأسبوعي ──────────────────────────────────


@login_required
def weekly_schedule(request):
    """عرض الجدول الأسبوعي — للمعلم أو كل المعلمين للمدير"""
    school = request.user.get_school()
    user = request.user

    teacher_id = request.GET.get("teacher")
    class_id = request.GET.get("class")
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    target_teacher = None
    if teacher_id:
        target_teacher = get_object_or_404(CustomUser, id=teacher_id)
    elif user.is_teacher() and not user.is_admin():
        target_teacher = user

    target_class = None
    if class_id:
        from core.models import ClassGroup

        target_class = get_object_or_404(ClassGroup, id=class_id, school=school)

    grid = ScheduleService.get_weekly_schedule(school, target_teacher, target_class, year)
    conflicts = ScheduleService.detect_conflicts(school, year) if user.is_admin() else []

    DAYS = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    PERIODS = range(1, 9)

    teachers = []
    classes = []
    if user.is_admin():
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
        from core.models import ClassGroup

        classes = ClassGroup.objects.filter(school=school, is_active=True).order_by(
            "grade", "section"
        )

    return render(
        request,
        "schedule/weekly.html",
        {
            "grid": grid,
            "days": DAYS,
            "periods": PERIODS,
            "conflicts": conflicts,
            "target_teacher": target_teacher,
            "target_class": target_class,
            "teachers": teachers,
            "classes": classes,
            "academic_year": year,
        },
    )


@login_required
def schedule_slot_create(request):
    """إضافة حصة جديدة للجدول — POST"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()

    if request.method == "POST":
        from core.models import ClassGroup

        try:
            slot = ScheduleSlot.objects.create(
                school=school,
                teacher_id=request.POST["teacher"],
                class_group_id=request.POST["class_group"],
                subject_id=request.POST.get("subject") or None,
                day_of_week=int(request.POST["day_of_week"]),
                period_number=int(request.POST["period_number"]),
                start_time=request.POST["start_time"],
                end_time=request.POST["end_time"],
                academic_year=request.POST.get("academic_year", settings.CURRENT_ACADEMIC_YEAR),
            )
            messages.success(request, f"تمت إضافة الحصة: {slot}")
        except Exception as e:
            messages.error(request, f"خطأ: {e}")
        return redirect("weekly_schedule")

    # GET → form
    teacher_ids = Membership.objects.filter(
        school=school, is_active=True, role__name__in=("teacher", "coordinator")
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
    from core.models import ClassGroup

    classes = ClassGroup.objects.filter(school=school, is_active=True).order_by("grade", "section")
    subjects = Subject.objects.filter(school=school).order_by("name_ar")
    DAYS = ScheduleSlot.DAYS
    return render(
        request,
        "schedule/slot_form.html",
        {
            "teachers": teachers,
            "classes": classes,
            "subjects": subjects,
            "days": DAYS,
        },
    )


@login_required
def schedule_slot_delete(request, slot_id):
    """حذف حصة من الجدول"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()
    slot = get_object_or_404(ScheduleSlot, id=slot_id, school=school)
    slot.is_active = False
    slot.save(update_fields=["is_active"])
    messages.success(request, "تم حذف الحصة من الجدول")
    return redirect("weekly_schedule")


@login_required
def generate_sessions(request):
    """توليد حصص يومية من الجدول — للمدير"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    if request.method == "POST":
        from datetime import date as dclass

        school = request.user.get_school()
        raw = request.POST.get("date", timezone.now().date().isoformat())
        try:
            gen_date = dclass.fromisoformat(raw)
        except ValueError:
            gen_date = timezone.now().date()
        count = ScheduleService.generate_daily_sessions(school, gen_date)
        messages.success(request, f"تم توليد {count} حصة ليوم {gen_date}")
        return redirect("weekly_schedule")
    return render(request, "schedule/generate_form.html", {"today": timezone.now().date()})


# ── نظام البديل ──────────────────────────────────────


@login_required
def teacher_absence_list(request):
    """قائمة غيابات المعلمين — للمدير"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()
    from datetime import date as dclass

    selected = request.GET.get("date", timezone.now().date().isoformat())
    try:
        abs_date = dclass.fromisoformat(selected)
    except ValueError:
        abs_date = timezone.now().date()

    absences = (
        TeacherAbsence.objects.filter(school=school, date=abs_date)
        .select_related("teacher", "reported_by")
        .prefetch_related("assignments__substitute")
    )

    return render(
        request,
        "substitute/absence_list.html",
        {
            "absences": absences,
            "abs_date": abs_date,
        },
    )


@login_required
def register_teacher_absence(request):
    """تسجيل غياب معلم"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()

    if request.method == "POST":
        from datetime import date as dclass

        teacher = get_object_or_404(
            CustomUser, id=request.POST["teacher"], memberships__school=school
        )
        raw_date = request.POST.get("date", timezone.now().date().isoformat())
        try:
            abs_date = dclass.fromisoformat(raw_date)
        except ValueError:
            abs_date = timezone.now().date()
        reason = request.POST.get("reason", "other")
        reason_notes = request.POST.get("reason_notes", "")
        absence = SubstituteService.register_absence(
            school, teacher, abs_date, reason, reason_notes, reported_by=request.user
        )
        messages.success(request, f"تم تسجيل غياب {teacher.full_name} بتاريخ {abs_date}")
        return redirect("absence_detail", absence_id=absence.id)

    teacher_ids = Membership.objects.filter(
        school=school, is_active=True, role__name__in=("teacher", "coordinator")
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
    return render(
        request,
        "substitute/register_absence.html",
        {
            "teachers": teachers,
            "reasons": TeacherAbsence.REASON,
            "today": timezone.now().date(),
        },
    )


@login_required
def absence_detail(request, absence_id):
    """تفاصيل الغياب + تعيين البدلاء"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()
    absence = get_object_or_404(TeacherAbsence, id=absence_id, school=school)

    our_day = SubstituteService._date_to_day(absence.date)
    slots = ScheduleSlot.objects.filter(
        school=school, teacher=absence.teacher, day_of_week=our_day, is_active=True
    ).select_related("class_group", "subject")

    # للكل حصة: هل يوجد بديل؟
    assignments = {
        a.slot_id: a
        for a in SubstituteAssignment.objects.filter(absence=absence).select_related("substitute")
    }

    slots_data = []
    for slot in slots:
        assignment = assignments.get(slot.id)
        available = SubstituteService.get_available_teachers(
            school,
            absence.date,
            slot.day_of_week,
            slot.period_number,
            exclude_teacher=absence.teacher,
        )
        slots_data.append({"slot": slot, "assignment": assignment, "available": available})

    return render(
        request,
        "substitute/absence_detail.html",
        {
            "absence": absence,
            "slots_data": slots_data,
        },
    )


@login_required
@require_POST
def assign_substitute(request, absence_id, slot_id):
    """HTMX: تعيين بديل لحصة"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()
    absence = get_object_or_404(TeacherAbsence, id=absence_id, school=school)
    slot = get_object_or_404(ScheduleSlot, id=slot_id, school=school)
    substitute = get_object_or_404(CustomUser, id=request.POST["substitute"])

    assignment = SubstituteService.assign_substitute(
        absence, slot, substitute, assigned_by=request.user, notes=request.POST.get("notes", "")
    )
    available = SubstituteService.get_available_teachers(
        school, absence.date, slot.day_of_week, slot.period_number, exclude_teacher=absence.teacher
    )
    return render(
        request,
        "substitute/partials/slot_card.html",
        {
            "slot": slot,
            "assignment": assignment,
            "available": available,
            "absence": absence,
        },
    )


@login_required
def substitute_report(request):
    """تقرير الحصص البديلة"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)
    school = request.user.get_school()
    from datetime import date as dclass
    from datetime import timedelta

    today = timezone.now().date()
    date_from = dclass.fromisoformat(
        request.GET.get("from", (today - timedelta(days=7)).isoformat())
    )
    date_to = dclass.fromisoformat(request.GET.get("to", today.isoformat()))

    assignments = SubstituteService.get_substitute_report(school, date_from, date_to)

    # ملخص: كم حصة لكل بديل
    summary = {}
    for a in assignments:
        name = a.substitute.full_name
        summary[name] = summary.get(name, 0) + 1

    return render(
        request,
        "substitute/report.html",
        {
            "assignments": assignments,
            "summary": sorted(summary.items(), key=lambda x: -x[1]),
            "date_from": date_from,
            "date_to": date_to,
        },
    )
