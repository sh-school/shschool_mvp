"""لوحةُ «إيقاع النشر» — كم نُشر وكم مضى على آخر نشرٍ وهل جرى تراجع (GitHub العامّ، أرقامٌ فقط).

مصدراها `deployments` (نشرُ Railway يسجّلها) وتشغيلاتُ `rollback.yml`. **«انتبه»**: مضى على آخر نشرٍ أكثرُ من 7 أيّامٍ (عملٌ مدموجٌ لا يصل الإنتاجَ)، أو جرى تراجعٌ في آخر 7 أيّام؛
**أحمرُ**: تراجعان فأكثرُ في 7 أيّام (عدمُ استقرارٍ لا حادثةٌ). قراءةُ القرص = 100 ناقصاً عقوبةَ كلٍّ منهما. ولا مدّةَ من الدمج إلى النشر هنا (تحتاج طلباً لكلّ إيداع).
"""

from __future__ import annotations

import time
from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish, score, worst

PANEL = "delivery"
DEPLOYS_PATH = "deployments?per_page=50"
ROLLBACK_PATH = "actions/workflows/rollback.yml/runs?status=completed&per_page=20"
STALE_DAYS = 7
WEEK = 7 * 86400


def reduce_deploys(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    stamps = sorted(
        (
            t
            for t in (github.epoch(d.get("created_at")) for d in payload if isinstance(d, dict))
            if t
        ),
        reverse=True,
    )
    return {"stamps": stamps}


def reduce_rollbacks(payload: Any) -> dict[str, Any] | None:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    stamps = [
        t
        for t in (
            github.epoch(r.get("created_at"))
            for r in runs
            if isinstance(r, dict) and r.get("conclusion") == "success"
        )
        if t
    ]
    return {"stamps": stamps}


def levels(days_since: float | None, rollbacks_week: int) -> list[str]:
    stale = contract.WARN if days_since is None or days_since > STALE_DAYS else contract.OK
    if rollbacks_week >= 2:
        back = contract.BAD
    else:
        back = contract.WARN if rollbacks_week else contract.OK
    return [stale, back]


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    deploys = github.fetch(DEPLOYS_PATH, reduce_deploys)
    rollbacks = github.fetch(ROLLBACK_PATH, reduce_rollbacks)
    if deploys is None or rollbacks is None:
        failed(PANEL, "github")
        return
    stamps = deploys["stamps"]
    days_since = None if not stamps else max(0.0, (moment - stamps[0]) / 86400)
    week = sum(1 for t in stamps if moment - t <= WEEK)
    back_week = sum(1 for t in rollbacks["stamps"] if moment - t <= WEEK)
    found = levels(days_since, back_week)
    overall = worst(found)
    if back_week:
        headline = f"{back_week} تراجعاً في آخر 7 أيّام"
    elif days_since is None:
        headline = "لا نشراتٍ مسجَّلة"
    elif days_since > STALE_DAYS:
        headline = f"لم يُنشر منذ {int(days_since)} يوماً"
    else:
        headline = "إيقاعُ النشر منتظم"
    publish(
        PANEL,
        status=overall,
        headline=headline,
        gauge=score(found),
        metrics=(
            ("نشراتُ آخر 7 أيّام", week),
            ("منذ آخر نشر", "—" if days_since is None else f"{days_since:.1f} يوماً"),
            ("تراجعاتٌ / 7 أيّام", back_week),
        ),
    )
