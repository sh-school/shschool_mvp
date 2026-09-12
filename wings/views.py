"""شاشةُ أجنحة المدرسة — طابقان، خمسةُ أجنحة، وجرسٌ يُقرأ بالساعة."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser, Wing, WingCoverage
from core.permissions import role_required
from operations.bells import day_type_for
from operations.day_attendance import (
    MORNING_STATES,
    day_state,
    enrolled_of,
    record_day,
    slots_of,
)
from operations.services import ScheduleService

from .services import (
    bell_tables,
    coverage_rows,
    floors_overview,
    outside_the_wings,
    sections_to_record,
    substitute_pool,
    wings_of,
)

DAY_LABEL = {"regular": "الأحد – الأربعاء", "thursday": "الخميس"}


@login_required
@role_required(
    "principal",
    "vice_admin",
    "vice_academic",
    "admin_supervisor",
    "platform_developer",
)
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
@role_required(*WingCoverage.ASSIGNER_ROLES)
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
@role_required(*WingCoverage.ASSIGNER_ROLES)
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
@role_required(*WingCoverage.ASSIGNER_ROLES)
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


#: من يرصد: مشرفُ الجناح (أصيلاً أو بديلاً) والقيادةُ ومطوّرُ المنصّة.
RECORD_ROLES = (
    "admin_supervisor",
    "vice_admin",
    "vice_academic",
    "principal",
    "platform_developer",
)


@login_required
@role_required(*RECORD_ROLES)
def record_index(request):
    """شُعبي اليومَ وحالُ رصدِها — «شُعبي المتبقّية n/5»."""
    school = request.user.get_school()
    year = academic_year_for_school(school)
    day = _day(request.GET.get("date"), timezone.localdate())

    # الحصصُ تُولَّد إن لم تكن — فشعبةٌ بلا حصصٍ لا تُرصد.
    ScheduleService.ensure_sessions_for_date(school, day)

    panels = []
    for wing in wings_of(request.user, school, year):
        rows = sections_to_record(wing, day)
        # العدُّ في العرض لا في القالب: `add` في جانغو لا تطرح، فحسابُ
        # «المتبقّية» هناك كان يُخرج صفراً دائماً.
        done = sum(1 for r in rows if r.is_recorded)
        panels.append(
            {
                "wing": wing,
                "rows": rows,
                "done": done,
                "total": len(rows),
                "remaining": len(rows) - done,
            }
        )
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


@login_required
@role_required(*RECORD_ROLES)
def record_section(request, class_id):
    """رصدُ شعبةٍ ليومٍ كامل — بالاستثناء: يُلمس الغائبُ وحدَه.

    و`POST` يكتب الحالةَ في **كلّ** حصص اليوم (السريان، §0.11) ويثبّت الشعبة.
    """
    school = request.user.get_school()
    klass = get_object_or_404(ClassGroup, id=class_id, school=school)
    day = _day(request.POST.get("date") or request.GET.get("date"), timezone.localdate())
    ScheduleService.ensure_sessions_for_date(school, day)

    if request.method == "POST":
        states = {
            key.removeprefix("s-"): value
            for key, value in request.POST.items()
            if key.startswith("s-") and value in MORNING_STATES
        }
        result = record_day(
            klass, day, states, by=request.user, note=(request.POST.get("note") or "").strip()
        )
        if result.confirmation is None:
            messages.error(
                request,
                f"لا حصصَ لـ{klass.short_code} في {day} — فلا شيءَ يُرصد.",
            )
        else:
            messages.success(request, f"ثُبّتت {klass.short_code}: {result.says}.")
        return redirect(f"{reverse('wings:record_index')}?date={day.isoformat()}")

    state = day_state(klass, day)
    students = [
        {
            "student": e.student,
            "status": state.get(e.student_id, {}).get("status", "present"),
        }
        for e in enrolled_of(klass)
    ]
    return render(
        request,
        "wings/record_section.html",
        {
            "klass": klass,
            "day": day,
            "students": students,
            "periods": slots_of(klass, day),
            "already": bool(state),
        },
    )
