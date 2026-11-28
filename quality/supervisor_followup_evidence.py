"""قرائنُ آليّةٌ بجانب المؤشرات 1 و2 و3 من «نموذج 19» (W-20261128-006).

أعدادٌ للفترة المحسوبة تُقرأ عند العرض ولا تُخزَّن: لا تملأ التقديرَ ولا تقترحه ولا تُحسب نسبة، ولا أسماءَ طلبة.
تُعرض لمن يملك `quality.supervisor_followup` وحدَه (يقرّره العرض)، ولا تدخل PDF.
بلا فترةٍ أو جناحٍ أو بياناتٍ: «لا قرينة متاحة» لا صفرٌ مضلِّل. عددُ الاستعلامات ثابت.

**تثبيتُ الحضور (المؤشر 1):** المعتمَدُ `PeriodConfirmation` (للأيام السابقة، وهو ما تقرؤه الشاشات) ومعه الرصدُ
المعتمَد `StudentAttendance` من المعلّم أو المشرف (مسارُ جدول الشعبة)، دون صفوف «متأخّر»: فقد تكون تسجيلاً لطالبٍ واحدٍ
لا رصداً للشعبة. والشعبةُ مثبَّتةٌ في يومٍ إن كان لها أحدُهما، واليومُ مكتملٌ إن ثُبّتت كلُّ شُعب الجناح.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db.models import Count, Q

from behavior.models import BehaviorInfraction
from core.academic_calendar import academic_year_for_school
from core.models import CustomUser, School
from core.models.academic import Wing
from operations.models import ClassExit, PeriodConfirmation, StudentAttendance
from operations.school_days import SchoolDays

UNAVAILABLE = "قرينة آلية: لا قرينة متاحة."


def indicator_evidence(
    school: School,
    supervisor: CustomUser,
    start: dt.date | None,
    end: dt.date | None,
) -> dict[int, str]:
    """نصُّ القرينة لكلٍّ من المؤشرات 1 و2 و3."""
    if start is None or end is None or start > end:
        return {1: UNAVAILABLE, 2: UNAVAILABLE, 3: UNAVAILABLE}
    return {
        1: _attendance_days(school, supervisor, start, end),
        2: _class_exits(school, supervisor, start, end),
        3: _infractions(school, supervisor, start, end),
    }


def _wing_section_ids(school: School, supervisor: CustomUser, on: dt.date) -> set[Any]:
    """الشُّعبُ النشطةُ في الجناح الذي يحمله المشرفُ في آخر يومٍ من الفترة."""
    wings = (
        Wing.objects.filter(
            school=school, academic_year=academic_year_for_school(school, on), is_active=True
        )
        .select_related("supervisor")
        .prefetch_related("coverages__substitute", "assignments__user", "class_groups")
    )
    return {
        klass.pk
        for wing in wings
        if supervisor in wing.holders(on)
        for klass in wing.class_groups.all()
        if klass.is_active
    }


def _attendance_days(school: School, supervisor: CustomUser, start: dt.date, end: dt.date) -> str:
    sections = _wing_section_ids(school, supervisor, end)
    if not sections:
        return UNAVAILABLE
    school_days = SchoolDays(school, start, end)
    span = (start + dt.timedelta(days=i) for i in range((end - start).days + 1))
    days = [day for day in span if day in school_days]
    confirmed: set[tuple[Any, dt.date]] = set(
        PeriodConfirmation.objects.filter(
            school=school, class_group_id__in=sections, date__range=(start, end)
        )
        .values_list("class_group_id", "date")
        .order_by()
        .distinct()
    )
    confirmed.update(
        StudentAttendance.objects.filter(
            school=school,
            source__in=("teacher", "supervisor"),
            session__class_group_id__in=sections,
            session__date__range=(start, end),
        )
        .exclude(status="late")
        .values_list("session__class_group_id", "session__date")
        .order_by()
        .distinct()
    )
    if not days or not confirmed:
        return UNAVAILABLE
    full = sum(1 for day in days if all((section, day) in confirmed for section in sections))
    return (
        f"قرينة آلية: أيامٌ ثُبّت فيها حضورُ كلّ شُعب الجناح: {full} من {len(days)} (أيامُ دراسة الفترة)."
    )


def _class_exits(school: School, supervisor: CustomUser, start: dt.date, end: dt.date) -> str:
    """خروجٌ استلمه المشرفُ أو سجّل عودتَه؛ وامتدادُ الجرس يتبع أصلَه فلا يُعدّ مرّتين."""
    rows = list(
        ClassExit.objects.filter(
            Q(routed_by=supervisor) | Q(returned_by=supervisor),
            school=school,
            session__date__range=(start, end),
        ).values_list("pk", "continued_from_id", "late_return_seconds")
    )
    if not rows:
        return UNAVAILABLE
    parents = {pk: parent for pk, parent, _late in rows}

    def root(pk: Any) -> Any:
        while parents[pk] in parents:
            pk = parents[pk]
        return pk

    exits = {root(pk) for pk, _parent, _late in rows}
    late = {root(pk) for pk, _parent, seconds in rows if seconds}
    return (
        f"قرينة آلية: خروجٌ من الصف استلمه أو سجّل عودتَه: {len(exits)}، منه عاد متأخراً: {len(late)}."
    )


def _infractions(school: School, supervisor: CustomUser, start: dt.date, end: dt.date) -> str:
    counts = BehaviorInfraction.objects.filter(
        school=school, reported_by=supervisor, date__range=(start, end)
    ).aggregate(
        total=Count("pk"),
        referred=Count("pk", filter=Q(disciplinary_action_type="social_specialist_referral")),
    )
    if not counts["total"]:
        return UNAVAILABLE
    return (
        f"قرينة آلية: مخالفاتٌ سجّلها: {counts['total']}، "
        f"منها المحالةُ للأخصائي الاجتماعي: {counts['referred']}."
    )
