"""لوحةُ «فحوصُ CI» — نتيجةُ `quality-gate` على main (آخرُ عشرةِ تشغيلاتٍ محسومة).

قراءةُ القرص = نسبةُ النجاح بين المحسوم (نجاحٌ أو فشلٌ أو انتهاءُ مهلة؛ الملغى والمتخطّى لا يُحسبان). أحمرُ متّصلٌ على main أكثرَ من
ساعةٍ = أحمر (والأقلُّ من ساعةٍ «انتبه»: قد يكون إصلاحُه في الطريق)، وبلا تشغيلٍ محسومٍ = «انتبه».
"""

from __future__ import annotations

import time
from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish

PANEL = "ci"
WORKFLOW = "quality-gate.yml"
PATH = f"actions/workflows/{WORKFLOW}/runs?branch=main&event=push&status=completed&per_page=10"
FAILURES = ("failure", "timed_out")
COUNTED = ("success", *FAILURES)
RED_BAD_AFTER = 3600


def reduce(payload: Any) -> dict[str, Any] | None:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    counted = [
        (github.epoch(run.get("updated_at")), run.get("conclusion"))
        for run in runs
        if isinstance(run, dict) and run.get("conclusion") in COUNTED
    ]
    counted = [(at, result) for at, result in counted if at is not None]
    streak = next((i for i, (_, result) in enumerate(counted) if result == "success"), len(counted))
    return {
        "total": len(counted),
        "passed": sum(1 for _, result in counted if result == "success"),
        "latest_at": counted[0][0] if counted else None,
        "latest_ok": counted[0][1] == "success" if counted else None,
        "red_streak": streak,
    }


def level(summary: dict[str, Any], now: float) -> str:
    if summary["total"] == 0:
        return contract.WARN
    if summary["latest_ok"]:
        return contract.OK
    return contract.BAD if now - float(summary["latest_at"]) > RED_BAD_AFTER else contract.WARN


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    summary = github.fetch(PATH, reduce)
    if summary is None:
        failed(PANEL, "github")
        return
    total = summary["total"]
    if total == 0:
        headline, gauge = "لا تشغيلَ محسوماً على main بعد", None
    elif summary["latest_ok"]:
        headline, gauge = "بوّابةُ الجودة خضراءُ على main", 100 * summary["passed"] / total
    else:
        headline = f"main أحمرُ منذ {summary['red_streak']} تشغيل"
        gauge = 100 * summary["passed"] / total
    publish(
        PANEL,
        status=level(summary, moment),
        headline=headline,
        gauge=gauge,
        metrics=(
            ("نجاحُ آخر عشرة", f"{summary['passed']} من {total}"),
            ("سلسلةُ الأحمر", summary["red_streak"]),
        ),
    )
