"""operations/views_schedule.py — views إدارة الجداول والغياب والبدلاء."""

import logging
from datetime import date, timedelta
from urllib.parse import urlencode

import django.db
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for, academic_year_for_school
from core.models import CustomUser, Membership
from core.models.academic import grade_order
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

_REPORT_ROLES = {
    "principal",
    "vice_academic",
    "vice_admin",
    "coordinator",
    "admin_supervisor",
    "admin",
}
_ADMIN_SCHEDULE_ROLES = {"principal", "vice_academic", "admin"}
#: من يكتب توزيعاتِ المواد — الوقودَ الذي يقرؤه المولّد.
SCHEDULE_MANAGE_ROLES = {"principal", "vice_academic"}

#: بعدها يُعدّ التوليدُ المعلّقُ ميّتاً. والحدُّ أكبرُ من `soft_time_limit`
#: للمهمّة (خمس عشرة دقيقة) بهامشِ انتظارٍ في الطابور — فما تجاوزه لم يعد
#: ينتظر عاملاً، بل يحجب الزرَّ عمّن يريد إعادةَ المحاولة.
_GENERATION_STALE_AFTER = timedelta(minutes=20)


def _reap_stale_generations(school, year):
    """يُنهي التوليداتِ المعلّقةَ التي لا عاملَ لها — ويعيد ما بقي حيّاً.

    فالعاملُ قد يكون مطفأً أو ساقطاً، و`delay()` تنجح لأنّ الوسيطَ قَبِل
    الرسالة ولا أحدَ يقرؤها. وصفٌّ «في الانتظار» إلى الأبد يقفل الزرَّ ويقول
    للمستخدم إنّ شيئاً يجري — وليس شيءٌ يجري.
    """
    cutoff = timezone.now() - _GENERATION_STALE_AFTER
    pending = ScheduleGeneration.objects.filter(
        school=school,
        academic_year=year,
        status__in=ScheduleGeneration.PENDING_STATUSES,
    )
    pending.filter(generated_at__lt=cutoff).update(
        status="failed",
        finished_at=timezone.now(),
        error_message=(
            "لم يلتقط عاملُ الخلفيّة هذه المهمّة خلال عشرين دقيقة — "
            "غالباً لأنّ Celery متوقّف. راجع تشغيلَه ثمّ أعد المحاولة."
        ),
    )
    return pending.filter(generated_at__gte=cutoff).first()


def _safe_schedule_settings_redirect(request, fallback_year=None):
    """Use a same-host Referer or a safe year-aware fallback."""
    referer = request.META.get("HTTP_REFERER", "")

    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)

    if fallback_year:
        query = urlencode({"year": fallback_year})
        target = f"{reverse('schedule_settings')}?{query}"

        if url_has_allowed_host_and_scheme(
            target,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(target)

    return redirect("schedule_settings")


#: من يتصفّح جداول غيره — القيادة ومن يُنسّق الجداول.
#: ومن سواهم يرى جدوله هو، مهما كتب في الرابط.
SCHEDULE_BROWSE_ROLES = {
    "principal",
    "vice_academic",
    "vice_admin",
    "coordinator",
    "admin_supervisor",
    "admin",
}


# ── الجدول الأسبوعي ──────────────────────────────────────────────


@login_required
@role_required(
    "principal",
    "vice_academic",
    "vice_admin",
    "coordinator",
    "teacher",
    "ese_teacher",
    "academic_advisor",
    "admin_supervisor",
    "admin",
)
def weekly_schedule(request):
    """عرض الجدول الأسبوعي — للمعلم أو كل المعلمين للمدير"""
    from core.models import ClassGroup

    school = request.user.get_school()
    user = request.user
    teacher_id = request.GET.get("teacher")
    class_id = request.GET.get("class")
    year = request.GET.get("year") or academic_year_for(request)

    # المعلّم يرى جدوله هو. وكان `?teacher=` يُقرأ لكلّ من طلبه، فيقرأ
    # المعلّمُ جدول زميله وجدول أيّ شعبةٍ بتغيير رقمٍ في الرابط — والقصدُ
    # المكتوب في وصف الدالّة خلافُه: «للمعلم أو كل المعلمين للمدير».
    may_browse = user.is_admin() or user.get_role() in SCHEDULE_BROWSE_ROLES

    target_teacher = None
    if teacher_id and may_browse:
        target_teacher = get_object_or_404(CustomUser.objects.in_school(school), id=teacher_id)
    elif user.is_teacher() and not may_browse:
        target_teacher = user

    target_class = None
    if class_id and may_browse:
        target_class = get_object_or_404(ClassGroup, id=class_id, school=school)

    # معاينةُ مسودّةِ توليدٍ قبل اعتمادها — لمن يتصفّح الجداول وحدَه، فالمسودّةُ
    # ليست جدولَ أحدٍ بعد.
    preview = None
    generation_id = request.GET.get("generation")
    if generation_id and may_browse:
        preview = get_object_or_404(
            ScheduleGeneration, id=generation_id, school=school, academic_year=year
        )

    grid = ScheduleService.get_weekly_schedule(
        school, target_teacher, target_class, year, generation=preview
    )
    conflicts = ScheduleService.detect_conflicts(school, year) if user.is_admin() else []

    DAYS = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    PERIODS = ScheduleSlot.PERIODS

    teachers, classes = [], []
    if user.is_admin():
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
        classes = ClassGroup.objects.filter(
            school=school, academic_year=academic_year_for_school(school), is_active=True
        ).in_school_order()

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
            "preview": preview,
        },
    )


