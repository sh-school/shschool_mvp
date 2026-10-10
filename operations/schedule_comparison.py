"""schedule_comparison.py — مقارنة مسودّة التوليد بالجدول المعتمَد بمُقيِّمٍ واحد (W-20261010-008).

القرار على نشر جدول المدرسة يحتاج أن يُعرف أيُّهما أفضل ناعماً، لا أيُّهما فيه مخالفات صلبة وحدَها.
فيُقاس الجدولان **بالمُقيِّم نفسِه** (`evaluate_slots` للصلب والاكتمال، و`ScheduleLab` للناعم) وبسياقٍ واحدٍ
(`load_context` مرّةً واحدة) في مهمّةٍ خلفيّة، وتُخزَّن النتيجةُ في `ScheduleGeneration.metrics["_comparison"]`
بلا هجرة. ولا تمسّ المولّد ولا النماذج.

المؤشّراتُ الخمسة بقرار D-310م: IND-02 اكتمال التموضع، IND-04 فراغات المعلّم، IND-08 تجاوز التتابع،
IND-13 عدالة الأطراف، IND-16 تحقّق التفضيلات؛ يُضاف عددُ الحصص المتغيّرة. قيمٌ فقط — لا أسماءَ معلّمين (PDPPL).

حدٌّ معلَن: HC22 (سقف الأولى) غيرُ مفحوصٍ في هذه المقارنة فلا يُدّعى مفحوصاً.
والمعتمَدُ بُني بمولّد V1 والمسودّةُ غالباً بـV2، فالفرقُ نتيجتان لا سبب.
"""

from __future__ import annotations

import logging
import time
from statistics import mean
from typing import Any

from .schedule_edges import edge_count
from .schedule_evaluator import evaluate_slots, generation_slots, live_slots
from .schedule_lab import (
    MIN_LOAD,
    REST_GAP,
    ScheduleLab,
    _gaps,
    load_context,
    load_slots,
)

logger = logging.getLogger(__name__)

COMPARISON_KEY = "_comparison"

#: المؤشّرات الخمسة: (الرمز، الاسم، الوحدة، الاتّجاه الأفضل، المعنى).
INDICATORS: tuple[tuple[str, str, str, str, str], ...] = (
    ("IND-02", "اكتمال التموضع", "%", "high", "نسبة حصص الإسناد الموضوعة فعلاً (X من Y)."),
    (
        "IND-04",
        "فراغات المعلّم",
        "% من أيام المعلّمين",
        "low",
        "أيامٌ فيها فراغٌ يزيد على استراحة حصّةٍ واحدة بين حصّتين.",
    ),
    (
        "IND-08",
        "تجاوز التتابع",
        "% من أيام المعلّمين",
        "low",
        "أيامٌ يتجاوز فيها تتابعُ المعلّم سقفَه المعتمد.",
    ),
    (
        "IND-13",
        "عدالة الأطراف",
        "% من حصص المعلّم",
        "low",
        "أكثر معلّمٍ تحمّلاً لأول خانةٍ في اليوم وآخرها مقابل المتوسّط.",
    ),
    ("IND-16", "تحقّق التفضيلات", "%", "high", "نسبة تفضيلات المعلّمين المعلنة التي تحقّقت."),
)

NOTES = (
    "HC22 (سقف الأولى) غير مفحوص في هذه المقارنة.",
    "المعتمد بُني بمولّد V1 والمسودّة غالباً بـV2: الفرقُ نتيجتان لا سبب.",
)


def edge_share_stats(by_teacher_day: dict[str, dict[int, list[int]]], load: dict[str, int]) -> dict:
    """نصيب كلّ معلّمٍ من أول خانةٍ وآخرها في أيامه (حصّتُه من حمله) — الأكثرُ والمتوسّط."""
    shares = [
        sum(edge_count(ps) for ps in days.values()) / load[tid]
        for tid, days in by_teacher_day.items()
        if load[tid] >= MIN_LOAD
    ]
    if not shares:
        return {"max": 0.0, "mean": 0.0}
    return {"max": round(100 * max(shares), 1), "mean": round(100 * mean(shares), 1)}


def gap_days_rate(lab: ScheduleLab) -> tuple[float, int, int]:
    """(النسبة، أيام الفراغ الزائد، أيام المعلّمين)."""
    total = bad = 0
    for days in lab.by_teacher_day.values():
        for periods in days.values():
            if not periods:
                continue
            total += 1
            if any(g > REST_GAP for g in _gaps(periods)):
                bad += 1
    return (round(100 * bad / total, 1) if total else 0.0), bad, total


