"""[CLINIC] W-20261119-003: كتابةُ شاشة «بطاقة الخروج» — لحظتا العيادة ووسمُ الخروج المبرَّر، فوق `operations.exit_wing`.

وحدةٌ رقيقةٌ تجمع الاستعلامَ بالمدرسة والتحقّقَ والكتابةَ في نداءٍ واحدٍ للعرض. لا أسماءَ ولا أسبابَ في السجلّات.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from clinic.exit_selectors import student_in_school
from operations import exit_wing
from operations.models import ClassExit

MOMENTS = ("arrive", "depart")


def press_moment(school: Any, exit_id: Any, step: str, user: Any) -> bool | None:
    """«وصل العيادة» أو «غادر»: `None` إن لم يكن الخروجُ في هذه المدرسة (404)، وإلا هل سجّلت هذه النقرةُ اللحظة."""
    if not ClassExit.objects.filter(school=school, pk=exit_id).exists():
        return None
    act = exit_wing.clinic_arrive if step == "arrive" else exit_wing.clinic_depart
    return act(exit_id, user)


def excuse_student(school: Any, user: Any, student_id: Any, ends_raw: str, reason: str) -> None:
    """يضع الوسمَ — `ValueError` برسالةٍ للمستخدم إن كان الطالبُ غريباً أو التاريخُ فاسداً أو السببُ فارغاً."""
    student = student_in_school(school, student_id)
    if student is None:
        raise ValueError("طالبٌ غيرُ موجود.")
    try:
        ends_on = dt.date.fromisoformat(ends_raw)
    except ValueError:
        raise ValueError("اكتب تاريخَ نهايةٍ صحيحاً.") from None
    exit_wing.set_excused(school, student, user, ends_on, reason)