def _schedule_print_selection(request):
    """ما يُطبع ولمن — يشترك فيه الورقُ وصفحةُ العرض التي تحتضنه."""
    from core.models import ClassGroup

    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    # الورقةُ المعلّقة في المدرسة هي «الجدول العام للمعلمين»: المعلّمون
    # سطوراً والأسبوعُ عرضاً. وكان الافتراضُ `school` — خمسُ خاناتٍ تحشر
    # فيها ألفُ حصّةٍ فلا تُقرأ ولا تُطبع.
    view_type = request.GET.get("view", "all_teachers")  # all_teachers, school, teacher, class
    paper = request.GET.get("paper") or ("a3" if view_type == "all_teachers" else "a4")
    teacher_id = request.GET.get("teacher")
    class_id = request.GET.get("class")

    target_teacher = None
    target_class = None

    # المعلّم يطبع جدوله هو. وكان الاختيار يُقرأ من الرابط بلا نظرٍ إلى
    # طالبه، و`get_object_or_404(CustomUser, id=…)` بلا قيد مدرسة — أي
    # جدولُ معلّمٍ في مدرسةٍ أخرى.
    may_browse = request.user.is_admin() or request.user.get_role() in SCHEDULE_BROWSE_ROLES

    if not may_browse:
        view_type = "teacher"
        target_teacher = request.user
    elif view_type == "teacher" and teacher_id:
        target_teacher = get_object_or_404(CustomUser.objects.in_school(school), id=teacher_id)
    elif view_type == "class" and class_id:
        target_class = get_object_or_404(ClassGroup, id=class_id, school=school)

    # قائمتا الاختيار لمن يتصفّح غيره وحده: عرضُهما على المعلّم يُظهر
    # أسماء زملائه وشُعب المدرسة في أداةٍ لا تعمل له أصلاً.
    teachers, classes = [], []
    if may_browse:
        teacher_ids_qs = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids_qs).order_by("full_name")
        classes = ClassGroup.objects.filter(
            school=school, academic_year=academic_year_for_school(school), is_active=True
        ).in_school_order()

    title = "الجدول الدراسي العام"
    if view_type == "all_teachers":
        title = "الجدول العام للمعلمين"
    elif target_teacher:
        title = f"جدول المعلم: {target_teacher.full_name}"
    elif target_class:
        title = f"جدول الفصل: {target_class}"

    return {
        "school": school,
        "year": year,
        "view_type": view_type,
        "paper": paper,
        "target_teacher": target_teacher,
        "target_class": target_class,
        "may_browse": may_browse,
        "teachers": teachers,
        "classes": classes,
        "title": title,
    }


