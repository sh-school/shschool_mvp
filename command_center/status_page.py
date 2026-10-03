"""صفحةُ «حالةُ اليوم» للمالك — تركيبٌ من لوحات مركز قيادة الجودة القائمة بلا مجمِّعٍ جديدٍ ولا قراءةِ شبكةٍ عند الرسم (W-20261002-022).

المالكُ كان يسأل يدويّاً نحو 30 مرّةً في اليوم: أيُّ الطلبات في الطابور؟ هل هناك أحمر؟ تعارضات؟ هل تمّ النشر؟ والجوابُ كلُّه مقروءٌ من
اللقطة (cache) التي تجمعها المجمِّعاتُ في الخلفيّة؛ فهذه الوحدةُ تجمعه في صفحةٍ واحدة بقراءةِ cache فقط (عقدُ `contract.py`).
المرحلةُ 1 من GitHub العامّ وحدَه. ما لا يراه الخادمُ — ما ينتظر اعتمادَه وحالةُ 8500 والشريط — يأتي في المرحلة 2 من مرآة الفلو (لا يُدّعى هنا).
"""

from __future__ import annotations

import time
from typing import Any

from django.core.cache import cache

from command_center import contract

STATE_LABELS = {
    "draft": "مسوّدة",
    "conflict": "تعارضٌ مع main",
    "behind": "متأخّرٌ عن main",
    "blocked": "ينتظر فحوصاً أو اعتماداً",
    "unstable": "فحصٌ غيرُ إلزاميٍّ فاشل",
    "clean": "جاهزٌ للدمج",
    "unknown": "غيرُ معروف",
}
#: طلباتٌ تحتاج نظراً: تعارضٌ أو فحصٌ فاشل (المسوّداتُ لا تُعدّ).
NEEDS_EYES = ("conflict", "unstable")


def _metric(panel: dict[str, Any], label: str) -> str | None:
    return next((m["value"] for m in panel["metrics"] if m["label"] == label), None)


def queue_rows() -> list[dict[str, Any]]:
    """صفوفُ جدول الطابور من بيانات لوحة `queue` المسطَّحة — تُرفض البياناتُ غيرُ الصالحة فيعود فارغاً."""
    envelope = cache.get(contract.cache_key("queue"))
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict) or not contract.valid_data(data):
        return []
    count = data.get("rows")
    rows: list[dict[str, Any]] = []
    for index in range(1, (count if isinstance(count, int) else 0) + 1):
        number, state = data.get(f"pr{index}_n"), data.get(f"pr{index}_s")
        if not isinstance(number, int) or state not in STATE_LABELS:
            continue
        idle = data.get(f"pr{index}_h")
        rows.append(
            {
                "number": number,
                "state": state,
                "label": STATE_LABELS[str(state)],
                "auto": data.get(f"pr{index}_a") == 1,
                "checks_ok": data.get(f"pr{index}_ok", 0),
                "checks_total": data.get(f"pr{index}_t", 0),
                "checks_bad": data.get(f"pr{index}_b", 0),
                "idle_hours": idle if isinstance(idle, int) and idle >= 0 else None,
                "needs_eyes": state in NEEDS_EYES or bool(data.get(f"pr{index}_b")),
            }
        )
    return rows


def build(now: float | None = None) -> dict[str, Any]:
    """سياقُ الصفحة: الأجوبةُ الأربعةُ في رأسها ثمّ الجدول."""
    moment = time.time() if now is None else now
    panels = {p["key"]: p for p in contract.read_panels(moment)}
    rows = queue_rows()
    unpublished = _metric(panels["pulls"], "إيداعاتٌ غيرُ منشورة")
    live = [r for r in rows if r["state"] != "draft"]
    return {
        "rows": rows,
        "reds": [p["title"] for p in panels.values() if p["status"] == contract.BAD],
        "unknown": [p["title"] for p in panels.values() if p["status"] == contract.UNKNOWN],
        "conflicts": [r["number"] for r in rows if r["state"] == "conflict"],
        "ready": sum(1 for r in live if r["state"] == "clean"),
        "live": len(live),
        "unpublished": unpublished,
        "deployed_clean": unpublished == "0",
        "queue_age": panels["queue"]["age_seconds"],
    }
