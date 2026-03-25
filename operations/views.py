import logging

import django.db
from django.conf import settings
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import StudentEnrollment
from core.permissions import leadership_required, role_required

from .models import Session, StudentAttendance, Subject
from .services import AttendanceService


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher", "academic_advisor", "admin_supervisor", "student", "parent")
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
            "user_role": request.user.get_role(),
        },
    )


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher", "admin_supervisor")
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
    existing = {
        att.student_id: att
        for att in StudentAttendance.objects.filter(session=session).select_related("student")
    }

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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher", "admin_supervisor")
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
            "session": session,
            "summary": summary,
        },
    )


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher", "admin_supervisor")
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher", "admin_supervisor")
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
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher", "admin_supervisor")
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
@leadership_required
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

    sessions = Session.objects.filter(school=school, date=report_date).select_related("teacher")
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
    PERIODS = range(1, 8)  # 7 حصص يومياً

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
            "user_role": user.get_role(),
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
        except (ValueError, TypeError, django.db.IntegrityError) as e:
            logger.exception("فشل إضافة حصة في الجدول الأسبوعي: %s", e)
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


# ══════════════════════════════════════════════════════════════
# المرحلة 3 — الجدولة الذكية
# ══════════════════════════════════════════════════════════════


@login_required
def smart_schedule_view(request):
    """صفحة إدارة الجدولة الذكية — عرض التوزيعات + زر التوليد"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    from .models import ScheduleGeneration, SubjectClassAssignment

    assignments = (
        SubjectClassAssignment.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("class_group", "subject", "teacher")
        .order_by("class_group__grade", "class_group__section", "subject__name_ar")
    )

    generations = ScheduleGeneration.objects.filter(school=school, academic_year=year)[:5]

    total_weekly = sum(a.weekly_periods for a in assignments)
    classes_count = assignments.values("class_group").distinct().count()
    teachers_count = assignments.values("teacher").distinct().count()

    return render(
        request,
        "schedule/smart_schedule.html",
        {
            "assignments": assignments,
            "generations": generations,
            "year": year,
            "total_weekly": total_weekly,
            "classes_count": classes_count,
            "teachers_count": teachers_count,
        },
    )


@login_required
@require_POST
def smart_generate(request):
    """توليد الجدول الذكي — POST فقط"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.POST.get("year", settings.CURRENT_ACADEMIC_YEAR)

    from .scheduler import generate_schedule

    result = generate_schedule(school, year, user=request.user)

    if result["success"]:
        messages.success(
            request,
            f"تم توليد الجدول بنجاح! الجودة: {result['quality']['score']}% — "
            f"{result['quality']['total_slots']} حصة في {result['elapsed_ms']}ms",
        )
    else:
        for err in result["errors"][:5]:
            messages.warning(request, err)
        quality = result.get("quality")
        if quality and quality.get("total_slots", 0) > 0:
            messages.info(
                request,
                f"تم توليد {quality['total_slots']} حصة (جودة: {quality['score']}%) "
                f"مع {len(result['errors'])} تعذّر",
            )

    return redirect("smart_schedule")


@login_required
def teacher_load_report(request):
    """تقرير أحمال المعلمين — عدد الحصص والعدالة"""
    if not request.user.is_admin():
        return HttpResponse("غير مسموح", status=403)

    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    from collections import Counter

    from core.models import CustomUser, Membership

    from .models import ScheduleSlot, SubstituteAssignment

    # معلمو المدرسة
    teacher_ids = Membership.objects.filter(
        school=school, is_active=True, role__name__in=("teacher", "coordinator")
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    # حصص كل معلم
    slot_counts = Counter(
        ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True).values_list(
            "teacher_id", flat=True
        )
    )

    # بدائل كل معلم (هذا الشهر)
    from datetime import date

    month_start = date.today().replace(day=1)
    sub_counts = Counter(
        SubstituteAssignment.objects.filter(
            school=school, absence__date__gte=month_start
        ).values_list("substitute_id", flat=True)
    )

    # حصص يومية (max/min/avg)
    daily_counts = {}
    for slot in ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True):
        key = (str(slot.teacher_id), slot.day_of_week)
        daily_counts[key] = daily_counts.get(key, 0) + 1

    teacher_data = []
    for t in teachers:
        tid = str(t.id)
        weekly = slot_counts.get(t.id, 0)
        subs = sub_counts.get(t.id, 0)
        days = [daily_counts.get((tid, d), 0) for d in range(5)]
        max_daily = max(days) if days else 0
        min_daily = min(d for d in days if d > 0) if any(d > 0 for d in days) else 0
        free_days = sum(1 for d in days if d == 0)

        teacher_data.append(
            {
                "teacher": t,
                "weekly": weekly,
                "subs": subs,
                "max_daily": max_daily,
                "min_daily": min_daily,
                "free_days": free_days,
                "days": days,
            }
        )

    # ترتيب حسب الحمل الأعلى
    teacher_data.sort(key=lambda x: -x["weekly"])

    avg_weekly = sum(d["weekly"] for d in teacher_data) / len(teacher_data) if teacher_data else 0

    return render(
        request,
        "schedule/teacher_load.html",
        {
            "teacher_data": teacher_data,
            "year": year,
            "avg_weekly": round(avg_weekly, 1),
            "total_teachers": len(teacher_data),
        },
    )


