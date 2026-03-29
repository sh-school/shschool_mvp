"""operations/views_swap.py — views التبديل والتعويض والحصص الحرة."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import role_required, SCHEDULE_MANAGE, SCHEDULE_VIEW

from .models import (
    CompensatorySession,
    FreeSlotRegistry,
    ScheduleSlot,
    TeacherAbsence,
    TeacherSwap,
)
from .services import CompensatoryService, FreeSlotService, SwapService

logger = logging.getLogger(__name__)

SCHEDULE_VIEW_ROLES = {"principal", "vice_academic", "vice_admin", "coordinator",
                       "teacher", "ese_teacher", "academic_advisor"}


# ── قائمة طلبات التبديل ─────────────────────────────────────────


@login_required
@role_required(SCHEDULE_VIEW)
def swap_list(request):
    """قائمة طلبات التبديل — مفلترة حسب الدور."""
    school = request.user.get_school()
    role = request.user.get_role()

    if role in ("principal", "vice_academic", "vice_admin"):
        swaps = TeacherSwap.objects.filter(school=school)
    elif role == "coordinator":
        from core.permissions import get_department_teacher_ids
        dept_teachers = get_department_teacher_ids(request.user) or set()
        swaps = TeacherSwap.objects.filter(school=school).filter(
            Q(teacher_a_id__in=dept_teachers) | Q(teacher_b_id__in=dept_teachers)
        )
    else:
        swaps = TeacherSwap.objects.filter(school=school).filter(
            Q(teacher_a=request.user) | Q(teacher_b=request.user)
        )

    swaps = swaps.select_related(
        "teacher_a", "teacher_b",
        "slot_a__subject", "slot_a__class_group",
        "slot_b__subject", "slot_b__class_group",
    ).order_by("-created_at")

    status_filter = request.GET.get("status", "")
    if status_filter:
        swaps = swaps.filter(status=status_filter)

    return render(request, "schedule/swap_list.html", {
        "swaps": swaps[:50],
        "status_filter": status_filter,
        "status_choices": TeacherSwap.STATUS,
    })


@login_required
@role_required("teacher", "ese_teacher", "principal", "vice_academic", "vice_admin")
def swap_request(request):
    """نموذج طلب تبديل."""
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

    my_slots = ScheduleSlot.objects.filter(
        school=school, teacher=request.user, is_active=True,
    ).select_related("class_group", "subject").order_by("day_of_week", "period_number")

    return render(request, "schedule/swap_request.html", {"my_slots": my_slots})


@login_required
@role_required(SCHEDULE_VIEW)
def swap_options_htmx(request, slot_id):
    """HTMX partial — معلمون متاحون للتبديل مع حصة معيّنة."""
    school = request.user.get_school()
    slot = get_object_or_404(ScheduleSlot, pk=slot_id, school=school)
    options = SwapService.get_swap_options(request.user, slot, school)
    return render(request, "schedule/partials/swap_options.html",
                  {"options": options, "slot": slot})


@login_required
@role_required("teacher", "ese_teacher", "coordinator", "principal", "vice_academic", "vice_admin")
def swap_respond(request, swap_id):
    """المعلم ب يقبل أو يرفض طلب التبديل."""
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
                messages.success(request, "تم قبول طلب التبديل — بانتظار موافقة المنسق")
            elif action == "reject":
                SwapService.respond_to_swap(swap, accepted=False, rejection_reason=rejection_reason)
                messages.info(request, "تم رفض طلب التبديل")
            else:
                messages.error(request, "إجراء غير صالح")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("swap_list")

    return render(request, "schedule/swap_respond.html", {"swap": swap})


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
            SwapService.approve_swap(
                swap, approved_by=request.user, approved=False,
                rejection_reason=rejection_reason,
            )
            messages.info(request, "تم رفض طلب التبديل")
        else:
            messages.error(request, "إجراء غير صالح")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("swap_list")


@login_required
@role_required(SCHEDULE_VIEW)
@require_POST
def swap_cancel(request, swap_id):
    """إلغاء طلب تبديل."""
    school = request.user.get_school()
    swap = get_object_or_404(TeacherSwap, pk=swap_id, school=school)
    try:
        SwapService.cancel_swap(swap, cancelled_by=request.user)
        messages.success(request, "تم إلغاء طلب التبديل")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("swap_list")


# ── الحصص التعويضية ───────────────────────────────────────────────


@login_required
@role_required(SCHEDULE_VIEW)
def compensatory_list(request):
    """قائمة الحصص التعويضية."""
    school = request.user.get_school()
    role = request.user.get_role()

    if role in ("principal", "vice_academic", "vice_admin"):
        comps = CompensatorySession.objects.filter(school=school)
    elif role == "coordinator":
        from core.permissions import get_department_teacher_ids
        dept_teachers = get_department_teacher_ids(request.user) or set()
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
            CompensatoryService.request_compensatory(
                school=school, teacher=request.user, original_slot=slot, absence=absence,
                compensatory_date=comp_date, compensatory_period=int(comp_period), notes=notes,
            )
            messages.success(request, "تم إرسال طلب التعويض بنجاح")
            return redirect("compensatory_list")
        except (ValueError, Exception) as e:
            messages.error(request, f"خطأ: {e}")
            return redirect("compensatory_request")

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
                comp, approved_by=request.user, approved=False,
                rejection_reason=rejection_reason,
            )
            messages.info(request, "تم رفض طلب التعويض")
        else:
            messages.error(request, "إجراء غير صالح")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("compensatory_list")


# ── الحصص الحرة ──────────────────────────────────────────────────


@login_required
@role_required(SCHEDULE_VIEW)
def teacher_free_slots(request, teacher_id):
    """HTMX partial — الحصص الحرة لمعلم معيّن."""
    from core.models import CustomUser

    school = request.user.get_school()
    teacher = get_object_or_404(
        CustomUser, pk=teacher_id,
        memberships__school=school, memberships__is_active=True,
    )
    free = FreeSlotService.get_teacher_free_slots(teacher, school)

    grid = {d: [] for d in range(5)}
    for f in free:
        grid[f.day_of_week].append(f.period_number)

    days = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    return render(request, "schedule/partials/free_slots_grid.html",
                  {"teacher": teacher, "grid": grid, "days": days})


@login_required
@role_required(SCHEDULE_MANAGE)
@require_POST
def build_free_slots(request):
    """بناء/إعادة بناء سجل الحصص الحرة."""
    school = request.user.get_school()
    count = FreeSlotService.build_registry(school)
    messages.success(request, f"تم بناء سجل الحصص الحرة: {count} حصة")
    return redirect("swap_list")


@login_required
@role_required(SCHEDULE_VIEW)
def teacher_weekly_view(request, teacher_id):
    """عرض الجدول الأسبوعي لمعلم معيّن."""
    from core.models import CustomUser

    from .services import ScheduleService

    school = request.user.get_school()
    teacher = get_object_or_404(
        CustomUser, pk=teacher_id,
        memberships__school=school, memberships__is_active=True,
    )
    grid = ScheduleService.get_weekly_schedule(school, teacher=teacher)
    days = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    periods = range(1, 8)

    return render(request, "schedule/teacher_weekly.html", {
        "teacher": teacher,
        "grid": grid,
        "days": days,
        "periods": periods,
    })
