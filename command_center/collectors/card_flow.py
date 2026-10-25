"""لوحةُ «مسارُ البطاقات» — أين تقف كلُّ بطاقةٍ بين «جاهز» و«منشور» وهل تجاوزت مرحلتُها عتبتَها (W-20261020-012).

المصدرُ **لقطةُ JSON للدفتر قراءةً فقط** (تبنيها جلسةُ الحوكمة خارج المنصّة): المنصّةُ لا تكتب في الدفتر ولا تنقل بطاقة.
صيغةُ اللقطة (tools/ledger_snapshot.py): ``{"schema": 1, "generated_at": ISO, "cards": [{"id", "state", "stages": {حالة: ISO}, "head"}]}``
ويُحوَّل عند القراءة إلى ثوانٍ بمراحل: ``ready ← approved ← pushed ← merged ← published``. لا مرحلةَ «طلب» في اللقطة (رقمُه ليس في الأحداث)،
فحدُّ «طلب + دمج» (60 دقيقة) يُقاس معاً من الدفع إلى الدمج.

- **العتباتُ** (قرارُ المالك 2026-10-20) بين كلّ مرحلةٍ والتي تليها: اعتماد > 4 ساعات، دفع > 30 دقيقة، طلب > 30 دقيقة،
  دمج > 30 دقيقة، نشر > 15 دقيقة. المرحلةُ الجاريةُ تُقاس إلى «الآن»، فتتجاوز وهي لم تنتهِ.
- **غيابُ المصدر ليس سلامةً**: لا لقطة أو لقطةٌ قديمةٌ ← ``failed`` فتُعرض «غيرَ معلومة» لا خضراء.
- **رموزُ بطاقاتٍ وأرقامٌ فقط** في اللوحة (عقدُ v1)؛ وحادثةٌ = (بطاقة، مرحلة) تُنذر مرّةً (`alert_new`).
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any

from django.core.cache import cache

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish, score, worst

PANEL = "card_flow"
STAGES = ("ready", "approved", "pushed", "merged", "published")
#: حالةُ الدفتر ← مرحلتُنا.
STATE_TO_STAGE = {
    "ready_for_review": "ready",
    "approved": "approved",
    "pushed": "pushed",
    "merged": "merged",
    "published": "published",
}
#: المرحلةُ الجاريةُ ← حدُّها بالثواني قبل أن تبلغ التاليةَ (قرارُ المالك 2026-10-20).
THRESHOLDS: dict[str, int] = {
    "ready": 4 * 3600,  # اعتماد
    "approved": 30 * 60,  # دفع
    "pushed": 60 * 60,  # طلب (30د) + دمج (30د) معاً
    "merged": 15 * 60,  # نشر
}
LABELS = {"ready": "اعتماد", "approved": "دفع", "pushed": "طلب ودمج", "merged": "نشر"}
#: لقطةٌ أقدمُ من هذا لا يُوثَق بها (الدورةُ ثلاث دقائق).
MAX_SNAPSHOT_AGE = 20 * 60
SNAPSHOT_PATH = "contents/ledger_snapshot.json"
_ALERTED_TTL = 7 * 24 * 3600


def _is_stamp(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def current_stage(stamps: Mapping[str, Any]) -> str | None:
    """آخرُ مرحلةٍ بلغتها البطاقةُ بالترتيب؛ ``None`` إن لم تبلغ «جاهز» أو اكتملت (published)."""
    last = None
    for stage in STAGES:
        if not _is_stamp(stamps.get(stage)):
            break
        last = stage
    return None if last in (None, "published") else last


def breaches(cards: Iterable[Mapping[str, Any]], now: float) -> list[dict[str, Any]]:
    """المراحلُ المتجاوزةُ حدَّها: ``[{"card", "stage", "over"}]`` (over بالثواني فوق الحدّ)، الأسوأُ أوّلاً."""
    found = []
    for card in cards:
        stamps, card_id = card.get("stamps"), card.get("id")
        if not isinstance(stamps, Mapping) or not isinstance(card_id, str):
            continue
        stage = current_stage(stamps)
        if stage is None:
            continue
        over = now - float(stamps[stage]) - THRESHOLDS[stage]
        if over > 0:
            found.append({"card": card_id, "stage": stage, "over": int(over)})
    return sorted(found, key=lambda b: -b["over"])


def alert_new(found: Iterable[Mapping[str, Any]], moment: float) -> int:
    """حادثةٌ واحدةٌ = تنبيهٌ واحد: (بطاقة، مرحلة) لم تُنذر من قبل تُنذر الآن. يعيد عددَ الجديد."""
    from command_center import alerts

    fresh = 0
    for item in found:
        key = f"qcc:card_flow:alerted:{item['card']}:{item['stage']}"
        if not cache.add(key, 1, _ALERTED_TTL):
            continue
        fresh += 1
        alerts.notify(
            "مسارُ البطاقات: بطاقةٌ تأخّرت",
            f"{item['card']} تجاوزت حدَّ مرحلة «{LABELS[item['stage']]}».",
            PANEL,
            "urgent",
            moment,
        )
    return fresh


def _seconds(value: Any) -> float | None:
    return github.epoch(value) if isinstance(value, str) else None


def reduce_snapshot(payload: Any) -> dict[str, Any] | None:
    """اللقطةُ ← ``{"generated_at": ثوانٍ, "cards": [{"id", "stamps"}]}`` (معرّفاتٌ وأزمنةٌ فقط)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        return None
    generated = _seconds(payload.get("generated_at"))
    if generated is None:
        return None
    cards = []
    for card in payload["cards"]:
        if not isinstance(card, dict) or not isinstance(card.get("id"), str):
            continue
        stages = card.get("stages") if isinstance(card.get("stages"), dict) else {}
        stamps = {
            STATE_TO_STAGE[state]: moment
            for state, raw in stages.items()
            if state in STATE_TO_STAGE and (moment := _seconds(raw)) is not None
        }
        cards.append({"id": card["id"], "stamps": stamps})
    return {"generated_at": generated, "cards": cards}


def collect(now: float | None = None, snapshot: dict[str, Any] | None = None) -> None:
    moment = time.time() if now is None else now
    data = snapshot if snapshot is not None else github.fetch(SNAPSHOT_PATH, reduce_snapshot)
    if data is None:
        failed(PANEL, "snapshot")
        return
    if moment - data["generated_at"] > MAX_SNAPSHOT_AGE:
        failed(PANEL, "stale")
        return
    found = breaches(data["cards"], moment)
    alert_new(found, moment)
    open_cards = sum(1 for c in data["cards"] if current_stage(c["stamps"]) is not None)
    levels = [contract.BAD if found else contract.OK]
    publish(
        PANEL,
        status=worst(levels),
        headline=f"{len(found)} بطاقةً متأخّرة" if found else "كلُّ المراحل ضمن حدّها",
        gauge=score(levels),
        metrics=(
            ("بطاقاتٌ في المسار", open_cards),
            ("متأخّرة", len(found)),
            ("أطولُ تجاوز", f"{found[0]['over'] // 60} د" if found else "—"),
        ),
    )