# `X_FRAME_OPTIONS = "DENY"` عامٌّ على المشروع، فيمنع عرض الورقة داخل إطار
# صفحة العرض في المنصّة — والمصدرُ هو الموقع نفسه، فـ sameorigin يكفي.
@xframe_options_sameorigin
@login_required
@role_required(SCHEDULE_BROWSE_ROLES | {"teacher", "ese_teacher", "academic_advisor"})
def schedule_print(request):
    """ورقةُ الطباعة نفسها — A4/A3، بلا هيدر المنصّة ولا فوترها."""
    ctx = _schedule_print_selection(request)
    school, year = ctx["school"], ctx["year"]

    # الجدولُ العام يكشف جداول المعلّمين جميعاً، ومن لا يتصفّح غيره صُرف
    # إلى جدوله في اختيار الطباعة.
    grid, matrix, matrix_totals = {}, [], None
    if ctx["view_type"] == "all_teachers":
        matrix = ScheduleService.get_teachers_matrix(school, year)
        matrix_totals = ScheduleService.matrix_totals(matrix, school, year)
    else:
        grid = ScheduleService.get_weekly_schedule(
            school, ctx["target_teacher"], ctx["target_class"], year
        )

    DAYS = [(0, "الأحد"), (1, "الاثنين"), (2, "الثلاثاء"), (3, "الأربعاء"), (4, "الخميس")]
    # الورقة المطبوعة تحمل توقيت كل حصة تحت رقمها، كما في جدول المدرسة —
    # وكانت الخلايا بلا توقيتٍ أصلاً.
    times = ScheduleService.period_times(school, year)
    PERIODS = [
        {"number": n, "start": times.get(n, (None, None))[0], "end": times.get(n, (None, None))[1]}
        for n in ScheduleSlot.PERIODS
    ]

    return render(
        request,
        "schedule/print_schedule.html",
        {
            **ctx,
            "grid": grid,
            "matrix": matrix,
            "matrix_totals": matrix_totals,
            "days": DAYS,
            "periods": PERIODS,
            "period_numbers": range(1, 8),
            # داخل الإطار: الورقةُ وحدها، وأدواتُها في الصفحة الحاضنة.
            "embed": request.GET.get("embed") == "1",
        },
    )


@login_required
@role_required(SCHEDULE_BROWSE_ROLES | {"teacher", "ese_teacher", "academic_advisor"})
def schedule_print_view(request):
    """الورقةُ داخل المنصّة — كصفحة الزيارات الصفّية: هيدرٌ وفوترٌ وأدوات،
    والورقةُ نفسها في إطارٍ يُطبع وحده."""
    return render(request, "schedule/print_view.html", _schedule_print_selection(request))


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def schedule_slot_create(request):
    """إضافة حصة جديدة للجدول"""
    from core.models import ClassGroup

    school = request.user.get_school()

    if request.method == "POST":
        try:
            from core.models import CustomUser as _CU

            teacher = get_object_or_404(_CU, id=request.POST["teacher"])
            # ✅ v5.4: ScheduleService.create_slot — atomic + logging
            slot = ScheduleService.create_slot(
                school=school,
                teacher=teacher,
                class_group_id=request.POST["class_group"],
                subject_id=request.POST.get("subject"),
                day_of_week=int(request.POST["day_of_week"]),
                period_number=int(request.POST["period_number"]),
                start_time=request.POST["start_time"],
                end_time=request.POST["end_time"],
                academic_year=request.POST.get("academic_year") or academic_year_for(request),
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
    classes = ClassGroup.objects.filter(
        school=school, academic_year=academic_year_for_school(school), is_active=True
    ).in_school_order()
    subjects = Subject.objects.filter(school=school).order_by("name_ar")

    return render(
        request,
        "schedule/slot_form.html",
        {
            "teachers": teachers,
            "classes": classes,
            "subjects": subjects,
            "days": ScheduleSlot.DAYS,
        },
    )


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

    return render(
        request, "substitute/absence_list.html", {"absences": absences, "abs_date": abs_date}
    )


@login_required
@role_required(_REPORT_ROLES)
def register_teacher_absence(request):
    """تسجيل غياب معلم — للمدير والمنسق"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()

    if request.method == "POST":
        teacher = get_object_or_404(
            CustomUser.objects.in_school(school), id=request.POST["teacher"]
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
            school,
            absence.date,
            slot.day_of_week,
            slot.period_number,
            exclude_teacher=absence.teacher,
            subject_id=slot.subject_id,
        )
        slots_data.append(
            {
                "slot": slot,
                "assignment": assignments.get(slot.id),
                "available": available,
            }
        )

    return render(
        request, "substitute/absence_detail.html", {"absence": absence, "slots_data": slots_data}
    )


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
        absence,
        slot,
        substitute,
        assigned_by=request.user,
        notes=request.POST.get("notes", ""),
    )
    available = SubstituteService.get_available_teachers(
        school,
        absence.date,
        slot.day_of_week,
        slot.period_number,
        exclude_teacher=absence.teacher,
        subject_id=slot.subject_id,
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


# ── الجدولة الذكية ────────────────────────────────────────────────


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def smart_schedule_view(request):
    """صفحة إدارة الجدولة الذكية"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    assignments = (
        SubjectClassAssignment.objects.filter(school=school, academic_year=year, is_active=True)
        .select_related("class_group", "subject", "teacher")
        .order_by(grade_order("class_group__grade"), "class_group__section", "subject__name_ar")
    )
    # التوليدُ الجاري — الصفحةُ تُخفي الزرَّ وتستطلع الحالةَ ما دام قائماً.
    # والقتلُ يسبق القراءة: صفٌّ متقادمٌ يُوسَم فاشلاً قبل أن يُعرض «جارياً».
    pending_generation = _reap_stale_generations(school, year)
    generations = list(
        ScheduleGeneration.objects.filter(school=school, academic_year=year).select_related(
            "generated_by"
        )[:5]
    )
    total_weekly = sum(a.weekly_periods for a in assignments)
    # ما وُضع فعلاً مقابلَ ما تطلبه التوزيعاتُ اليوم — لا رقمٌ مجرَّدٌ لا يُقاس على شيء.
    # ومسودّةٌ لم تعد تغطّي الطلبَ الحاليَّ هي بالضبط ما يجب أن يلفت النظر.
    for g in generations:
        ratio = 100 * g.total_slots_created / total_weekly if total_weekly else 0.0
        # نصٌّ لا رقم: `floatformat` يتبع اللغةَ فيكتب «100٫0»، والرقمُ هنا يُقرأ ويُقارَن.
        g.placed_ratio = f"{ratio:.1f}"

    # ✅ v5.4: CapacityCheckService.get_overcapacity_classes — validation في service layer
    from operations.services import CapacityCheckService

    overcapacity_classes = CapacityCheckService.get_overcapacity_classes(assignments)

    return render(
        request,
        "schedule/smart_schedule.html",
        {
            "assignments": assignments,
            "generations": generations,
            "pending_generation": pending_generation,
            # زرُّ الاعتماد لمن يملكه: كان يظهر لكلّ من يرى الصفحةَ، و`admin`
            # يضغطه فيُصدَم بـ403.
            "can_approve": request.user.is_superuser
            or request.user.get_role() in ("principal", "vice_academic"),
            "year": year,
            "total_weekly": total_weekly,
            "classes_count": assignments.values("class_group").distinct().count(),
            "teachers_count": assignments.values("teacher").distinct().count(),
            "overcapacity_classes": overcapacity_classes,
        },
    )


