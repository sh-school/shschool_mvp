"""لوحةُ «الطابورُ والنشر» — الطلباتُ المفتوحةُ بحالة كلٍّ منها (W-20261002-022؛ تغني المالكَ عن الاستعلام اليدويّ عن الطابور والأحمر والتعارضات).

المصدرُ GitHub العامّ بجلبٍ شرطيٍّ (`collectors/github.py`): قائمةُ الطلبات المفتوحة، ثمّ لكلّ طلبٍ `mergeable_state` وفحوصُ رأسِه.
ما يُخزَّن **أرقامٌ وتصنيفاتٌ ثابتةٌ فقط** (رقمُ الطلب، وحالتُه من قائمةٍ مغلقة، وعددُ الفحوص الناجحة/الكلّ، وعمرُه بالساعات) — لا عنوانَ ولا
اسمَ فرعٍ ولا كاتب (`contract.py`: لا نصَّ من طرفٍ ثالث والمستودعُ عامّ). وتُحفظ الصفوفُ مسطَّحةً في بيانات اللوحة نفسِها (`pr1_n`…)
فلا مخزنَ ثانياً ولا هجرة؛ وصفحةُ `/command-center/status/` تقرؤها.

الحالةُ (`state`): draft مسوّدة · conflict تعارضٌ مع main · behind متأخّرٌ عن main · blocked ينتظر فحوصاً أو اعتماداً · unstable فحصٌ غيرُ إلزاميٍّ فاشل ·
clean جاهزٌ للدمج · unknown لم يُعرف. و`auto` = الدمجُ التلقائيُّ مفعَّل. «في الطابور» لا يُرى من الواجهة العامّة بلا رمز، فلا يُدّعى.

اللوحة: «انتبه» إن وُجد طلبٌ غيرُ مسوّدةٍ فيه تعارضٌ أو فحصٌ فاشل؛ وأحمرُ (فيصل جرسَ المطوّر عبر `alerts.py`) إن بقي كذلك ولم يُمسّ الطلبُ
ساعتَين (`STUCK_HOURS`) — فتعارضٌ عابرٌ بعد دمجِ غيره لا يُنذر، وطلبٌ عالقٌ يُنذر. والمسوّداتُ لا تُنذر.
"""

from __future__ import annotations

import time
from typing import Any

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed

PANEL = "queue"
OPEN_PATH = "pulls?state=open&per_page=30"
MAX_ROWS = 12
STUCK_HOURS = 2
STATES = ("draft", "conflict", "behind", "blocked", "unstable", "clean", "unknown")
_MAP = {
    "dirty": "conflict",
    "behind": "behind",
    "blocked": "blocked",
    "unstable": "unstable",
    "clean": "clean",
    "has_hooks": "clean",
    "draft": "draft",
}
_FAIL = ("failure", "timed_out", "cancelled", "action_required", "startup_failure")


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def reduce_open(payload: Any) -> dict[str, Any] | None:
    """رقمُ كلّ طلبٍ مفتوحٍ وطرفُ رأسِه وكونُه مسوّدةً وهل الدمجُ التلقائيُّ مفعَّل وآخرُ تحديثٍ — بلا نصّ."""
    if not isinstance(payload, list):
        return None
    rows: list[list[Any]] = []
    for pull in payload:
        if not isinstance(pull, dict):
            continue
        number = _int(pull.get("number"))
        raw_head = pull.get("head")
        head: dict[str, Any] = raw_head if isinstance(raw_head, dict) else {}
        raw_sha = head.get("sha")
        sha: str = raw_sha if isinstance(raw_sha, str) else ""
        if number is None or not sha.isalnum():
            continue
        updated = github.epoch(pull.get("updated_at"))
        rows.append(
            [number, sha[:40], bool(pull.get("draft")), pull.get("auto_merge") is not None, updated]
        )
    return {"rows": rows}


def reduce_detail(payload: Any) -> dict[str, Any] | None:
    state = payload.get("mergeable_state") if isinstance(payload, dict) else None
    return {"state": _MAP.get(str(state), "unknown")} if isinstance(payload, dict) else None


