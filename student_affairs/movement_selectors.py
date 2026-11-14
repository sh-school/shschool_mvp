"""[STUDENT_AFFAIRS] W-20261114-009: قراءةُ لوحة «خارج الفصل الآن» وسجلّ الخروج التاريخي.

القراءةُ من `ClassExit` وحدها (لا نسخةٌ ثانية)، ومضيَّقةٌ بنطاق `_followup_scope`
(مشرفُ الجناح جناحَه، والقيادةُ المدرسةَ).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from core.labels import class_label
from operations.models import ClassExit

#: من تجاوزت غيبتُه هذا العددَ من الدقائق يُبرَز بلون التنبيه في اللوحة الحيّة.
ALERT_MINUTES = 15

_DESTINATION_LABELS = dict(ClassExit.DESTINATIONS)


def _minutes(start: dt.datetime, end: dt.datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def live_rows(school: Any, scope: Any, day: dt.date, now: dt.datetime) -> list[dict[str, Any]]:
    """من خرج في `day` ولم يعد بعد — الأطولُ غياباً أولاً، وفيهم من تجاوز `ALERT_MINUTES`."""
    qs = scope.narrow(
        ClassExit.objects.filter(school=school, session__date=day, returned_at__isnull=True)
    ).select_related("student", "session__class_group")
    rows = []
    for e in qs:
        minutes = _minutes(e.left_at, now)
        group = e.session.class_group
        rows.append(
            {
                "student": e.student,
                "class_text": class_label(group.grade, group.section),
                "destination": _DESTINATION_LABELS.get(e.destination, e.destination),
                "left_at": timezone.localtime(e.left_at),
                "minutes": minutes,
                "alert": minutes > ALERT_MINUTES,
            }
        )
    rows.sort(key=lambda r: r["minutes"], reverse=True)
    return rows


def history_rows(
    school: Any, scope: Any, start: dt.date, end: dt.date, student_id: Any = None
) -> list[dict[str, Any]]:
    """سطرٌ لكلّ طالب: عددُ خروجه ومجموعُ دقائقه، وتفصيلُهما بالوجهة. الخروجُ المفتوح يُعدّ مرّةً بلا دقائق."""
    qs = scope.narrow(
        ClassExit.objects.filter(school=school, session__date__range=(start, end))
    ).select_related("student")
    if student_id:
        qs = qs.filter(student_id=student_id)
    by_student: dict[Any, dict[str, Any]] = {}
    for e in qs:
        row = by_student.setdefault(
            e.student_id,
            {"student": e.student, "count": 0, "minutes": 0, "by_destination": {}},
        )
        mins = _minutes(e.left_at, e.returned_at) if e.returned_at else 0
        row["count"] += 1
        row["minutes"] += mins
        cell = row["by_destination"].setdefault(e.destination, [0, 0])
        cell[0] += 1
        cell[1] += mins
    rows = list(by_student.values())
    for row in rows:
        cells = row["by_destination"]
        row["destinations"] = [
            {"label": label, "count": cells[code][0], "minutes": cells[code][1]}
            for code, label in ClassExit.DESTINATIONS
            if code in cells
        ]
    rows.sort(key=lambda r: (-r["minutes"], -r["count"]))
    return rows
