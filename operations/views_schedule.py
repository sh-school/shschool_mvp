"""operations/views_schedule.py — views إدارة الجداول والغياب والبدلاء."""

import logging
from datetime import date, timedelta

import django.db
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import CustomUser, Membership
from core.permissions import role_required

from .models import (
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherExemption,
    TeacherPreference,
)
from .services import ScheduleService, SubstituteService

logger = logging.getLogger(__name__)

_REPORT_ROLES = {"principal", "vice_academic", "vice_admin", "coordinator", "admin_supervisor", "admin"}
_ADMIN_SCHEDULE_ROLES = {"principal", "vice_academic", "admin"}


# ── الجدول الأسبوعي ──────────────────────────────────────────────


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "teacher",
               "ese_teacher", "academic_advisor", "admin_supervisor", "admin")
def weekly_schedule(request):
    """عرض الجدول الأسبوعي — للمعلم أو كل المعلمين للمدير"""
    from core.models import ClassGroup

    school = request.user.get_school()
    user = request.user
    teacher_id = request.GET.get("teacher")
    class_id = request.GET.get("class")
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    target_teacher = None
    if teacher_id:
        target_teacher = get_object_or_404(
            CustomUser, id=teacher_id,
            memberships__school=school, memberships__is_active=True,
        )
    elif user.is_teacher() and not user.is_admin():
        target_teacher = user

    target_class = None
    if class_id:
        target_class = get_object_or_404(ClassGroup, id=class_id, school=school)

    grid = ScheduleService.get_weekly_schedule(school, target_teacher, target_class, year)
    conflicts = ScheduleService.detect_conflicts(school, year) if user.is_admin() else []

    DAYS = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    PERIODS = range(1, 8)

    teachers, classes = [], []
    if user.is_admin():
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
        classes = ClassGroup.objects.filter(school=school, is_active=True).order_by("grade", "section")

    return render(request, "schedule/weekly.html", {
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
    })