# ═════════════════════════════════════════════════════════════════════
# المرحلة 6 — views التبديل والتعويض
# ═════════════════════════════════════════════════════════════════════

from core.permissions import (
    coordinator_required,
    leadership_required,
    permission_required,
    role_required,
    schedule_view_required,
    SCHEDULE_MANAGE,
    SCHEDULE_SWAP_REQUEST,
    SCHEDULE_SWAP_APPROVE,
    SCHEDULE_VIEW,
)
from .models import (
    CompensatorySession,
    FreeSlotRegistry,
    ScheduleSlot,
    TeacherAbsence,
    TeacherSwap,
)
from .services import CompensatoryService, FreeSlotService, SwapService


# ── قائمة طلبات التبديل ─────────────────────────────────────────

@login_required
@role_required(SCHEDULE_VIEW)
def swap_list(request):
    """قائمة طلبات التبديل — مفلترة حسب الدور."""
    school = request.user.get_school()
    role = request.user.get_role()

    if role in ("principal", "vice_academic", "vice_admin"):
        # القيادة ترى الكل
        swaps = TeacherSwap.objects.filter(school=school)
    elif role == "coordinator":
        # المنسق يرى طلبات تخصصه
        dept = request.user.department
        from core.models import Membership
        dept_teachers = Membership.objects.filter(
            school=school, is_active=True, department=dept,
        ).values_list("user_id", flat=True)
        swaps = TeacherSwap.objects.filter(
            school=school,
        ).filter(
            django.db.models.Q(teacher_a_id__in=dept_teachers) |
            django.db.models.Q(teacher_b_id__in=dept_teachers)
        )
    else:
        # المعلم يرى طلباته فقط
        swaps = TeacherSwap.objects.filter(
            school=school,
        ).filter(
            django.db.models.Q(teacher_a=request.user) |
            django.db.models.Q(teacher_b=request.user)
        )

    swaps = swaps.select_related(
        "teacher_a", "teacher_b", "slot_a__subject", "slot_b__subject",
        "slot_a__class_group", "slot_b__class_group",
    ).order_by("-created_at")

    # فلتر الحالة
    status_filter = request.GET.get("status", "")
    if status_filter:
        swaps = swaps.filter(status=status_filter)

    return render(request, "schedule/swap_list.html", {
        "swaps": swaps[:50],
        "status_filter": status_filter,
        "status_choices": TeacherSwap.STATUS,
    })


# ── طلب تبديل جديد ──────────────────────────────────────────────

@login_required
@role_required("teacher", "ese_teacher", "principal", "vice_academic", "vice_admin")
def swap_request(request):
    """نموذج طلب تبديل — يعرض الخيارات المتاحة."""
    school = request.user.get_school()

    if request.method == "POST":
        from datetime import date as date_cls

        slot_a_id = request.POST.get("slot_a")
        slot_b_id = request.POST.get("slot_b")
        swap_date_str = request.POST.get("swap_date", "")
        reason = request.POST.get("reason", "")

        if not slot_a_id or not slot_b_id:
            messages.error(request, "يرجى اختيار حصتين للتبديل")
            return redirect("swap_request")

        slot_a = get_object_or_404(ScheduleSlot, pk=slot_a_id, school=school)
        slot_b = get_object_or_404(ScheduleSlot, pk=slot_b_id, school=school)

        try:
            swap_date = date_cls.fromisoformat(swap_date_str) if swap_date_str else timezone.now().date()
        except ValueError:
            swap_date = timezone.now().date()

        try:
            swap = SwapService.create_swap_request(
                school=school,
                teacher_a=slot_a.teacher,
                teacher_b=slot_b.teacher,
                slot_a=slot_a,
                slot_b=slot_b,
                swap_date_a=swap_date,
                swap_date_b=swap_date,
                reason=reason,
                requested_by=request.user,
            )
            messages.success(request, f"تم إرسال طلب التبديل بنجاح (رقم: {str(swap.pk)[:8]})")
            return redirect("swap_list")
        except Exception as e:
            messages.error(request, f"خطأ: {e}")
            return redirect("swap_request")

    # GET — عرض حصص المعلم للاختيار
    my_slots = ScheduleSlot.objects.filter(
        school=school, teacher=request.user, is_active=True,
    ).select_related("class_group", "subject").order_by("day_of_week", "period_number")

    return render(request, "schedule/swap_request.html", {
        "my_slots": my_slots,
    })


