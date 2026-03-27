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
        target_teacher = get_object_or_404(CustomUser, id=teacher_id)
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
    school = request.user.get_school()
    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

    assignments = (
        SubjectClassAssignment.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("class_group", "subject", "teacher")
        .order_by("class_group__grade", "class_group__section", "subject__name_ar")
    )
    generations = ScheduleGeneration.objects.filter(school=school, academic_year=year)[:5]
    total_weekly = sum(a.weekly_periods for a in assignments)

    return render(request, "schedule/smart_schedule.html", {
        "assignments": assignments,
        "generations": generations,
        "year": year,
        "total_weekly": total_weekly,
        "classes_count": assignments.values("class_group").distinct().count(),
        "teachers_count": assignments.values("teacher").distinct().count(),
    })


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
@require_POST
def smart_generate(request):
    """توليد الجدول الذكي — POST فقط"""
    from .scheduler import generate_schedule

    school = request.user.get_school()
    year = request.POST.get("year", settings.CURRENT_ACADEMIC_YEAR)
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