def _smart_schedule_redirect(year):
    """العودةُ إلى صفحة الجدولة للعام نفسِه الذي طُلب التوليدُ له.

    كان الردُّ `redirect("smart_schedule")` بلا عام، فتُفتح الصفحةُ على العام
    الافتراضيّ: من ولّد جدولَ العام القادم يرى سجلَّ توليدِ عامٍ آخر — ولا يرى
    مسودّتَه، ولا الرقمَ الذي يقول كم حصّةً وُضعت.
    """
    return redirect(f"{reverse('smart_schedule')}?{urlencode({'year': year})}")


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
@require_POST
def smart_generate(request):
    """يضع التوليدَ في الطابور — ولا يُولّد داخل الطلب.

    قِيس زمنُ التوليد في هذه المدرسة على ثلاثةٍ وثلاثين عمليّةً فكان بين
    ٤٢ ثانيةً و٢٧٩، و`gunicorn` يقطع الطلبَ عند مئةٍ وعشرين ثانيةً و`nginx`
    مثلَه. فالزرُّ المتزامنُ كان يَعِد بجدولٍ ويُسلّم «502» بعد دقيقتين،
    والتوليدُ يمضي في عاملٍ لا أحدَ ينتظره.

    والصفُّ يُنشأ هنا قبل الإرسال لا في العامل: هو ما يراه المستخدمُ حالةً،
    وهو ما يمنع توليداً ثانياً فوق جارٍ.
    """
    school = request.user.get_school()
    year = request.POST.get("year") or academic_year_for(request)

    # حارسُ التزامن — توليدان متوازيان يتنازعان جدولاً واحداً، وآخرُهما يفوز
    # بلا أن يعلم أحدٌ أنّ أوّلَهما كان.
    running = _reap_stale_generations(school, year)
    if running is not None:
        messages.info(
            request,
            "هناك توليدٌ جارٍ لهذا العام — انتظر انتهاءَه قبل أن تبدأ آخر.",
        )
        return _smart_schedule_redirect(year)

    generation = ScheduleGeneration.objects.create(
        school=school,
        academic_year=year,
        generated_by=request.user,
        status="queued",
    )

    from .tasks import generate_smart_schedule_task

    try:
        generate_smart_schedule_task.delay(str(generation.id))
    except Exception as exc:  # وسيطُ الرسائل ساقطٌ أو غيرُ مهيّأ
        # ولا يُترك الصفُّ «في الانتظار» إلى الأبد: انتظارٌ بلا عاملٍ كذبةٌ
        # صامتة. يُقال إنّ العاملَ غيرُ متاح، ويُقال ماذا يفعل المسؤول.
        logger.exception("تعذّر إرسال مهمّة توليد الجدول: %s", exc)
        generation.status = "failed"
        # سببُ السقوط في السجلّ أعلاه؛ والمعروضُ للمستخدم ما يفعله لا ما رآه النظام.
        generation.error_message = "تعذّر إرسال المهمّة إلى عامل الخلفيّة — راجع تشغيل Celery."
        generation.finished_at = timezone.now()
        generation.save(update_fields=["status", "error_message", "finished_at"])
        messages.error(
            request,
            "عاملُ المهامّ الخلفيّة غيرُ متاح، ولم يبدأ التوليد. " "راجع تشغيل Celery ثمّ أعد المحاولة.",
        )
        return _smart_schedule_redirect(year)

    messages.success(
        request,
        "بدأ توليد الجدول في الخلفيّة — تُحدَّث الحالةُ في هذه الصفحة تلقائيّاً، "
        "ويصلك إشعارٌ عند انتهائه.",
    )
    return _smart_schedule_redirect(year)


