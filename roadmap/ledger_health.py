"""لقطةُ الدفتر وحارسُ الانحراف بينه وبين الخارطة — قراءةٌ فقط (W-20261009-026).

الدفترُ (`delivery_manager_work/ledger/events.jsonl`) خارج المستودع، وأحداثُه تُلحَق فقط. تُعيد `reduce_cards` هنا اشتقاقَ حالة كلّ
بطاقةٍ بالقدر الذي تحتاجه القياساتُ (الحالةُ وزمنُها والحاملُ والملاحظات) — **لا تكتب** ولا تستورد أداةَ الدفتر (خارج المستودع). وهي
نسخةٌ مصغَّرةٌ من `ledger.py::reduce_state`؛ فإن تبدّل شكلُ الأحداث فاختبارُ العقد (`tests/test_roadmap_health.py`) يسقط.

الانحرافُ أربعة أصناف (تقريرٌ لا حجب):

1. **طلبٌ مدموجٌ بلا بند**: رقمُ طلبٍ تذكره ملاحظاتُ بطاقةٍ مدموجةٍ/منشورة ولا يرد في `pr` ولا `note` ولا `ref` لأيّ بند.
2. **بطاقةٌ مدموجةٌ بلا رقمِ طلب**: لا يمكن مطابقتُها بالخارطة آليّاً.
3. **بندٌ مُغلَق بلا مرجع**: كما في `health.closed_without_reference`.
4. **بندٌ يذكر بطاقةً لا يعرفها الدفتر**: `W-…` في حقول البند وليست في الدفتر.

المطابقةُ بأرقام الطلبات المذكورة في الملاحظات، وهي عمليّاً ما تحمله 87% من البطاقات المنشورة (قيس 10-10: 140 من 161)؛
فالتقريرُ **حدٌّ أدنى للانحراف** لا إحصاءٌ كامل.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from roadmap.health import closed_without_reference
from roadmap.models import RoadmapItem

MERGED_STATES = frozenset({"merged", "published"})
_PR = re.compile(r"(?:#|الطلب|طلب|PR)\s*(\d{3,5})\b")
_CARD = re.compile(r"W-\d{8}-\d+")
_NUMBER = re.compile(r"#(\d{2,6})\b")


def read_events(path: Path) -> list[dict[str, Any]]:
    """أحداثُ الدفتر؛ ملفٌّ غائبٌ أو سطرٌ فاسدٌ يرفع خطأً صريحاً (لا نصفَ لقطة)."""
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"السطر {number} ليس JSON") from exc
        if not isinstance(event, dict) or not {"ts", "id", "kind", "data"} <= event.keys():
            raise ValueError(f"السطر {number} ينقصه ts/id/kind/data")
        events.append(event)
    return events


def reduce_cards(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for event in events:
        data, card_id, kind = event["data"], event["id"], event["kind"]
        if kind == "created":
            cards[card_id] = {
                "id": card_id,
                "created": event["ts"],
                "state": "captured",
                "state_ts": event["ts"],
                "held_by": data.get("held_by") or "",
                "notes": [],
            }
            continue
        card = cards.get(card_id)
        if card is None:
            continue
        if kind == "state":
            if "held_by" in data:
                card["held_by"] = data["held_by"] or ""
            card["state"], card["state_ts"] = data["state"], event["ts"]
        elif kind == "update" and "held_by" in data:
            card["held_by"] = data["held_by"] or ""
        elif kind == "note":
            card["notes"].append(str(data.get("text", "")))
    return cards


def _days(stamp: str, today: date) -> int:
    return max(0, (today - date.fromisoformat(stamp[:10])).days)


def ledger_summary(cards: Mapping[str, Mapping[str, Any]], today: date) -> dict[str, Any]:
    """الشكلُ الذي تقرؤه الصفحةُ من `RoadmapMeta.data["ledger"]` (يتحقّق منه `health.ledger_snapshot`)."""
    by_state: dict[str, dict[str, int]] = {}
    routed = unheld = routed_oldest = 0
    for card in cards.values():
        age = _days(card["state_ts"], today)
        slot = by_state.setdefault(card["state"], {"n": 0, "oldestDays": 0})
        slot["n"] += 1
        slot["oldestDays"] = max(slot["oldestDays"], age)
        if card["state"] == "routed":
            routed += 1
            routed_oldest = max(routed_oldest, age)
            unheld += 0 if card["held_by"] else 1
    return {
        "asOf": today.isoformat(),
        "total": len(cards),
        "routed": routed,
        "routedNoHolder": unheld,
        "routedOldestDays": routed_oldest,
        "byState": by_state,
    }


def _item_numbers(items: Iterable[RoadmapItem]) -> set[int]:
    return {
        int(n) for o in items for text in (o.pr, o.note, o.ref) for n in _NUMBER.findall(text or "")
    }


def drift_report(
    cards: Mapping[str, Mapping[str, Any]], items: list[RoadmapItem]
) -> dict[str, Any]:
    known = _item_numbers(items)
    prs_without_item: list[dict[str, Any]] = []
    merged_without_pr: list[str] = []
    for card in sorted(cards.values(), key=lambda c: c["id"]):
        if card["state"] not in MERGED_STATES:
            continue
        numbers = {int(n) for text in card["notes"] for n in _PR.findall(text)}
        if not numbers:
            merged_without_pr.append(card["id"])
        prs_without_item += [{"pr": n, "card": card["id"]} for n in sorted(numbers - known)]
    red, _archived = closed_without_reference(items)
    unknown_cards = [
        {"item": o.code, "card": c}
        for o in items
        for c in sorted(set(_CARD.findall(f"{o.note} {o.ref} {o.deps} {o.criterion}")))
        if c not in cards
    ]
    return {
        "prsWithoutItem": prs_without_item,
        "mergedWithoutPr": merged_without_pr,
        "closedWithoutReference": [o.code for o in red],
        "itemsWithUnknownCard": unknown_cards,
    }


def drift_counts(report: Mapping[str, Any]) -> dict[str, int]:
    """أعدادُ الأصناف الأربعة — ما يدخل اللقطةَ (التفصيلُ يبقى في التقرير)."""
    return {key: len(value) for key, value in report.items()}