# ── HTMX: خيارات التبديل لحصة معيّنة ────────────────────────────

@login_required
def swap_options_htmx(request, slot_id):
    """HTMX partial — يُعيد معلمين متاحين للتبديل مع حصة معيّنة."""
    school = request.user.get_school()
    slot = get_object_or_404(ScheduleSlot, pk=slot_id, school=school)
    options = SwapService.get_swap_options(request.user, slot, school)
    return render(request, "schedule/partials/swap_options.html", {
        "options": options,
        "slot": slot,
    })


# ── رد المعلم ب (قبول/رفض) ───────────────────────────────────────

@login_required
def swap_respond(request, swap_id):
    """المعلم ب يعرض تفاصيل الطلب ثم يقبل أو يرفض."""
    school = request.user.get_school()
    swap = get_object_or_404(
        TeacherSwap.objects.select_related(
            "teacher_a", "teacher_b", "slot_a", "slot_b",
            "slot_a__subject", "slot_a__class_group",
            "slot_b__subject", "slot_b__class_group",
        ),
        pk=swap_id, school=school, teacher_b=request.user,
    )

    if request.method == "POST":
        action = request.POST.get("action", "")
        rejection_reason = request.POST.get("rejection_reason", "")

        try:
            if action == "accept":
                SwapService.respond_to_swap(swap, accepted=True)
                messages.success(request, "تم قبول طلب التبديل -- بانتظار موافقة المنسق")
            elif action == "reject":
                SwapService.respond_to_swap(swap, accepted=False, rejection_reason=rejection_reason)
                messages.info(request, "تم رفض طلب التبديل")
            else:
                messages.error(request, "اجراء غير صالح")
        except ValueError as e:
            messages.error(request, str(e))

        return redirect("swap_list")

    # GET — عرض تفاصيل الطلب
    return render(request, "schedule/swap_respond.html", {"swap": swap})


# ── موافقة المنسق/النائب ─────────────────────────────────────────

@login_required
@role_required("coordinator", "principal", "vice_academic", "vice_admin")
@require_POST
def swap_approve(request, swap_id):
    """المنسق أو النائب يوافق/يرفض طلب التبديل."""
    school = request.user.get_school()
    swap = get_object_or_404(TeacherSwap, pk=swap_id, school=school)

    action = request.POST.get("action", "")
    rejection_reason = request.POST.get("rejection_reason", "")

    try:
        if action == "approve":
            SwapService.approve_swap(swap, approved_by=request.user, approved=True)
            messages.success(request, "تم اعتماد التبديل وتنفيذه")
        elif action == "reject":
            SwapService.approve_swap(swap, approved_by=request.user, approved=False, rejection_reason=rejection_reason)
            messages.info(request, "تم رفض طلب التبديل")
        else:
            messages.error(request, "إجراء غير صالح")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("swap_list")


# ── قائمة الحصص التعويضية ────────────────────────────────────────

@login_required
@role_required(SCHEDULE_VIEW)
def compensatory_list(request):
    """قائمة الحصص التعويضية."""
    school = request.user.get_school()
    role = request.user.get_role()

    if role in ("principal", "vice_academic", "vice_admin"):
        comps = CompensatorySession.objects.filter(school=school)
    elif role == "coordinator":
        dept = request.user.department
        from core.models import Membership
        dept_teachers = Membership.objects.filter(
            school=school, is_active=True, department=dept,
        ).values_list("user_id", flat=True)
        comps = CompensatorySession.objects.filter(school=school, teacher_id__in=dept_teachers)
    else:
        comps = CompensatorySession.objects.filter(school=school, teacher=request.user)

    comps = comps.select_related(
        "teacher", "original_slot__subject", "original_slot__class_group",
        "class_group", "subject",
    ).order_by("-created_at")

    status_filter = request.GET.get("status", "")
    if status_filter:
        comps = comps.filter(status=status_filter)

    return render(request, "schedule/compensatory_list.html", {
        "compensatory_sessions": comps[:50],
        "status_filter": status_filter,
        "status_choices": CompensatorySession.STATUS,
    })


# ── طلب تعويض جديد ──────────────────────────────────────────────

