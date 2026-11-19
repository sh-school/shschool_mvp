"""[CLINIC] W-20261119-003: قراءةُ شاشة «بطاقة الخروج» للممرّض والأخصائيّ — من خرج إلى العيادة الآن، ومن وُسم.

لا سببَ زيارةٍ هنا: القراءةُ من `ClassExit` (لحظاتٌ ووجهة) و`ExcusedExit` (وسمٌ بمدّة)، وسببُ الوسم لا يُقرأ إلا لواضعه.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import ValidationError

from core.labels import class_label
from core.models import CustomUser
from operations.models import ClassExit, ExcusedExit


def clinic_exits(school: Any, day: dt.date) -> list[dict[str, Any]]:
    """خروجُ اليوم المفتوحُ إلى العيادة، الأقدمُ أوّلاً — ومعه لحظتا الوصول والمغادرة إن سُجّلتا."""
    qs = (
        ClassExit.objects.filter(
            school=school, session__date=day, destination="clinic", returned_at__isnull=True
        )
        .select_related("student", "session__class_group")
        .order_by("left_at")
    )
    return [
        {
            "pk": e.pk,
            "student": e.student,
            "class_text": class_label(e.session.class_group.grade, e.session.class_group.section),
            "left_at": e.left_at,
            "arrived": e.clinic_arrived_at,
            "departed": e.clinic_left_at,
        }
        for e in qs
    ]


def marks_set_by(school: Any, user: Any, day: dt.date) -> list[dict[str, Any]]:
    """الوسومُ السارية التي وضعها هذا المستخدمُ نفسُه — لا وسمَ غيره ولا سببَه."""
    qs = (
        ExcusedExit.objects.filter(school=school, set_by=user, ends_on__gte=day)
        .select_related("student")
        .order_by("ends_on")
    )
    return [{"student": m.student, "starts_on": m.starts_on, "ends_on": m.ends_on} for m in qs]


def student_in_school(school: Any, student_id: Any) -> CustomUser | None:
    """الطالبُ بمعرّفه إن كان مقيَّداً نشطاً في المدرسة، وإلا `None` (معرّفٌ فاسدٌ أو من مدرسةٍ أخرى)."""
    try:
        return (
            CustomUser.objects.filter(
                enrollments__is_active=True, enrollments__class_group__school=school
            )
            .distinct()
            .filter(pk=student_id)
            .first()
        )
    except (ValueError, TypeError, ValidationError):
        return None
