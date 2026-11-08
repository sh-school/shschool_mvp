"""علامةُ «جديد» و«منقول» بجانب اسم الطالب في جداول الغياب (W-20261108-015).

المصدرُ الواحد: تواريخُ القيد في `StudentEnrollment` والانتقالُ الوارد المكتمل في `StudentTransfer` — لا جدولَ
ثانياً. والنافذةُ ثلاثون يوماً قبل اليوم المعروض؛ ما بعدها طالبٌ عاديّ بلا علامة.
أمّا استبعادُ ما قبل القيد وما بعد المغادرة من العدّ فيمرّ من `StudentEnrollment.objects.on_roll(day)` وحدَه.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any

from core.models.academic import StudentEnrollment
from student_affairs.models import StudentTransfer

MARK_NEW = "جديد"
MARK_MOVED = "منقول"
#: أيّامُ النافذة التي يُعدّ فيها الطالبُ جديداً أو منقولاً.
MARK_WINDOW_DAYS = 30


def enrolment_marks(school: Any, student_ids: Iterable[Any], day: dt.date) -> dict[Any, str]:
    """{الطالب: «جديد» أو «منقول»} لمن قُيّد أو نُقل في الثلاثين يوماً السابقة لـ`day` (شاملةً اليوم)."""
    ids = list(student_ids)
    if not ids:
        return {}
    since = day - dt.timedelta(days=MARK_WINDOW_DAYS)
    base = StudentEnrollment.objects.filter(student_id__in=ids, class_group__school=school)
    rows = base.filter(enrolled_at__gte=since, enrolled_at__lte=day).values_list(
        "student_id", "class_group__academic_year"
    )
    # قيدان في النافذة نفسِها لعامٍ واحد (نقلٌ داخليّ حديث) ⇒ منقول.
    counts: dict[tuple[Any, Any], int] = {}
    for key in rows:
        counts[key] = counts.get(key, 0) + 1
    marks: dict[Any, str] = {}
    if counts:
        # قيدٌ سابقٌ للطالب في العام نفسه ⇒ انتقل بين شعبتين لا قُيّد لأوّل مرّة.
        earlier = set(
            base.filter(enrolled_at__lt=since).values_list(
                "student_id", "class_group__academic_year"
            )
        )
        for key, count in counts.items():
            marks[key[0]] = MARK_MOVED if count > 1 or key in earlier else MARK_NEW
    incoming = StudentTransfer.objects.filter(
        school=school,
        student_id__in=ids,
        direction="in",
        status="completed",
        transfer_date__gte=since,
        transfer_date__lte=day,
    ).values_list("student_id", flat=True)
    for student in incoming:
        marks[student] = MARK_MOVED
    return marks