@login_required
@role_required("teacher", "ese_teacher", "principal", "vice_academic", "vice_admin")
def compensatory_request(request):
    """نموذج طلب حصة تعويضية."""
    school = request.user.get_school()

    if request.method == "POST":
        from datetime import date as date_cls

        slot_id = request.POST.get("original_slot")
        absence_id = request.POST.get("absence")
        comp_date_str = request.POST.get("compensatory_date", "")
        comp_period = request.POST.get("compensatory_period", "")
        notes = request.POST.get("notes", "")

        if not all([slot_id, absence_id, comp_date_str, comp_period]):
            messages.error(request, "يرجى ملء جميع الحقول")
            return redirect("compensatory_request")

        slot = get_object_or_404(ScheduleSlot, pk=slot_id, school=school)
        absence = get_object_or_404(TeacherAbsence, pk=absence_id, school=school)

        try:
            comp_date = date_cls.fromisoformat(comp_date_str)
            comp = CompensatoryService.request_compensatory(
                school=school,
                teacher=request.user,
                original_slot=slot,
                absence=absence,
                compensatory_date=comp_date,
                compensatory_period=int(comp_period),
                notes=notes,
            )
            messages.success(request, "تم إرسال طلب التعويض بنجاح")
            return redirect("compensatory_list")
        except (ValueError, Exception) as e:
            messages.error(request, f"خطأ: {e}")
            return redirect("compensatory_request")

    # GET
    my_absences = TeacherAbsence.objects.filter(
        school=school, teacher=request.user,
    ).order_by("-date")[:10]

    my_slots = ScheduleSlot.objects.filter(
        school=school, teacher=request.user, is_active=True,
    ).select_related("class_group", "subject").order_by("day_of_week", "period_number")

    return render(request, "schedule/compensatory_form.html", {
        "my_absences": my_absences,
        "my_slots": my_slots,
    })


# ── موافقة على تعويض ─────────────────────────────────────────────

@login_required
@role_required("coordinator", "principal", "vice_academic", "vice_admin")
@require_POST
def compensatory_approve(request, comp_id):
    """المنسق/النائب يوافق أو يرفض طلب التعويض."""
    school = request.user.get_school()
    comp = get_object_or_404(CompensatorySession, pk=comp_id, school=school)

    action = request.POST.get("action", "")
    rejection_reason = request.POST.get("rejection_reason", "")

    try:
        if action == "approve":
            CompensatoryService.approve_compensatory(comp, approved_by=request.user, approved=True)
            messages.success(request, "تمت الموافقة على الحصة التعويضية")
        elif action == "reject":
            CompensatoryService.approve_compensatory(
                comp, approved_by=request.user, approved=False, rejection_reason=rejection_reason,
            )
            messages.info(request, "تم رفض طلب التعويض")
        else:
            messages.error(request, "إجراء غير صالح")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("compensatory_list")


# ── HTMX: الحصص الحرة لمعلم ─────────────────────────────────────

@login_required
def teacher_free_slots(request, teacher_id):
    """HTMX partial — يُعيد الحصص الحرة لمعلم معيّن."""
    from core.models import CustomUser
    school = request.user.get_school()
    teacher = get_object_or_404(CustomUser, pk=teacher_id)

    free = FreeSlotService.get_teacher_free_slots(teacher, school)

    # بناء grid
    grid = {d: [] for d in range(5)}
    for f in free:
        grid[f.day_of_week].append(f.period_number)

    days = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]

    return render(request, "schedule/partials/free_slots_grid.html", {
        "teacher": teacher,
        "grid": grid,
        "days": days,
    })


# ── بناء سجل الحصص الحرة ────────────────────────────────────────

@login_required
@role_required(SCHEDULE_MANAGE)
@require_POST
def build_free_slots(request):
    """بناء/إعادة بناء سجل الحصص الحرة."""
    school = request.user.get_school()
    count = FreeSlotService.build_registry(school)
    messages.success(request, f"تم بناء سجل الحصص الحرة: {count} حصة")
    return redirect("swap_list")


# ── عرض جدول معلم ────────────────────────────────────────────────

@login_required
@role_required(SCHEDULE_VIEW)
def teacher_weekly_view(request, teacher_id):
    """عرض الجدول الأسبوعي لمعلم معيّن."""
    from core.models import CustomUser
    school = request.user.get_school()
    teacher = get_object_or_404(CustomUser, pk=teacher_id)

    from .services import ScheduleService
    grid = ScheduleService.get_weekly_schedule(school, teacher=teacher)
    days = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    periods = range(1, 8)

    return render(request, "schedule/teacher_weekly.html", {
        "teacher": teacher,
        "grid": grid,
        "days": days,
        "periods": periods,
    })
