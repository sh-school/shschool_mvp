"""كتابةُ لوحةٍ في اللقطة بشكلٍ موحَّد — الطريقُ الوحيد الذي تستعمله المجمِّعات (فوق `contract.store`)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from command_center import contract

#: عقوبةُ كلّ فحصٍ على قراءة القرص: الأحمرُ يخفضه أكثرَ من الأصفر — والمئةُ سليمٌ كلُّه.
PENALTY = {contract.OK: 0, contract.WARN: 12, contract.BAD: 35}


def worst(levels: Iterable[str]) -> str:
    """أسوأُ الحالات: bad ثمّ warn ثمّ ok."""
    found = set(levels)
    if contract.BAD in found:
        return contract.BAD
    return contract.WARN if contract.WARN in found else contract.OK


def score(levels: Iterable[str]) -> int:
    """قراءةُ القرص من حالات الفحوص: 100 ناقصاً عقوبةَ كلٍّ منها، ولا تنزل عن الصفر."""
    return max(0, 100 - sum(PENALTY.get(level, PENALTY[contract.WARN]) for level in levels))


def publish(
    panel: str,
    *,
    status: str,
    headline: str,
    gauge: float | None,
    metrics: Sequence[tuple[str, Any]] = (),
    detail: str = "",
) -> None:
    """يكتب لوحةً: حالتُها وجملتُها وقراءةُ قرصِها وحتّى أربعةِ مؤشّراتٍ ثانويّة (عنوانٌ وقيمة)."""
    data: dict[str, Any] = {"status": status, "headline": headline[: contract.MAX_STRING]}
    if detail:
        data["detail"] = detail[: contract.MAX_STRING]
    if gauge is not None:
        data["gauge"] = max(0, min(100, round(gauge)))
    for index, (label, value) in enumerate(metrics[: contract.MAX_METRICS], start=1):
        data[f"m{index}_l"] = str(label)[: contract.MAX_STRING]
        data[f"m{index}_v"] = str(value)[: contract.MAX_STRING]
    contract.store(panel, data)


def failed(panel: str, code: str) -> None:
    """فشلُ جمعٍ: تبقى آخرُ قيمةٍ سليمةٍ ويُحدَّث الرمزُ وحدَه (`ok=False` ← «انتبه» لا «سليم»)."""
    contract.store(panel, {}, ok=False, err=code)
