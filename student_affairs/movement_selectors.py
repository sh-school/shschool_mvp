"""[STUDENT_AFFAIRS] W-20261114-009: قراءةُ لوحة «خارج الفصل الآن» وسجلّ الخروج التاريخي.

القراءةُ من `ClassExit` وحدها (لا نسخةٌ ثانية)، ومضيَّقةٌ بنطاق `_followup_scope`
(مشرفُ الجناح جناحَه، والقيادةُ المدرسةَ).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from core.labels import class_label
from operations.exit_card import GRACE_DESTINATIONS
from operations.models import ClassExit, ExitDestinationGrace

_DESTINATION_LABELS = dict(ClassExit.DESTINATIONS)

#: من بلغ هذا الكسرَ من مهلته يُلوَّن بالتحذير قبل أن يتأخّر.
WARN_FRACTION = 0.8


def _minutes(start: dt.datetime, end: dt.datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def _tone(minutes: int, allowed: int | None) -> str:
    """لونُ «خارج الآن» بالمهلة: بلا مهلةٍ محايد، ثمّ سليمٌ فتحذيرٌ فمتأخّر."""
    if allowed is None:
        return "info"
    if minutes > allowed:
        return "danger"
    return "warning" if minutes >= allowed * WARN_FRACTION else "success"


def grace_rows(school: Any) -> list[tuple[str, str, int | None]]:
    """مُهَلُ الوجهات القابلة للضبط للعرض: (رمز، اسم، دقائق أو None)."""
    graces = dict(
        ExitDestinationGrace.objects.filter(school=school).values_list("destination", "minutes")
    )
    return [(code, label, graces.get(code)) for code, label in GRACE_DESTINATIONS]


def _open_cards(school: Any, scope: Any, day: dt.date) -> Any:
    return scope.narrow(
        ClassExit.objects.filter(school=school, session__date=day, returned_at__isnull=True)
    ).select_related("student", "session__class_group")


def incoming_rows(school: Any, scope: Any, day: dt.date, now: dt.datetime) -> list[dict[str, Any]]:
    """«قادمون إليك»: بطاقاتٌ خرج بها الطلابُ إلى مشرف الجناح ولم تُستلَم (لم تُحدَّد وجهتُها) — الأطولُ انتظاراً أولاً."""
    rows = [
        {
            "pk": e.pk,
            "student": e.student,
            "class_text": class_label(e.session.class_group.grade, e.session.class_group.section),
            "left_at": timezone.localtime(e.left_at),
            "waited": _minutes(e.left_at, now),
        }
        for e in _open_cards(school, scope, day).filter(
            routed_at__isnull=True, destination="wing_sup"
        )
    ]
    rows.sort(key=lambda r: r["waited"], reverse=True)
    return rows


def live_rows(school: Any, scope: Any, day: dt.date, now: dt.datetime) -> list[dict[str, Any]]:
    """«خارج الآن»: من خرج في `day` ولم يعد وليس قادماً — الأطولُ غياباً أولاً، ملوَّنين بمهلة وجهاتهم."""
    rows = []
    qs = _open_cards(school, scope, day).exclude(routed_at__isnull=True, destination="wing_sup")
    for e in qs:
        minutes = _minutes(e.routed_at or e.left_at, now)
        group = e.session.class_group
        rows.append(
            {
                "pk": e.pk,
                "student": e.student,
                "class_text": class_label(group.grade, group.section),
                "destination": _DESTINATION_LABELS.get(e.destination, e.destination),
                "left_at": timezone.localtime(e.left_at),
                "minutes": minutes,
                "allowed": e.allowed_minutes,
                "tone": _tone(minutes, e.allowed_minutes),
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