@login_required
@role_required("principal", "vice_academic", "vice_admin", "coordinator", "admin")
def schedule_print(request):
    """طباعة الجدول الأسبوعي — A4/A3"""
    from core.models import ClassGroup

    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    view_type = request.GET.get("view", "school")  # school, teacher, class
    paper = request.GET.get("paper", "a4")  # a4, a3
    teacher_id = request.GET.get("teacher")
    class_id = request.GET.get("class")

    target_teacher = None
    target_class = None

    if view_type == "teacher" and teacher_id:
        target_teacher = get_object_or_404(CustomUser, id=teacher_id)
    elif view_type == "class" and class_id:
        target_class = get_object_or_404(ClassGroup, id=class_id, school=school)

    grid = ScheduleService.get_weekly_schedule(school, target_teacher, target_class, year)

    DAYS = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    PERIODS = range(1, 8)

    # Teachers and classes for selector
    teacher_ids_qs = Membership.objects.filter(
        school=school, is_active=True, role__name__in=("teacher", "coordinator")
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids_qs).order_by("full_name")
    classes = ClassGroup.objects.filter(school=school, is_active=True).order_by("grade", "section")

    title = "الجدول الدراسي العام"
    if target_teacher:
        title = f"جدول المعلم: {target_teacher.full_name}"
    elif target_class:
        title = f"جدول الفصل: {target_class}"

    return render(request, "schedule/print_schedule.html", {
        "grid": grid,
        "days": DAYS,
        "periods": PERIODS,
        "paper": paper,
        "view_type": view_type,
        "target_teacher": target_teacher,
        "target_class": target_class,
        "teachers": teachers,
        "classes": classes,
        "title": title,
        "school": school,
        "year": year,
    })


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def schedule_slot_create(request):
    """إضافة حصة جديدة للجدول"""
    from core.models import ClassGroup

    school = request.user.get_school()

    if request.method == "POST":
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

    teacher_ids = Membership.objects.filter(
        school=school, is_active=True, role__name__in=("teacher", "coordinator")
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
    classes = ClassGroup.objects.filter(school=school, is_active=True).order_by("grade", "section")
    subjects = Subject.objects.filter(school=school).order_by("name_ar")

    return render(request, "schedule/slot_form.html", {
        "teachers": teachers,
        "classes": classes,
        "subjects": subjects,
        "days": ScheduleSlot.DAYS,
    })


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def schedule_slot_delete(request, slot_id):
    """حذف حصة من الجدول (soft delete)"""
    school = request.user.get_school()
    slot = get_object_or_404(ScheduleSlot, id=slot_id, school=school)
    slot.is_active = False
    slot.save(update_fields=["is_active"])
    messages.success(request, "تم حذف الحصة من الجدول")
    return redirect("weekly_schedule")


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def generate_sessions(request):
    """توليد حصص يومية من الجدول — للمدير"""
    if request.method == "POST":
        school = request.user.get_school()
        raw = request.POST.get("date", timezone.now().date().isoformat())
        try:
            gen_date = date.fromisoformat(raw)
        except ValueError:
            gen_date = timezone.now().date()
        count = ScheduleService.generate_daily_sessions(school, gen_date)
        messages.success(request, f"تم توليد {count} حصة ليوم {gen_date}")
        return redirect("weekly_schedule")

    return render(request, "schedule/generate_form.html", {"today": timezone.now().date()})


# ── نظام البديل ──────────────────────────────────────────────────


@login_required
@role_required(_REPORT_ROLES)
def teacher_absence_list(request):
    """قائمة غيابات المعلمين — للمدير والمنسق"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    selected = request.GET.get("date", timezone.now().date().isoformat())
    try:
        abs_date = date.fromisoformat(selected)
    except ValueError:
        abs_date = timezone.now().date()

    absences = (
        TeacherAbsence.objects.filter(school=school, date=abs_date)
        .select_related("teacher", "reported_by")
        .prefetch_related("assignments__substitute")
    )
    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        absences = absences.filter(teacher_id__in=dept_ids)

    return render(request, "substitute/absence_list.html",
                  {"absences": absences, "abs_date": abs_date})


@login_required
@role_required(_REPORT_ROLES)
def register_teacher_absence(request):
    """تسجيل غياب معلم — للمدير والمنسق"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()

    if request.method == "POST":
        teacher = get_object_or_404(
            CustomUser, id=request.POST["teacher"], memberships__school=school
        )
        raw_date = request.POST.get("date", timezone.now().date().isoformat())
        try:
            abs_date = date.fromisoformat(raw_date)
        except ValueError:
            abs_date = timezone.now().date()

        reason = request.POST.get("reason", "other")
        reason_notes = request.POST.get("reason_notes", "")
        absence = SubstituteService.register_absence(
            school, teacher, abs_date, reason, reason_notes, reported_by=request.user
        )
        messages.success(request, f"تم تسجيل غياب {teacher.full_name} بتاريخ {abs_date}")
        return redirect("absence_detail", absence_id=absence.id)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        teachers = CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")
    else:
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator", "ese_teacher")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    return render(request, "substitute/register_absence.html", {
        "teachers": teachers,
        "reasons": TeacherAbsence.REASON,
        "today": timezone.now().date(),
    })


@login_required
@role_required(_REPORT_ROLES)
def absence_detail(request, absence_id):
    """تفاصيل الغياب + تعيين البدلاء"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    absence = get_object_or_404(TeacherAbsence, id=absence_id, school=school)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None and absence.teacher_id not in dept_ids:
        return HttpResponse("هذا المعلم ليس من قسمك", status=403)

    our_day = SubstituteService._date_to_day(absence.date)
    slots = ScheduleSlot.objects.filter(
        school=school, teacher=absence.teacher, day_of_week=our_day, is_active=True
    ).select_related("class_group", "subject")

    assignments = {
        a.slot_id: a
        for a in SubstituteAssignment.objects.filter(absence=absence).select_related("substitute")
    }
    slots_data = []
    for slot in slots:
        available = SubstituteService.get_available_teachers(
            school, absence.date, slot.day_of_week, slot.period_number,
            exclude_teacher=absence.teacher,
            subject_id=slot.subject_id,
        )
        slots_data.append({
            "slot": slot,
            "assignment": assignments.get(slot.id),
            "available": available,
        })

    return render(request, "substitute/absence_detail.html",
                  {"absence": absence, "slots_data": slots_data})


@login_required
@role_required(_REPORT_ROLES)
@require_POST
def assign_substitute(request, absence_id, slot_id):
    """HTMX: تعيين بديل لحصة"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    absence = get_object_or_404(TeacherAbsence, id=absence_id, school=school)
    slot = get_object_or_404(ScheduleSlot, id=slot_id, school=school)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None and absence.teacher_id not in dept_ids:
        return HttpResponse("هذا المعلم ليس من قسمك", status=403)

    substitute = get_object_or_404(CustomUser, id=request.POST["substitute"])
    assignment = SubstituteService.assign_substitute(
        absence, slot, substitute, assigned_by=request.user,
        notes=request.POST.get("notes", ""),
    )
    available = SubstituteService.get_available_teachers(
        school, absence.date, slot.day_of_week, slot.period_number,
        exclude_teacher=absence.teacher,
        subject_id=slot.subject_id,
    )
    return render(request, "substitute/partials/slot_card.html", {
        "slot": slot, "assignment": assignment, "available": available, "absence": absence,
    })


