"""شاشةُ أجنحة المدرسة — طابقان، خمسةُ أجنحة، وجرسٌ يُقرأ بالساعة."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required
from core.models import ClassGroup, CustomUser, Wing, WingCoverage
from operations.absence_policy import next_gate
from operations.absence_standing import unexcused_days_for_class
from operations.bells import day_type_for
from operations.day_attendance import enrolled_of
from operations.models import StudentAttendance
from operations.period_register import (
    absent_yesterday,
    cells_of,
    confirm_period,
    focus_period,
    periods_of,
)
from operations.services import ScheduleService

from .services import (
    bell_tables,
    coverage_rows,
    floors_overview,
    outside_the_wings,
    record_panels,
    substitute_pool,
    wings_of,
)

DAY_LABEL = {"regular": "الأحد – الأربعاء", "thursday": "الخميس"}


@login_required
@capability_required("wings.floors")
def floors(request):
    school = request.user.get_school()
    now = timezone.localtime()
    year = academic_year_for_school(school)
    day_type = day_type_for(now.date())

    panels = floors_overview(school, year, now)
    outside = outside_the_wings(school, year)
    wing_students = sum(panel.student_count for panel in panels)
    return render(
        request,
        "wings/floors.html",
        {
            "panels": panels,
            "tables": bell_tables(school),
            "now": now,
            "year": year,
            "day_label": DAY_LABEL.get(day_type, "عطلة — لا دوام"),
            "is_school_day": bool(day_type),
            "wing_count": sum(len(panel.wings) for panel in panels),
            "section_count": sum(panel.section_count for panel in panels),
            "student_count": wing_students,
            "outside": outside,
            "perms_can_cover": request.user.is_superuser
            or request.user.get_role() in WingCoverage.ASSIGNER_ROLES,
            # سجلُّ المدرسة كلُّه — والفرقُ بينه وبين طلاب الأجنحة معروضٌ لا مطروح.
            "register_count": wing_students + outside.student_count,
        },
    )


def _day(raw, fallback=None):
    """تاريخٌ من نصّ — وما لا يُقرأ يرتدّ إلى بديلٍ لا يُسقط الطلب."""
    try:
        return dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return fallback


@login_required
@capability_required("wings.assign_cover")
def coverage(request):
    """تغطيةُ الأجنحة — من يحمل كلَّ جناحٍ اليوم، ومن يُناب عند الغياب.

    وصلاحيّتُها للمدير والنائبين ومطوّر المنصّة: لوحةُ إدارة جانغو مقصورةٌ على
    المدير والمطوّر بقرار المدرسة، فبلا هذه الشاشة لا يستطيع النائبان تعيينَ
    بديلٍ — وهما اثنان من الأربعة الذين أذن لهم المدير.
    """
    school = request.user.get_school()
    year = academic_year_for_school(school)
    today = timezone.localdate()
    return render(
        request,
        "wings/coverage.html",
        {
            "rows": coverage_rows(school, year, today),
            "pool": substitute_pool(school, on_date=today),
            "today": today,
            "year": year,
        },
    )


@login_required
@capability_required("wings.assign_cover")
@require_POST
def coverage_assign(request, code):
    school = request.user.get_school()
    year = academic_year_for_school(school)
    wing = get_object_or_404(Wing, school=school, code=code, academic_year=year)
    today = timezone.localdate()

    substitute = CustomUser.objects.filter(id=request.POST.get("substitute") or None).first()
    if substitute is None:
        messages.error(request, "اختر البديل.")
        return redirect("wings:coverage")

    cover = WingCoverage(
        wing=wing,
        substitute=substitute,
        assigned_by=request.user,
        reason=request.POST.get("reason") or "absence",
        start_date=_day(request.POST.get("start_date"), today),
        end_date=_day(request.POST.get("end_date")),
        note=(request.POST.get("note") or "").strip(),
    )
    try:
        cover.full_clean()
    except ValidationError as err:
        for field_errors in err.message_dict.values():
            for text in field_errors:
                messages.error(request, text)
        return redirect("wings:coverage")

    cover.save()
    until = f"حتّى {cover.end_date}" if cover.end_date else "بلا تاريخِ انتهاء"
    messages.success(
        request, f"{substitute.full_name} يغطّي {wing.name} من {cover.start_date} — {until}."
    )
    return redirect("wings:coverage")


@login_required
@capability_required("wings.assign_cover")
@require_POST
def coverage_end(request, pk):
    """إنهاءُ التغطية — بتاريخٍ لا بحذف.

    الحذفُ يمحو من حمل الجناحَ أمسِ، ومن يقرأ غيابَ الأسبوع الماضي يحتاج أن
    يعرف من كان يرصده. فتُغلق المدّةُ ويبقى السجلّ.
    """
    school = request.user.get_school()
    cover = get_object_or_404(WingCoverage, pk=pk, wing__school=school)
    today = timezone.localdate()
    cover.end_date = max(_day(request.POST.get("end_date"), today), cover.start_date)
    cover.ended_by = request.user
    cover.save(update_fields=["end_date", "ended_by"])
    messages.success(
        request,
        f"انتهت تغطيةُ {cover.substitute.full_name} لـ{cover.wing.name} في {cover.end_date}.",
    )
    return redirect("wings:coverage")


@login_required
@capability_required("wings.record_day")
def record_index(request):
    """شُعبي اليومَ وحالُ رصدِها — «شُعبي المتبقّية n/5»."""
    school = request.user.get_school()
    year = academic_year_for_school(school)
    day = _day(request.GET.get("date"), timezone.localdate())

    # الحصصُ تُولَّد إن لم تكن — فشعبةٌ بلا حصصٍ لا تُرصد.
    ScheduleService.ensure_sessions_for_date(school, day)

    # العدُّ في الخدمة لا في القالب: `add` في جانغو لا تطرح، فحسابُ
    # «المتبقّية» هناك كان يُخرج صفراً دائماً.
    panels = record_panels(request.user, school, year, day)
    return render(
        request,
        "wings/record_index.html",
        {
            "panels": panels,
            "day": day,
            "today": timezone.localdate(),
            "day_type": day_type_for(day),
        },
    )


def _time(raw):
    try:
        return dt.time.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _own_class(request, class_id):
    """شعبةٌ من أجنحة المستخدم وحدَها — والمشرفُ لجناحه فقط (قرارُ 2026-09-13).

    والقيادةُ ترى الأجنحةَ الخمسة (`wings_of`). ومن طلب شعبةَ جناحٍ آخر برابطها
    المباشر يلقى 404 لا 403: وجودُ الشعبة في جناحٍ غيرِه ليس شأنَه.
    """
    school = request.user.get_school()
    klass = get_object_or_404(ClassGroup, id=class_id, school=school)
    year = academic_year_for_school(school)
    if klass.wing_id not in {w.id for w in wings_of(request.user, school, year)}:
        raise Http404("ليست من شُعب جناحك")
    return school, klass


@login_required
@capability_required("wings.record_day")
def record_section(request, class_id):
    """كشفُ الشعبة: الطلابُ صفوفاً، والحصصُ أعمدةً، والحصّةُ المفتوحةُ للرصد.

    تُفتح الحصّةُ الجارية، وإلّا أوّلُ فائتة، وإلّا أوّلُ قادمة — ويُختار غيرُها
    بـ`?p=HH:MM`. وكلُّ طالبٍ بجانبه ما يغيّر قرارَ المشرف في لحظته: «غاب أمس»،
    وأيّامُ غيابه بلا عذرٍ أمام أوّل عتبةٍ لم يتجاوزها.
    """
    school, klass = _own_class(request, class_id)
    day = _day(request.GET.get("date"), timezone.localdate())
    ScheduleService.ensure_sessions_for_date(school, day)

    now = timezone.now()
    periods = periods_of(klass, day)
    wanted = _time(request.GET.get("p"))
    focus = next((p for p in periods if p.start == wanted), None) or focus_period(periods, day, now)
    cells = cells_of(klass, day)
    yesterday = absent_yesterday(klass, day)
    unexcused = unexcused_days_for_class(klass, school, day)

    rows = []
    for enrollment in enrolled_of(klass):
        sid = enrollment.student_id
        days = unexcused.get(sid, 0)
        gate = next_gate(klass.grade, days)
        own = cells.get(sid, {})
        rows.append(
            {
                "student": enrollment.student,
                "track": [(p, own.get(p.start)) for p in periods],
                "cell": own.get(focus.start) if focus else None,
                "absent_yesterday": sid in yesterday,
                "days": days,
                "gate": gate,
            }
        )
    return render(
        request,
        "wings/record_section.html",
        {
            "klass": klass,
            "day": day,
            "periods": [(p, p.status(day, now)) for p in periods],
            "focus": focus,
            "focus_status": focus.status(day, now) if focus else "",
            "measured_now": bool(focus and focus.in_window(day, now)),
            "rows": rows,
            "whereabouts": [w for w in StudentAttendance.WHEREABOUTS if w[0] != "gate"],
            "draft_key": f"rec:{klass.id}:{day.isoformat()}:{focus.key if focus else ''}",
        },
    )


@login_required
@capability_required("wings.record_day")
@require_POST
def record_period(request, class_id):
    """تثبيتُ حصّة — ومعه مخالفتا التأخّر والهروب إن استوجبهما الرصد."""
    school, klass = _own_class(request, class_id)
    day = _day(request.POST.get("date"), timezone.localdate())
    start = _time(request.POST.get("start"))
    back = f"{reverse('wings:record_section', args=[klass.id])}?date={day.isoformat()}"

    marks: dict = {}
    for key, value in request.POST.items():
        for prefix, field in (
            ("s-", "status"),
            ("w-", "whereabouts"),
            ("m-", "late_minutes"),
            ("t-", "tapped_at"),
        ):
            if key.startswith(prefix):
                marks.setdefault(key.removeprefix(prefix), {})[field] = value
    try:
        result = confirm_period(klass, day, start, marks, by=request.user)
    except ValueError as err:
        messages.error(request, str(err))
        return redirect(back)

    messages.success(request, f"ثُبّتت {klass.short_code} — {result.says}.")
    return redirect(back)
