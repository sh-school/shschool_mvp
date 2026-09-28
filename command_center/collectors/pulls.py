"""لوحةُ «الطلباتُ ومسارُ الدمج» — طلباتٌ مفتوحةٌ وأقدمُها عمراً، وتأخّرُ النشر (كم إيداعاً في main لم يُنشر بعد)، والفروعُ البعيدةُ بلا طلب.

قراءةُ القرص = 100 ناقصاً 3 لكلّ إيداعٍ غيرِ منشور ونقطتان لكلّ طلبٍ مفتوحٍ فوق العشرة ونقطتان لكلّ فرعٍ بلا طلبٍ فوق العشرة.
ما يُحفظ أرقامٌ فقط. تأخّرُ النشر من مقارنة آخر نشرٍ مسجَّلٍ في GitHub بـmain (نشرُ Railway يسجّل `deployments`)، فلا يُقرأ الإنتاجُ نفسُه.

**الفروعُ بلا طلب** (REP-10 في المنصّة، D-50م — كانت قراءةُ RK مهمّةً مجدولةً في Claude Code): فرعٌ في GitHub غيرُ main لا يطابق طرفُه
رأسَ أيِّ طلبٍ مفتوح (والمسوّدةُ طلبٌ). الطابورُ يحذف فرعَ الطلب المدموج (`delete_branch_on_merge`)، فالباقي عملٌ مدفوعٌ بلا طلبٍ أو طلبٌ
أُغلق بلا دمج — نظافةٌ لا خطرُ فقدان (العملُ في GitHub)، فـ«انتبه» لا أحمر. المقارنةُ بطرف الإيداع (سداسيٌّ مقصوص) لا باسم الفرع،
فلا يُخزَّن اسمُ فرعٍ ولا عنوانُ طلب. والفروعُ **المحلّيّة** (RK1..RK3) لا يراها الخادم فليست هنا.
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
BRANCHES_PATH = "branches?per_page=100"
DEFAULT_BRANCH = "main"
LAG_WARN = 20
OLDEST_WARN_DAYS = 7
ORPHAN_WARN = 10
_SHA_LEN = 12


def short_sha(value: Any) -> str | None:
    """طرفُ إيداعٍ سداسيٌّ مقصوص، أو None لما ليس كذلك (لا يُخزَّن نصٌّ من الردّ)."""
    if not isinstance(value, str) or len(value) < 7:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value[:_SHA_LEN].lower()


def reduce_open(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    pulls = [p for p in payload if isinstance(p, dict)]
    live = [p for p in pulls if not p.get("draft")]
    created = [t for t in (github.epoch(p.get("created_at")) for p in live) if t is not None]
    heads = {short_sha((p.get("head") or {}).get("sha")) for p in pulls}
    return {
        "open": len(pulls),
        "drafts": len(pulls) - len(live),
        "oldest": min(created) if created else None,
        "heads": sorted(h for h in heads if h),
    }


def reduce_branches(payload: Any) -> dict[str, Any] | None:
    """أطرافُ الفروع البعيدة عدا main — و`full` إن امتلأت الصفحةُ (فالعددُ حدٌّ أدنى)."""
    if not isinstance(payload, list):
        return None
    branches = [b for b in payload if isinstance(b, dict) and b.get("name") != DEFAULT_BRANCH]
    tips = {short_sha((b.get("commit") or {}).get("sha")) for b in branches}
    return {"tips": sorted(t for t in tips if t), "full": len(payload) >= 100}


def orphans(opened: dict[str, Any], branches: dict[str, Any] | None) -> int | None:
    """فروعٌ لا يطابق طرفُها رأسَ طلبٍ مفتوح، أو None إن لم يُعرف (عطلُ الجلب، أو خلاصةٌ قديمةٌ بلا أطراف)."""
    if (
        not branches
        or not isinstance(branches.get("tips"), list)
        or not isinstance(opened.get("heads"), list)
    ):
        return None
    heads = set(opened["heads"])
    return sum(1 for tip in branches["tips"] if tip not in heads)


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


def level(oldest_days: float | None, lag: int | None, orphan_count: int | None = None) -> str:
    stale = oldest_days is not None and oldest_days > OLDEST_WARN_DAYS
    littered = orphan_count is not None and orphan_count > ORPHAN_WARN
    if lag is None or stale or littered or lag > LAG_WARN:
        return contract.WARN
    return contract.OK


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    opened = github.fetch(OPEN_PATH, reduce_open)
    if opened is None:
        failed(PANEL, "github")
        return
    lag = _lag()
    branches = github.fetch(BRANCHES_PATH, reduce_branches)
    stray = orphans(opened, branches)
    oldest = opened["oldest"]
    days = None if oldest is None else max(0.0, (moment - float(oldest)) / 86400)
    gauge = (
        100
        - 3 * (lag or 0)
        - 2 * max(0, opened["open"] - 10)
        - 2 * max(0, (stray or 0) - ORPHAN_WARN)
    )
    stray_text = (
        "؟" if stray is None else f"{stray}{'+' if branches and branches.get('full') else ''}"
    )
    publish(
        PANEL,
        status=level(days, lag, stray),
        headline=f"{opened['open']} طلباً مفتوحاً" if opened["open"] else "لا طلباتٍ مفتوحة",
        gauge=gauge if lag is not None else None,
        metrics=(
            ("مسوَّدات", opened["drafts"]),
            ("الأقدمُ عمراً", "—" if days is None else f"{int(days)} يوماً"),
            ("إيداعاتٌ غيرُ منشورة", "؟" if lag is None else lag),
            ("فروعٌ بلا طلب", stray_text),
        ),
    )
