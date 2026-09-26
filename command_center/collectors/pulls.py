"""لوحةُ «الطلباتُ ومسارُ الدمج» — طلباتٌ مفتوحةٌ وأقدمُها عمراً، وتأخّرُ النشر (كم إيداعاً في main لم يُنشر بعد).

قراءةُ القرص = 100 ناقصاً 3 لكلّ إيداعٍ غيرِ منشور ونقطتان لكلّ طلبٍ مفتوحٍ فوق العشرة. ما يُحفظ أرقامٌ فقط.
تأخّرُ النشر من مقارنة آخر نشرٍ مسجَّلٍ في GitHub بـmain (نشرُ Railway يسجّل `deployments`)، فلا يُقرأ الإنتاجُ نفسُه.
"""

from __future__ import annotations

import time
from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish

PANEL = "pulls"
OPEN_PATH = "pulls?state=open&per_page=100"
DEPLOY_PATH = "deployments?per_page=1"
LAG_WARN = 20
OLDEST_WARN_DAYS = 7


def reduce_open(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    pulls = [p for p in payload if isinstance(p, dict)]
    live = [p for p in pulls if not p.get("draft")]
    created = [t for t in (github.epoch(p.get("created_at")) for p in live) if t is not None]
    return {
        "open": len(pulls),
        "drafts": len(pulls) - len(live),
        "oldest": min(created) if created else None,
    }


def reduce_deploy(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    sha = payload[0].get("sha") if payload and isinstance(payload[0], dict) else None
    return {"sha": sha if isinstance(sha, str) and sha.isalnum() and len(sha) >= 7 else ""}


def reduce_compare(payload: Any) -> dict[str, Any] | None:
    ahead = payload.get("ahead_by") if isinstance(payload, dict) else None
    return {"ahead": ahead} if isinstance(ahead, int) else None


def _lag() -> int | None:
    """إيداعاتُ main غيرُ المنشورة، أو None إن لم يُعرف (لا نشرٌ مسجَّل أو عطلُ الجلب)."""
    deploy = github.fetch(DEPLOY_PATH, reduce_deploy)
    if not deploy or not deploy["sha"]:
        return None
    compare = github.fetch(f"compare/{deploy['sha']}...main", reduce_compare)
    return None if compare is None else int(compare["ahead"])


def level(oldest_days: float | None, lag: int | None) -> str:
    stale = oldest_days is not None and oldest_days > OLDEST_WARN_DAYS
    if lag is None or stale or lag > LAG_WARN:
        return contract.WARN
    return contract.OK


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    opened = github.fetch(OPEN_PATH, reduce_open)
    if opened is None:
        failed(PANEL, "github")
        return
    lag = _lag()
    oldest = opened["oldest"]
    days = None if oldest is None else max(0.0, (moment - float(oldest)) / 86400)
    gauge = 100 - 3 * (lag or 0) - 2 * max(0, opened["open"] - 10)
    publish(
        PANEL,
        status=level(days, lag),
        headline=f"{opened['open']} طلباً مفتوحاً" if opened["open"] else "لا طلباتٍ مفتوحة",
        gauge=gauge if lag is not None else None,
        metrics=(
            ("مسوَّدات", opened["drafts"]),
            ("الأقدمُ عمراً", "—" if days is None else f"{int(days)} يوماً"),
            ("إيداعاتٌ غيرُ منشورة", "؟" if lag is None else lag),
        ),
    )