@login_required
@role_required(_REPORT_ROLES)
def substitute_report(request):
    """تقرير الحصص البديلة"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    today = timezone.now().date()
    date_from = date.fromisoformat(request.GET.get("from", (today - timedelta(days=7)).isoformat()))
    date_to = date.fromisoformat(request.GET.get("to", today.isoformat()))

    assignments = SubstituteService.get_substitute_report(school, date_from, date_to)
    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        assignments = [a for a in assignments if a.absence.teacher_id in dept_ids]

    summary = {}
    for a in assignments:
        name = a.substitute.full_name
        summary[name] = summary.get(name, 0) + 1

    return render(request, "substitute/report.html", {
        "assignments": assignments,
        "summary": sorted(summary.items(), key=lambda x: -x[1]),
        "date_from": date_from,
        "date_to": date_to,
    })


# ── الجدولة الذكية ────────────────────────────────────────────────


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def smart_schedule_view(request):
    """صفحة إدارة الجدولة الذكية"""
    from collections import defaultdict

    from .scheduler_constraints import get_max_periods_for_day

    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    assignments = (
        SubjectClassAssignment.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("class_group", "subject", "teacher")
        .order_by("class_group__grade", "class_group__section", "subject__name_ar")
    )
    generations = ScheduleGeneration.objects.filter(school=school, academic_year=year)[:5]
    total_weekly = sum(a.weekly_periods for a in assignments)

    # ── Pre-validation: capacity check per class ──
    from .scheduler import _grade_to_level

    class_demand = defaultdict(int)
    class_levels = {}
    for a in assignments:
        cid = str(a.class_group_id)
        class_demand[cid] += a.weekly_periods
        class_levels[cid] = _grade_to_level(a.class_group.grade)

    overcapacity_classes = []
    for cid, demand in class_demand.items():
        level = class_levels.get(cid, "")
        thu_max = get_max_periods_for_day(4, level)
        weekly_capacity = 4 * 7 + thu_max
        if demand > weekly_capacity:
            overcapacity_classes.append({
                "class_id": cid,
                "demand": demand,
                "capacity": weekly_capacity,
                "overflow": demand - weekly_capacity,
            })

    return render(request, "schedule/smart_schedule.html", {
        "assignments": assignments,
        "generations": generations,
        "year": year,
        "total_weekly": total_weekly,
        "classes_count": assignments.values("class_group").distinct().count(),
        "teachers_count": assignments.values("teacher").distinct().count(),
        "overcapacity_classes": overcapacity_classes,
    })


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
@require_POST
def smart_generate(request):
    """توليد الجدول الذكي — POST فقط"""
    from .scheduler import generate_schedule

    school = request.user.get_school()
    year = request.POST.get("year", settings.CURRENT_ACADEMIC_YEAR)

    try:
        result = generate_schedule(school, year, user=request.user)
    except Exception as exc:
        logger.exception("خطأ في توليد الجدول: %s", exc)
        messages.error(request, f"خطأ في التوليد: {exc}")
        return redirect("smart_schedule")

    ps = result.get("phase_stats", {})
    total_placed = ps.get("phase1", 0) + ps.get("phase2", 0) + ps.get("phase3", 0)
    total_tasks = result.get("total_tasks", 0)

    if result["success"]:
        messages.success(
            request,
            f"✅ تم توليد الجدول بنجاح! الجودة: {result['quality']['score']}% — "
            f"{total_placed}/{total_tasks} حصة في {result['elapsed_ms']}ms "
            f"(م1: {ps.get('phase1', 0)} | م2: {ps.get('phase2', 0)} | م3: {ps.get('phase3', 0)})",
        )
    else:
        failed = ps.get("failed", len(result["errors"]))
        # Show capacity warnings as error-level messages first
        capacity_errors = [e for e in result.get("errors", []) if e.startswith("⚠️")]
        other_errors = [e for e in result.get("errors", []) if not e.startswith("⚠️")]

        for ce in capacity_errors:
            messages.error(request, ce)

        for err in other_errors[:5]:
            messages.warning(request, err)
        if total_placed > 0:
            messages.info(
                request,
                f"تم توليد {total_placed}/{total_tasks} حصة (جودة: {result['quality']['score']}%) "
                f"— {failed} تعذّر "
                f"(م1: {ps.get('phase1', 0)} | م2: {ps.get('phase2', 0)} | م3: {ps.get('phase3', 0)})",
            )
        if len(result["errors"]) > 5:
            messages.warning(request, f"... و{len(result['errors']) - 5} أخطاء أخرى")

    return redirect("smart_schedule")


@login_required
@role_required(_REPORT_ROLES)
def teacher_load_report(request):
    """تقرير أحمال المعلمين"""
    from collections import Counter

    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        teachers = CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")
    else:
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator", "ese_teacher")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    slot_counts = Counter(
        ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True)
        .values_list("teacher_id", flat=True)
    )
    month_start = date.today().replace(day=1)
    sub_counts = Counter(
        SubstituteAssignment.objects.filter(
            school=school, absence__date__gte=month_start
        ).values_list("substitute_id", flat=True)
    )

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
        teacher_data.append({
            "teacher": t,
            "weekly": weekly,
            "subs": subs,
            "max_daily": max(days) if days else 0,
            "min_daily": min(d for d in days if d > 0) if any(d > 0 for d in days) else 0,
            "free_days": sum(1 for d in days if d == 0),
            "days": days,
        })

    teacher_data.sort(key=lambda x: -x["weekly"])
    avg_weekly = sum(d["weekly"] for d in teacher_data) / len(teacher_data) if teacher_data else 0

    return render(request, "schedule/teacher_load.html", {
        "teacher_data": teacher_data,
        "year": year,
        "avg_weekly": round(avg_weekly, 1),
        "total_teachers": len(teacher_data),
    })


# ── تفضيلات المعلم ──────────────────────────────────────────────


@login_required
@role_required("teacher", "ese_teacher", "coordinator", "activities_coordinator")
def teacher_preferences(request):
    """صفحة تفضيلات المعلم للجدولة الذكية"""
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)
    pref, _created = TeacherPreference.objects.get_or_create(
        teacher=request.user, school=school, academic_year=year,
    )

    if request.method == "POST":
        pref.max_daily_periods = int(request.POST.get("max_daily_periods", 5))
        pref.max_consecutive = int(request.POST.get("max_consecutive", 3))
        free_day = request.POST.get("free_day", "")
        pref.free_day = int(free_day) if free_day else None
        pref.notes = request.POST.get("notes", "")
        pref.save()
        messages.success(request, "تم حفظ تفضيلاتك للجدولة الذكية")
        return redirect("teacher_preferences")

    return render(request, "schedule/teacher_preferences.html", {
        "pref": pref,
        "days": ScheduleSlot.DAYS,
        "year": year,
    })


# ── اعتماد الجدول ─────────────────────────────────────────────────


@login_required
@role_required("principal", "vice_academic")
@require_POST
def approve_schedule(request, generation_id):
    """اعتماد الجدول المولّد"""
    school = request.user.get_school()
    gen = get_object_or_404(ScheduleGeneration, id=generation_id, school=school)

    if gen.status != "draft":
        messages.warning(request, "هذا الجدول ليس مسودة — لا يمكن اعتماده")
        return redirect("smart_schedule")

    # Archive any previously approved generation
    ScheduleGeneration.objects.filter(
        school=school, academic_year=gen.academic_year, status="approved"
    ).update(status="archived")

    gen.status = "approved"
    gen.save(update_fields=["status"])

    # Notify all teachers
    from notifications.models import InAppNotification

    teacher_ids = Membership.objects.filter(
        school=school, is_active=True,
        role__name__in=("teacher", "coordinator", "ese_teacher", "activities_coordinator"),
    ).values_list("user_id", flat=True)

    notifs = [
        InAppNotification(
            user_id=tid,
            title="تم اعتماد الجدول الدراسي",
            body=f"تم اعتماد الجدول للعام {gen.academic_year}. راجع جدولك من صفحة الجدول الأسبوعي.",
            event_type="general",
            priority="normal",
            related_url="/teacher/weekly-schedule/",
        )
        for tid in teacher_ids
    ]
    InAppNotification.objects.bulk_create(notifs)

    messages.success(request, f"تم اعتماد الجدول وإشعار {len(notifs)} معلم")
    return redirect("smart_schedule")


# ── إعدادات الجدول — النائب الأكاديمي ───────────────────────────


@login_required
@role_required("principal", "vice_academic")
def schedule_settings(request):
    """إعدادات الجدول الذكي — تفريغات المعلمين + حصص مزدوجة"""
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    exemptions = (
        TeacherExemption.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("teacher", "created_by")
    )
    subjects = Subject.objects.filter(school=school).order_by("name_ar")
    teacher_prefs = (
        TeacherPreference.objects.filter(school=school, academic_year=year)
        .select_related("teacher")
        .order_by("teacher__full_name")
    )

    # قائمة المعلمين لإضافة تفريغ
    teacher_ids = Membership.objects.filter(
        school=school, is_active=True,
        role__name__in=("teacher", "coordinator", "ese_teacher", "activities_coordinator"),
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    return render(request, "schedule/schedule_settings.html", {
        "exemptions": exemptions,
        "subjects": subjects,
        "teacher_prefs": teacher_prefs,
        "teachers": teachers,
        "days": ScheduleSlot.DAYS,
        "year": year,
    })


@login_required
@role_required("principal", "vice_academic")
@require_POST
def add_exemption(request):
    """إضافة تفريغ معلم — POST"""
    school = request.user.get_school()
    year = request.POST.get("year", settings.CURRENT_ACADEMIC_YEAR)
    teacher = get_object_or_404(CustomUser, id=request.POST["teacher"])
    exemption_type = request.POST.get("exemption_type", "full_day")
    day_of_week = int(request.POST["day_of_week"])
    period_number = request.POST.get("period_number")
    reason = request.POST.get("reason", "")

    TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=year,
        exemption_type=exemption_type,
        day_of_week=day_of_week,
        period_number=int(period_number) if period_number else None,
        reason=reason,
        created_by=request.user,
    )
    messages.success(request, f"تم تفريغ {teacher.full_name}")
    return redirect(f"{request.META.get('HTTP_REFERER', '/operations/schedule-settings/')}?year={year}")


@login_required
@role_required("principal", "vice_academic")
@require_POST
def remove_exemption(request, exemption_id):
    """إلغاء تفريغ"""
    school = request.user.get_school()
    exemption = get_object_or_404(TeacherExemption, id=exemption_id, school=school)
    exemption.is_active = False
    exemption.save(update_fields=["is_active"])
    messages.success(request, "تم إلغاء التفريغ")
    return redirect(request.META.get("HTTP_REFERER", "/operations/schedule-settings/"))


@login_required
@role_required("principal", "vice_academic")
@require_POST
def toggle_double_period(request, subject_id):
    """تفعيل/إلغاء الحصة المزدوجة لمادة"""
    school = request.user.get_school()
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    subject.requires_double_period = not subject.requires_double_period
    subject.save(update_fields=["requires_double_period"])
    status = "مفعّلة" if subject.requires_double_period else "معطّلة"
    messages.success(request, f"الحصة المزدوجة لـ {subject.name_ar}: {status}")
    return redirect(request.META.get("HTTP_REFERER", "/operations/schedule-settings/"))