def reduce_checks(payload: Any) -> dict[str, Any] | None:
    runs = payload.get("check_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    done = [r for r in runs if isinstance(r, dict) and r.get("status") == "completed"]
    return {
        "total": len(runs),
        "ok": sum(1 for r in done if r.get("conclusion") in ("success", "skipped", "neutral")),
        "bad": sum(1 for r in done if r.get("conclusion") in _FAIL),
    }


def level(rows: list[dict[str, Any]], now: float) -> str:
    """أسوأُ حالةٍ بين الطلبات غيرِ المسوّدة: أحمرُ إن بقي التعارضُ أو الفحصُ الفاشل بلا لمسٍ فوق STUCK_HOURS."""
    status = contract.OK
    for row in rows:
        if row["state"] == "draft" or not (row["state"] == "conflict" or row["bad"]):
            continue
        idle = row["idle_hours"]
        if idle is not None and idle > STUCK_HOURS:
            return contract.BAD
        status = contract.WARN
    return status


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    opened = github.fetch(OPEN_PATH, reduce_open)
    if opened is None:
        failed(PANEL, "github")
        return
    rows: list[dict[str, Any]] = []
    for number, sha, draft, auto, updated in opened["rows"][:MAX_ROWS]:
        detail = github.fetch(f"pulls/{number}", reduce_detail)
        checks = github.fetch(f"commits/{sha}/check-runs?per_page=100", reduce_checks)
        state = "draft" if draft else (detail["state"] if detail else "unknown")
        rows.append(
            {
                "n": number,
                "state": state,
                "auto": auto,
                "ok": checks["ok"] if checks else 0,
                "total": checks["total"] if checks else 0,
                "bad": checks["bad"] if checks else 0,
                "idle_hours": None
                if updated is None
                else max(0.0, (moment - float(updated)) / 3600),
            }
        )
    live = [r for r in rows if r["state"] != "draft"]
    conflicts = sum(1 for r in live if r["state"] == "conflict")
    red = sum(1 for r in live if r["bad"])
    data: dict[str, Any] = {}
    for index, row in enumerate(rows, start=1):
        data[f"pr{index}_n"] = row["n"]
        data[f"pr{index}_s"] = row["state"]
        data[f"pr{index}_a"] = 1 if row["auto"] else 0
        data[f"pr{index}_ok"] = row["ok"]
        data[f"pr{index}_t"] = row["total"]
        data[f"pr{index}_b"] = row["bad"]
        data[f"pr{index}_h"] = -1 if row["idle_hours"] is None else int(row["idle_hours"])
    data["rows"] = len(rows)
    status = level(rows, moment)
    if not live:
        headline, gauge = "لا طلباتٍ مفتوحةً غيرَ المسوّدات", 100
    elif conflicts or red:
        headline, gauge = (
            f"{conflicts} تعارضٌ و{red} فحصٌ فاشل بين {len(live)} طلباً",
            100 - 25 * min(4, conflicts + red),
        )
    else:
        headline, gauge = f"{len(live)} طلباً مفتوحاً بلا تعارضٍ ولا فحصٍ فاشل", 100
    summary = (
        ("مفتوحةٌ (بلا المسوّدات)", len(live)),
        ("مسوّدات", len(rows) - len(live)),
        ("تعارضات", conflicts),
        ("فحوصٌ فاشلة", red),
    )
    for index, (label, value) in enumerate(summary, start=1):
        data[f"m{index}_l"], data[f"m{index}_v"] = label, str(value)
    # صفوفُ الجدول مسطَّحةٌ في بيانات اللوحة نفسِها فتقرؤها صفحةُ الحالة، ومعها ما يعرضه QCC (الحالةُ والجملةُ والقرصُ والمؤشّرات)
    contract.store(
        PANEL,
        {"status": status, "headline": headline[: contract.MAX_STRING], "gauge": gauge, **data},
    )
