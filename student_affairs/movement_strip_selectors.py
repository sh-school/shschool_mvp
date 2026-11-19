"""[STUDENT_AFFAIRS] W-20261119-003: شريطُ الأجنحة والتفصيلُ بالوجهة في شاشة الحركة (إدارةُ الأجنحة 3/4).

قراءةٌ من `ClassExit` وحدَها مضيَّقةً بنطاق `_followup_scope`. شريطٌ بخمس خانات لكلّ جناح، ثمّ تفصيلٌ بالوجهة
**يدمج العيادةَ مع غيرها** لمن ليس من الصحّة: عدّادُ العيادة المنفصلُ بالجناح واليومِ يكشف زيارةً صحّيّةً لقاصر.
لا أسماءَ هنا: أرقامٌ فقط.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from operations.exit_wing import excused_ids
from operations.models import ClassExit

#: خاناتُ الشريط بترتيبها: مفتاحُ العدّ، واسمُه المعروض.
STRIP_CELLS = (
    ("out", "خارج الآن"),
    ("late", "متأخر"),
    ("unreceived", "لم يُستلم"),
    ("returned", "عادوا اليوم"),
    ("late_returns", "عادوا متأخرين"),
)

#: وجهاتٌ تُدمج في خانةٍ واحدةٍ لغير الصحّة — فيها العيادةُ فلا تنفرد.
MERGED_DESTINATIONS = ("clinic", "sa_coord", "vice", "admin", "other", "wing_sup")
MERGED_LABEL = "الإدارة وغيرها"

_NO_WING = "بلا جناح"
_ALL = "كلّ الأجنحة"


def _count(card: dict[str, Any], now: dt.datetime, excused: set[Any]) -> dict[str, int]:
    """مساهمةُ بطاقةٍ واحدةٍ في خانات الشريط (0 أو 1 لكلّ خانة)."""
    hit = dict.fromkeys((k for k, _ in STRIP_CELLS), 0)
    if card["returned_at"] is not None:
        if not card["system_closed"]:
            hit["returned"] = 1
        if (card["late_return_seconds"] or 0) > 0 and card["student_id"] not in excused:
            hit["late_returns"] = 1
        return hit
    if card["routed_at"] is None and card["destination"] == "wing_sup":
        hit["unreceived"] = 1
        return hit
    hit["out"] = 1
    allowed = card["allowed_minutes"]
    since = card["routed_at"] or card["left_at"]
    if allowed is not None and card["student_id"] not in excused:
        hit["late"] = int((now - since).total_seconds() // 60 > allowed)
    return hit


def wing_strip(school: Any, scope: Any, day: dt.date, now: dt.datetime) -> list[dict[str, Any]]:
    """سطرٌ لكلّ جناحٍ بخمس خانات — وسطرُ «كلّ الأجنحة» أوّلاً حين يزيد الظاهرُ عن جناحٍ واحد."""
    cards = scope.narrow(ClassExit.objects.filter(school=school, session__date=day)).values(
        "session__class_group__wing__name",
        "student_id",
        "destination",
        "left_at",
        "routed_at",
        "returned_at",
        "allowed_minutes",
        "system_closed",
        "late_return_seconds",
    )
    excused = excused_ids(school, day)
    by_wing: dict[str, dict[str, int]] = {}
    for card in cards:
        name = card["session__class_group__wing__name"] or _NO_WING
        cell = by_wing.setdefault(name, dict.fromkeys((k for k, _ in STRIP_CELLS), 0))
        for key, value in _count(card, now, excused).items():
            cell[key] += value
    rows = [
        {"wing": name, "cells": [(label, cell[key]) for key, label in STRIP_CELLS]}
        for name, cell in sorted(by_wing.items())
    ]
    if len(rows) > 1:
        total = [
            (label, sum(r["cells"][i][1] for r in rows)) for i, (_, label) in enumerate(STRIP_CELLS)
        ]
        rows.insert(0, {"wing": _ALL, "cells": total})
    return rows


def destination_split(
    school: Any, scope: Any, day: dt.date, health_viewer: bool
) -> list[tuple[str, int]]:
    """عددُ خروج اليوم بالوجهة. غيرُ الصحّة يرى العيادةَ مدموجةً في «الإدارة وغيرها» لا منفردة."""
    counts: dict[str, int] = {}
    for code in scope.narrow(
        ClassExit.objects.filter(school=school, session__date=day)
    ).values_list("destination", flat=True):
        counts[code] = counts.get(code, 0) + 1
    labels = dict(ClassExit.DESTINATIONS)
    rows: list[tuple[str, int]] = []
    merged = 0
    for code, number in counts.items():
        if not health_viewer and code in MERGED_DESTINATIONS:
            merged += number
        else:
            rows.append((labels.get(code, code), number))
    rows.sort(key=lambda r: (-r[1], r[0]))
    if merged:
        rows.append((MERGED_LABEL, merged))
    return rows