@login_required
@role_required(_ADMIN_SCHEDULE_ROLES)
def smart_generate_status(request):
    """حالةُ آخر توليدٍ — تسألها الصفحةُ كلَّ بضع ثوانٍ ما دام هناك جارٍ.

    وحدُّ ما تُرجعه مقصود: حالةٌ ونصٌّ مختصر. فصفحةٌ تُعيد تحميلَ نفسها كلَّ
    ثلاثِ ثوانٍ على مئاتِ الصفوف تُثقل الخادمَ لتقول «ما زال يعمل».
    """
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    # ما تقادم لا يُقال عنه «جارٍ» — وإلّا استطلعت الصفحةُ إلى الأبد.
    _reap_stale_generations(school, year)

    generation = (
        ScheduleGeneration.objects.filter(school=school, academic_year=year)
        .only(
            "id",
            "status",
            "quality_score",
            "total_slots_created",
            "generation_time_ms",
            "error_message",
        )
        .first()
    )
    if generation is None:
        return JsonResponse({"status": None, "pending": False})

    return JsonResponse(
        {
            "id": str(generation.id),
            "status": generation.status,
            "status_label": generation.get_status_display(),
            "pending": generation.is_pending,
            "quality": round(generation.quality_score),
            "slots": generation.total_slots_created,
            "elapsed_ms": generation.generation_time_ms,
            "error": generation.error_message,
        }
    )


@login_required
@role_required(_REPORT_ROLES)
def teacher_load_report(request):
    """تقرير أحمال المعلمين"""
    from core.permissions import get_department_teacher_ids

    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    dept_ids = get_department_teacher_ids(request.user)
    if dept_ids is not None:
        teachers = CustomUser.objects.filter(id__in=dept_ids).order_by("full_name")
    else:
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator", "ese_teacher")
        ).values_list("user_id", flat=True)
        teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    # ✅ v5.4: TeacherLoadService.get_teacher_load_data — business logic في service layer
    from operations.services import TeacherLoadService

    data = TeacherLoadService.get_teacher_load_data(school, year, teachers)

    return render(
        request,
        "schedule/teacher_load.html",
        {
            "year": year,
            **data,
        },
    )


# ── تفضيلات المعلم ──────────────────────────────────────────────