def measure(school: Any, academic_year: str, slots_qs: Any, ctx: Any) -> dict:
    """مقياسُ جدولٍ واحد: الصلب والاكتمال من المُقيِّم، والمؤشّراتُ الخمسة من المختبر."""
    evaluation = evaluate_slots(school, academic_year, slots_qs)
    lab = ScheduleLab(load_slots(slots_qs), ctx)
    gap_rate, gap_days, days = gap_days_rate(lab)
    runs = lab.runs()[1]
    edges = edge_share_stats(lab.by_teacher_day, lab.load)
    preference = lab.preference_satisfaction()
    required = evaluation.required_periods
    completeness = round(100 * evaluation.placed_periods / required, 1) if required else 100.0
    return {
        "hard_total": evaluation.hard_total,
        "hard_breaches": dict(sorted(evaluation.hard_breaches.items())),
        "unplaced": evaluation.infeasibility_value,
        "indicators": {
            "IND-02": {
                "value": completeness,
                "detail": f"{evaluation.placed_periods} من {required}",
            },
            "IND-04": {"value": gap_rate, "detail": f"{gap_days} من {days}"},
            "IND-08": {
                "value": runs["value"] if runs["value"] is not None else 0.0,
                "detail": f"{runs['detail'].get('أيّامٌ مخالفة', 0)} من {runs['detail'].get('أيّامُ المعلّمين', 0)}",
            },
            "IND-13": {"value": edges["max"], "detail": f"المتوسّط {edges['mean']}%"},
            "IND-16": {"value": preference["value"], "detail": ""},
        },
        "edge_cv": lab.edge_fairness()["value"],
    }


def slot_keys(slots_qs: Any) -> set[tuple[str, str, str, int, int]]:
    return {
        (
            str(s.class_group_id),
            str(s.subject_id or ""),
            str(s.teacher_id),
            s.day_of_week,
            s.period_number,
        )
        for s in slots_qs
    }


def changed_slots(draft_keys: set, live_keys: set) -> dict[str, int]:
    """الحصص المتغيّرة: ما في المسودّة وليس في المعتمد (أُضيف/نُقل)، وما في المعتمد وليس فيها."""
    return {"added": len(draft_keys - live_keys), "removed": len(live_keys - draft_keys)}


def compare_generation(generation: Any) -> dict:
    """يقارن مسودّةً بالمعتمَد الحاليّ ويخزّن النتيجة في `metrics` ويُرجعها. لا يكتب غير ذلك."""
    started = time.monotonic()
    school, year = generation.school, generation.academic_year
    ctx = load_context(school, year)
    live_qs, draft_qs = live_slots(school, year), generation_slots(generation)
    live, draft = measure(school, year, live_qs, ctx), measure(school, year, draft_qs, ctx)
    live_keys, draft_keys = slot_keys(live_qs), slot_keys(draft_qs)
    rows = []
    for code, name, unit, better, meaning in INDICATORS:
        a, b = live["indicators"][code]["value"], draft["indicators"][code]["value"]
        delta = None if a is None or b is None else round(b - a, 1)
        rows.append(
            {
                "code": code,
                "name": name,
                "unit": unit,
                "better": better,
                "meaning": meaning,
                "live": live["indicators"][code],
                "draft": draft["indicators"][code],
                "delta": delta,
                "verdict": _verdict(delta, better),
            }
        )
    result = {
        "rows": rows,
        "live": {k: live[k] for k in ("hard_total", "hard_breaches", "unplaced", "edge_cv")},
        "draft": {k: draft[k] for k in ("hard_total", "hard_breaches", "unplaced", "edge_cv")},
        "changed_slots": changed_slots(draft_keys, live_keys),
        "has_live": bool(live_keys),
        "notes": list(NOTES),
        "seconds": round(time.monotonic() - started, 2),
    }
    metrics = dict(generation.metrics or {})
    metrics[COMPARISON_KEY] = result
    generation.metrics = metrics
    generation.save(update_fields=["metrics"])
    return result


def _verdict(delta: float | None, better: str) -> str:
    """تحسّن/تراجع/ثبات — باتّجاه المؤشّر؛ لا حكمَ بلا فرق."""
    if delta is None or delta == 0:
        return "same"
    return "better" if (delta > 0) == (better == "high") else "worse"


def comparison_for_display(generation: Any) -> dict | None:
    """مقارنةُ المسودّة بالمعتمَد من `metrics`؛ ولو غابت لمسودّةٍ طُلبت لها مرّةً في الساعة (idempotent).

    المقارنةُ مهمّةٌ خلفيّة تُطلب عند انتهاء التوليد؛ وهذا الطلبُ يغطّي ما لم يُطلب لها (توليدُ V2 ومسوّداتٌ
    سابقة) بلا أن يحسب الطلبُ شيئاً. والعرضُ بلا نتيجةٍ يقول «قيد الحساب».
    """
    found = (generation.metrics or {}).get(COMPARISON_KEY)
    if found or generation.status != "draft":
        return found
    from django.core.cache import cache

    from .tasks import compare_generation_to_live_task

    if cache.add(f"schedule-compare:{generation.pk}", 1, 3600):
        try:
            compare_generation_to_live_task.delay(str(generation.pk))
        except Exception:  # noqa: BLE001 — العرضُ لا يسقط لتعذّر الإرسال
            logger.exception("تعذّر طلب مقارنة المسودّة %s", generation.pk)
    return None
