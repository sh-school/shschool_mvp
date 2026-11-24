"""[CLINIC] W-20261119-003: كتابةُ شاشة «بطاقة الخروج» — لحظتا العيادة ووسمُ الخروج المبرَّر، فوق `operations.exit_wing`.

وحدةٌ رقيقةٌ تجمع الاستعلامَ بالمدرسة والتحقّقَ والكتابةَ في نداءٍ واحدٍ للعرض. لا أسماءَ ولا أسبابَ في السجلّات.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError

from clinic.exit_selectors import student_in_school
from core.models import CustomUser
from operations import exit_wing
from operations.models import ClassExit

MOMENTS = ("arrive", "depart")


def press_moment(school: Any, exit_id: Any, step: str, user: Any) -> bool | None:
    """«وصل العيادة» أو «غادر»: `None` إن لم يكن الخروجُ في هذه المدرسة (404)، وإلا هل سجّلت هذه النقرةُ اللحظة."""
    if not ClassExit.objects.filter(school=school, pk=exit_id).exists():
        return None
    act = exit_wing.clinic_arrive if step == "arrive" else exit_wing.clinic_depart
    return act(exit_id, user)


def receive_arrival(school: Any, exit_id: Any, user: Any) -> CustomUser | None:
    """«استلام» من «قادمون إليك»: يسجّل الوصولَ (متساوي الأثر) ويُرجع الطالبَ؛ `None` إن لم يكن الخروجُ مفتوحاً إلى العيادة في هذه المدرسة."""
    try:
        row = (
            ClassExit.objects.select_related("student")
            .filter(school=school, pk=exit_id, destination="clinic", returned_at__isnull=True)
            .first()
        )
    except (ValueError, TypeError, ValidationError):
        return None
    if row is None:
        return None
    exit_wing.clinic_arrive(row.pk, user)
    return row.student


def depart_on_close(school: Any, student_id: Any, day: dt.date, user: Any) -> bool:
    """إغلاقُ الزيارة يسجّل «غادر» على خروج الطالب المفتوح إلى العيادة اليوم إن كان قد وصل؛ لا يكتب returned_at أبداً (ق8)."""
    pk = (
        ClassExit.objects.filter(
            school=school,
            student_id=student_id,
            session__date=day,
            destination="clinic",
            returned_at__isnull=True,
            clinic_arrived_at__isnull=False,
        )
        .values_list("pk", flat=True)
        .first()
    )
    return pk is not None and exit_wing.clinic_depart(pk, user)


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