@login_required
@role_required("teacher", "ese_teacher", "coordinator", "activities_coordinator")
def teacher_preferences(request):
    """صفحة تفضيلات المعلم للجدولة الذكية"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    pref, _created = TeacherPreference.objects.get_or_create(
        teacher=request.user,
        school=school,
        academic_year=year,
    )

    if request.method == "POST":
        # القيمُ من قائمةٍ مغلقة، و`int()` على نصٍّ حرٍّ يُسقط الصفحةَ بـ500
        # ويقبل ما لا معنى له. فما خرج عن المدى يعود إلى الافتراضيّ.
        pref.max_daily_periods = _one_of(request.POST.get("max_daily_periods"), range(1, 8), 5)
        #: و«حصّةٌ واحدة» سقفٌ مشروع: أي لا حصّتين متجاورتين البتّة — وهو
        #: قيدٌ قائمٌ لمعلّمٍ في المدرسة، والمحرّكُ يقرؤه ولا يرفعه في الاسترخاء.
        pref.max_consecutive = _one_of(request.POST.get("max_consecutive"), range(1, 8), 3)
        #: سقفُ الفراغ اختياريّ: الفراغُ لعامّة الكادر ترجيحٌ مرن، ومن اختار
        #: سقفاً صار في حقّه قيداً صلباً. فالفراغُ نصّاً لا يُقرأ افتراضيّاً
        #: بل يُقرأ عدماً — و«0» قيمةٌ صحيحةٌ تعني «لا فراغَ البتّة».
        max_gap = request.POST.get("max_gap", "")
        pref.max_gap = _one_of(max_gap, range(0, 6), None) if max_gap != "" else None
        free_day = request.POST.get("free_day", "")
        pref.free_day = _one_of(free_day, range(0, 5), None) if free_day else None
        pref.notes = request.POST.get("notes", "")
        pref.save()
        messages.success(request, "تم حفظ تفضيلاتك للجدولة الذكية")
        return redirect("teacher_preferences")

    return render(
        request,
        "schedule/teacher_preferences.html",
        {
            "pref": pref,
            "days": ScheduleSlot.DAYS,
            "year": year,
        },
    )


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

    from notifications.models import InAppNotification

    teacher_ids = Membership.objects.filter(
        school=school,
        is_active=True,
        role__name__in=("teacher", "coordinator", "ese_teacher", "activities_coordinator"),
    ).values_list("user_id", flat=True)

    # الاعتمادُ والإشعارُ فعلٌ واحد. كان الحفظُ يسبق `bulk_create` بلا معاملة،
    # فحين سقط الإدراجُ بقي الجدولُ «معتمَداً» ولم يعلم به معلّمٌ واحد — نصفُ
    # فعلٍ لا يُرى نصفُه الناقص.
    with transaction.atomic():
        # الاعتمادُ هو النشر: حصصُ هذه المسودّة تُفعَّل ويُطفأ ما سواها في
        # العام نفسه. وكان الاعتمادُ يقلب حقلَ حالةٍ لا غير، والحصصُ حيّةٌ
        # منذ لحظة التوليد — فلم يكن الزرُّ يقرّر شيئاً.
        #
        # والمسودّاتُ الأقدمُ من هذا الحقل حصصُها حيّةٌ أصلاً وبلا مرجع توليد،
        # فإطفاءُ الحيّ لها يمحو الجدولَ كلَّه: تُعامَل كما كانت — قلبَ حالةٍ.
        draft_slots = ScheduleSlot.objects.filter(generation=gen)
        if draft_slots.exists():
            ScheduleSlot.objects.filter(
                school=school, academic_year=gen.academic_year, is_active=True
            ).exclude(generation=gen).update(is_active=False)
            draft_slots.update(is_active=True)

        ScheduleGeneration.objects.filter(
            school=school, academic_year=gen.academic_year, status="approved"
        ).update(status="archived")

        gen.status = "approved"
        gen.save(update_fields=["status"])

        # `school` لازمٌ لا زينة: الإشعارُ صفٌّ مستأجِرٌ تحرسه RLS، وصفٌّ بلا
        # مدرسةٍ ترفضه السياسةُ fail-closed — فتسقط العمليّةُ كلُّها.
        notifs = [
            InAppNotification(
                user_id=tid,
                school=school,
                title="تم اعتماد الجدول الدراسي",
                body=(
                    f"تم اعتماد الجدول للعام {gen.academic_year}. "
                    "راجع جدولك من صفحة الجدول الأسبوعي."
                ),
                event_type="general",
                priority="medium",
                related_url="/teacher/weekly-schedule/",
            )
            for tid in teacher_ids
        ]
        InAppNotification.objects.bulk_create(notifs)

    messages.success(request, f"تم اعتماد الجدول وإشعار {len(notifs)} معلم")
    return redirect("smart_schedule")


def _one_of(raw, allowed, fallback):
    """رقمٌ من مدىً مغلق — وما خرج عنه يعود إلى الافتراضيّ بلا سقوط."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value in allowed else fallback


# ── إعدادات الجدول — النائب الأكاديمي ───────────────────────────


