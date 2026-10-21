"""شبكةُ تفضيل موضع الحصّة للمعلّم: قراءتُها وحفظُها وتهيئتُها للعرض (المرحلة أ من W-20261010-032، D-330م).

الحالةُ المحايدةُ لا تُخزَّن (غيابُ الصفّ = محايدة)؛ والمعلّمُ صاحبُ الشبكة هو `request.user` دائماً — لا يُقرأ
معرّفُ معلّمٍ من الطلب فلا يعدّل أحدٌ شبكةَ غيره. ولا يقرؤها أيُّ محرّكٍ بعد: تُحفظ وتُعرض فقط.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from django.db import transaction

from operations.models import ScheduleSlot, TeacherPeriodPreference

#: خانةٌ في الشبكة: `cell_<يوم>_<حصة>` — اليومُ من 0 والحصّةُ من 1.
CELL = re.compile(r"^cell_(\d+)_(\d+)$")
#: علامةُ وجود الشبكة في الطلب: طلبٌ بلا شبكةٍ (صفحةٌ قديمة أو اختبار) لا يمسح ما حُفظ.
GRID_MARKER = "grid_present"
NEUTRAL = ""
STATES = [
    (NEUTRAL, "محايدة"),
    (TeacherPeriodPreference.PREFER, "أفضّلها"),
    (TeacherPeriodPreference.AVOID, "أتجنّبها"),
]
_VALID = {TeacherPeriodPreference.PREFER, TeacherPeriodPreference.AVOID}
_DAYS = {value for value, _label in ScheduleSlot.DAYS}


def stored_grid(teacher: Any, school: Any, academic_year: str) -> dict[tuple[int, int], str]:
    """{(يوم، حصّة) ← حالة} لما حفظه المعلّمُ في العامّ (المحايدةُ غائبة)."""
    rows = TeacherPeriodPreference.objects.filter(
        teacher=teacher, school=school, academic_year=academic_year
    ).values_list("day_of_week", "period_number", "preference")
    return {(day, period): state for day, period, state in rows}


def wanted_from_post(post: Mapping[str, str]) -> dict[tuple[int, int], str]:
    """الخاناتُ المطلوبةُ من الطلب: ما كان خارجَ المدى أو بقيمةٍ مجهولةٍ يُرفض فلا يُخزَّن (يُعامَل محايداً)."""
    wanted: dict[tuple[int, int], str] = {}
    for name, value in post.items():
        match = CELL.match(name)
        if not match or value not in _VALID:
            continue
        day, period = int(match.group(1)), int(match.group(2))
        if day in _DAYS and period in ScheduleSlot.PERIODS:
            wanted[(day, period)] = value
    return wanted


def save_grid(
    teacher: Any,
    school: Any,
    academic_year: str,
    post: Mapping[str, str],
    free_day: int | None = None,
) -> bool:
    """يحفظ شبكةَ المعلّم من الطلب: يُضاف الجديدُ ويُعدَّل المتغيّرُ ويُحذف ما صار محايداً. يُرجع هل كانت في الطلب.

    يوم التفريغ (قرارُ الإدارة D-341م) لا يُعرض للمعلّم ولا يُكتب فيه، وما خُزِّن عليه قبل ذلك يبقى كما هو.
    """
    if GRID_MARKER not in post:
        return False
    wanted = {key: state for key, state in wanted_from_post(post).items() if key[0] != free_day}
    with transaction.atomic():
        mine = TeacherPeriodPreference.objects.filter(
            teacher=teacher, school=school, academic_year=academic_year
        )
        for row in mine:
            if row.day_of_week == free_day:
                continue
            state = wanted.pop((row.day_of_week, row.period_number), None)
            if state is None:
                row.delete()
            elif state != row.preference:
                row.preference = state
                row.save(update_fields=["preference", "updated_at"])
        TeacherPeriodPreference.objects.bulk_create(
            TeacherPeriodPreference(
                teacher=teacher,
                school=school,
                academic_year=academic_year,
                day_of_week=day,
                period_number=period,
                preference=state,
            )
            for (day, period), state in wanted.items()
        )
    return True


def grid_for_template(
    teacher: Any, school: Any, academic_year: str, free_day: int | None = None
) -> list[dict[str, Any]]:
    """أيامُ الأسبوع بحصصها وحالةِ كلٍّ منها، جاهزةً للقالب: [{اليوم، الحصص: [{الرقم، الاسم، الحالة}]}].

    يوم التفريغ يُخفى عن المعلّم كلّياً (D-341م): لا عمودَ له ولا اسمَه في الصفحة.
    """
    stored = stored_grid(teacher, school, academic_year)
    return [
        {
            "day": day,
            "label": label,
            "cells": [
                {
                    "period": period,
                    "name": f"cell_{day}_{period}",
                    "state": stored.get((day, period), NEUTRAL),
                }
                for period in ScheduleSlot.PERIODS
            ],
        }
        for day, label in ScheduleSlot.DAYS
        if day != free_day
    ]