@login_required
@role_required("principal", "vice_academic")
def schedule_settings(request):
    """إعدادات الجدول الذكي — تفريغات المعلمين + حصص مزدوجة"""
    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)

    # الشاشةُ للتفريغات وحدَها. والقيودُ الشخصيّةُ الدائمةُ — «لا أولى ولا
    # سابعة» — تسكن الجدولَ نفسَه لأنّ المولّدَ لا يقرأ غيرَه، وليست منه:
    # التفريغُ غيابٌ لسببٍ خارجيٍّ له مرجعٌ وتاريخ، وتلك صفةٌ لازمة.
    active = TeacherExemption.objects.filter(
        school=school, academic_year=year, is_active=True
    ).select_related("teacher", "created_by")
    exemptions = active.releases()
    # القيودُ الشخصيّةُ الدائمة — «لا أولى ولا سابعة» — تُميَّز اليوم بنصّ السبب
    # لا بحقلٍ صريح. وكانت تُستبعد من الشاشة كلّيّاً بينما المولّدُ يقرؤها
    # ويقيّد بها الجدول: قيودٌ لا يراها أحد ولا يستطيع أحدٌ حذفَها. فتُعرض في
    # قسمها، لا تُخفى.
    personal_rules = active.exclude(pk__in=exemptions.values("pk"))
    subjects = Subject.objects.filter(school=school).order_by("name_ar")
    teacher_prefs = (
        TeacherPreference.objects.filter(school=school, academic_year=year)
        .select_related("teacher")
        .order_by("teacher__full_name")
    )

    # قائمة المعلمين لإضافة تفريغ
    teacher_ids = Membership.objects.filter(
        school=school,
        is_active=True,
        role__name__in=("teacher", "coordinator", "ese_teacher", "activities_coordinator"),
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")

    return render(
        request,
        "schedule/schedule_settings.html",
        {
            "exemptions": exemptions,
            "personal_rules": personal_rules,
            "subjects": subjects,
            "teacher_prefs": teacher_prefs,
            "teachers": teachers,
            "days": ScheduleSlot.DAYS,
            "periods": ScheduleSlot.PERIODS,
            "year": year,
        },
    )


@login_required
@role_required("principal", "vice_academic")
@require_POST
def add_exemption(request):
    """إضافة تفريغ معلم — POST.

    المدخلاتُ تمرّ على `TeacherExemptionForm` أوّلاً: هي التي تقيّد المعلّمَ
    بمدرسة المُدخِل، وتحوّل الأرقامَ، وتردّ الناقصَ رسالةً لا صفحةَ خطأ.
    """
    from .forms import TeacherExemptionForm

    school = request.user.get_school()
    year = request.POST.get("year") or academic_year_for(request)

    form = TeacherExemptionForm(request.POST, school=school)
    if not form.is_valid():
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            for error in errors:
                messages.error(request, f"{label}: {error}" if label else error)
        return _safe_schedule_settings_redirect(request, year)

    data = form.cleaned_data
    teacher = data["teacher"]

    # ✅ v5.4: ScheduleService.create_exemption — atomic + logging
    try:
        ScheduleService.create_exemption(
            school=school,
            teacher=teacher,
            academic_year=year,
            exemption_type=data["exemption_type"],
            day_of_week=data["day_of_week"],
            period_number=data["period_number"],
            reason=data["reason"],
            created_by=request.user,
            source=data["source"],
            source_reference=data["source_reference"],
        )
    except DjangoValidationError as exc:
        # تفريغُ يومٍ كاملٍ قرارٌ إداريّ — ورفضُه يُقال، ولا يصير 500.
        messages.error(request, "؛ ".join(exc.messages))
    else:
        messages.success(request, f"تم تفريغ {teacher.full_name}")
    return _safe_schedule_settings_redirect(request, year)


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
    return _safe_schedule_settings_redirect(
        request,
        exemption.academic_year,
    )


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
    return _safe_schedule_settings_redirect(request)


# ── توزيعات المواد على الشُّعب — وقودُ المولّد ────────────────────


def _assignment_redirect(year, class_id=""):
    query = {"year": year}
    if class_id:
        query["class"] = class_id
    return redirect(f"{reverse('subject_assignments')}?{urlencode(query)}")


@login_required
@role_required(SCHEDULE_MANAGE_ROLES)
def subject_assignments(request):
    """قائمةُ التوزيعات واستمارةُ الإضافة — وكلُّ صفٍّ يُعدَّل في مكانه."""
    from .forms import SubjectClassAssignmentForm

    school = request.user.get_school()
    year = request.GET.get("year") or academic_year_for(request)
    class_id = request.GET.get("class", "")

    qs = SubjectClassAssignment.objects.filter(
        school=school, academic_year=year, is_active=True
    ).select_related("class_group", "subject", "teacher")
    if class_id:
        qs = qs.filter(class_group_id=class_id)
    # من 7/1 إلى 12/4 — ترتيبُ المدرسة لا ترتيبُ الحروف الذي يُقدّم «العاشر» على «السابع».
    qs = qs.order_by(grade_order("class_group__grade"), "class_group__section", "subject__name_ar")
    assignments = list(qs)
    teachers = list(CustomUser.objects.teachers(school).order_by("full_name"))

    # معلّمٌ مُسنَدٌ وليس في القائمة (دورٌ خارج الأدوار المدرِّسة، أو عضويّةٌ
    # أُطفئت) يُعرض باسمه لا «بلا معلّم»: فالرأسُ يعدّه مُسنَداً والقائمةُ لا
    # تعرفه، وكان حفظُ الصفّ على هذه الحال يُرسل معلّماً فارغاً فيمحوه بصمت.
    listed = {t.id for t in teachers}
    for a in assignments:
        a.teacher_outside_list = a.teacher_id is not None and a.teacher_id not in listed

    # استمارةٌ أُعيدت بأخطائها: تُعرض بما كُتب فيها، لا فارغةً.
    rejected = request.session.pop("assignment_form_data", None)
    form = SubjectClassAssignmentForm(rejected or None, school=school, year=year)
    if rejected:
        form.is_valid()

    return render(
        request,
        "schedule/subject_assignments.html",
        {
            "year": year,
            "assignments": assignments,
            "form": form,
            "classes": form.fields["class_group"].queryset,
            "teachers": teachers,
            "selected_class_id": class_id,
            "totals": {
                "count": len(assignments),
                "periods": sum(a.weekly_periods for a in assignments),
                "unstaffed": sum(1 for a in assignments if a.teacher_id is None),
            },
        },
    )


@login_required
@role_required(SCHEDULE_MANAGE_ROLES)
@require_POST
def subject_assignment_add(request):
    from .forms import SubjectClassAssignmentForm

    school = request.user.get_school()
    year = request.POST.get("year") or academic_year_for(request)
    form = SubjectClassAssignmentForm(request.POST, school=school, year=year)
    if not form.is_valid():
        # تُعاد المدخلاتُ لا تُطمس: يرى المُدخِل ما كتب وما رُفض منه.
        request.session["assignment_form_data"] = {
            k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"
        }
        for err in form.non_field_errors():
            messages.error(request, err)
        return _assignment_redirect(year)
    obj = form.save(commit=False)
    obj.school, obj.academic_year = school, year
    obj.save()
    messages.success(request, f"أُضيف: {obj}")
    return _assignment_redirect(year, str(obj.class_group_id))


@login_required
@role_required(SCHEDULE_MANAGE_ROLES)
@require_POST
def subject_assignment_edit(request, assignment_id):
    """تعديلُ الصفّ في مكانه: المعلّم والحصص والمعمل والتوازي — لا الشعبةُ ولا المادّة."""
    school = request.user.get_school()
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, school=school, is_active=True)
    year = obj.academic_year

    teacher_id = request.POST.get("teacher") or None
    teacher = None
    if teacher_id and obj.teacher_id and teacher_id == str(obj.teacher_id):
        # لم يتغيّر — فلا يُعاد التحقّق: معلّمٌ خارج القائمة يبقى ولا يُمحى
        # لأنّ المُدخِل عدّل الحصصَ أو المعمل. أمّا الفراغُ الصريح فتفريغٌ مقصود.
        teacher = obj.teacher
    elif teacher_id:
        teacher = CustomUser.objects.teachers(school).filter(pk=teacher_id).first()
        if teacher is None:
            messages.error(request, "المعلّم المختار ليس من معلّمي مدرستك.")
            return _assignment_redirect(year, str(obj.class_group_id))
    try:
        periods = int(request.POST.get("weekly_periods", obj.weekly_periods))
    except (TypeError, ValueError):
        periods = 0
    if not 1 <= periods <= 35:
        messages.error(request, "عدد الحصص الأسبوعيّة يجب أن يكون بين ١ و٣٥.")
        return _assignment_redirect(year, str(obj.class_group_id))

    obj.teacher = teacher
    obj.weekly_periods = periods
    obj.requires_lab = bool(request.POST.get("requires_lab"))
    obj.parallel_group = (request.POST.get("parallel_group") or "").strip()[:40]
    obj.save(update_fields=["teacher", "weekly_periods", "requires_lab", "parallel_group"])
    messages.success(request, f"حُفظ: {obj}")
    return _assignment_redirect(year, str(obj.class_group_id))


@login_required
@role_required(SCHEDULE_MANAGE_ROLES)
@require_POST
def subject_assignment_delete(request, assignment_id):
    """حذفٌ ناعم — يبقى الصفُّ أثراً، ويخرج من عين المولّد."""
    school = request.user.get_school()
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, school=school, is_active=True)
    obj.is_active = False
    obj.save(update_fields=["is_active"])
    messages.success(request, f"حُذف توزيع {obj.subject.name_ar} لشعبة {obj.class_group}.")
    return _assignment_redirect(obj.academic_year, str(obj.class_group_id))
