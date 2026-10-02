"""تخطيطُ صفحة «مركز قيادة الجودة» — تصنيفُ اللوحات وتجميعُها وترتيبُها (W-20261002-027، ملاحظةُ المالك 2026-10-02).

كانت اللوحاتُ كلُّها بلاطاتٍ متساويةً في شبكةٍ واحدةٍ بقرصٍ دائريٍّ لكلٍّ منها: قراءةٌ 0–100 مركَّبةٌ اعتباطيّةً (100 ناقصاً عقوبات) لا تقول شيئاً يُفعل.
والآن: ستُّ مجموعاتٍ من الأخطر على المالك إلى الأقلّ، ولكلّ لوحةٍ **رقمُها الحقيقيّ** كبيراً (أحدُ مؤشّراتها الأربعة) وبجانبه **هدفُها** حيث
تُعرّف الشيفرةُ عتبةً فعلاً. وما لا عتبةَ له في مجمِّعه لا يُكتب له هدفٌ هنا — لا رقمَ يُخمَّن (شرطُ المايسترو).

عقدُ اللقطة v1 (`contract.py`) لم يتغيّر: الرقمُ الرئيسيُّ هو مؤشّرٌ بعينه من المؤشّرات الأربعة (`FEATURED`)، فيستمرّ `command_center.js` في تحديثه
بمفاتيح `<لوحة>.m<ن>v` كما كان، والقرصُ (`gauge`) باقٍ في اللقطة لمن يقرؤها لكنّ الصفحةَ لم تعد ترسمه.
"""

from __future__ import annotations

from typing import Any

from command_center import contract
from command_center.collectors import database, guards
from roadmap.admin_monitor import BACKUP_OK_HOURS

#: (مفتاح، عنوان، لوحاتُها بالترتيب) — الأخطرُ على المالك أوّلاً. لوحةٌ غيرُ مسجَّلةٍ في `contract.PANELS` تُتجاوز (فرعٌ لم يُدمج بعدُ).
GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("prod", "الإنتاجُ وجاهزيّته", ("production", "latency", "database", "messaging", "ux")),
    ("security", "الأمانُ والامتثال", ("security", "supply", "compliance")),
    ("shipping", "التسليمُ والنشر", ("queue", "pulls", "today", "delivery", "sync")),
    ("quality", "جودةُ الشيفرة", ("ci", "quality", "guards")),
    ("plan", "الخطّة", ("roadmap",)),
)

#: رقمُ اللوحة الكبير: فهرسُ المؤشّر (1–4) الذي يُعرض كبيراً؛ والمفقودُ يعرض جملةَ اللوحة (headline) كبيرةً.
FEATURED: dict[str, int] = {
    "production": 3,  # آخرُ نسخٍ احتياطيّ
    "latency": 1,
    "database": 2,  # الاتّصالات
    "messaging": 3,  # فاشلةٌ غيرُ محلولة
    "ux": 1,
    "security": 1,
    "supply": 3,  # تنبيهاتٌ حرجة / عالية
    "compliance": 1,  # بلاغاتُ خرقٍ مفتوحة
    "queue": 1,
    "pulls": 3,  # إيداعاتٌ غيرُ منشورة
    "today": 1,
    "delivery": 1,
    "sync": 1,
    "ci": 1,
    "quality": 1,
    "roadmap": 3,  # قراراتٌ بانتظارك
}

#: هدفُ الرقم الكبير — نصٌّ يُبنى من عتبة المجمِّع نفسِه حيث وُجدت (فلا يتباعد)، وإلّا يغيب.
TARGETS: dict[str, str] = {
    "production": f"≤ {BACKUP_OK_HOURS} ساعة",
    "database": f"أقلّ من {round(database.CONN_WARN * 100)}% من الحدّ",
    "messaging": "0",
    "supply": "لا حرجة",
    "compliance": "0",
    "pulls": "0",
    "sync": "0",
    "guards": f"هامشٌ ≥ {guards.BAD_MARGIN} بايتاً",
}

STATE_LABELS = {"ok": "✔ سليم", "warn": "▲ انتبه", "bad": "✖ خطر", "unknown": "؟ غير معلوم"}
_ORDER = (contract.BAD, contract.WARN, contract.UNKNOWN, contract.OK)


def _tile(panel: dict[str, Any]) -> dict[str, Any]:
    """لوحةٌ بحقولها للعرض: الرقمُ الكبير (بفهرسه) وهدفُه، وفتحاتُ المؤشّرات الأخرى بفهارسها الأصليّة.

    عنصرُ الرقم الكبير يُرسم ولو لم تُجمَع اللوحةُ بعدُ («؟») ليجد التحديثُ الحيُّ مكانَه؛ والفتحاتُ تُرسم كلُّها (المفقودةُ مخفيّة).
    """
    index = FEATURED.get(panel["key"])
    metrics = panel["metrics"]
    featured = (
        metrics[index - 1] if index and index <= len(metrics) else {"label": "", "value": "؟"}
    )
    slots = [
        {"i": i, "m": metrics[i - 1] if i <= len(metrics) else None}
        for i in range(1, contract.MAX_METRICS + 1)
        if i != index
    ]
    return {
        **panel,
        "featured_index": index,
        "featured": featured,
        "target": TARGETS.get(panel["key"], ""),
        "slots": slots,
        "state_label": STATE_LABELS.get(panel["status"], STATE_LABELS["unknown"]),
    }


def groups(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """المجموعاتُ بلوحاتها مرتَّبةً داخلها: الأحمرُ ثمّ «انتبه» ثمّ غيرُ المعلوم ثمّ السليم (ثباتُ الترتيب الأصليّ عند التساوي)."""
    by_key = {p["key"]: p for p in panels}
    result = []
    for key, title, members in GROUPS:
        tiles = [_tile(by_key[m]) for m in members if m in by_key]
        if not tiles:
            continue
        tiles.sort(
            key=lambda t: _ORDER.index(t["status"]) if t["status"] in _ORDER else len(_ORDER)
        )
        worst = tiles[0]["status"]
        ok = sum(1 for t in tiles if t["status"] == contract.OK)
        result.append(
            {
                "key": key,
                "title": title,
                "tiles": tiles,
                "worst": worst,
                "worst_label": STATE_LABELS.get(worst, STATE_LABELS["unknown"]),
                "ok": ok,
                "total": len(tiles),
            }
        )
    return result


def strip(panels: list[dict[str, Any]]) -> dict[str, Any]:
    """شريطُ «ما ينتظرك الآن»: ما يراه الخادمُ من مصادره وحدَها — الأحمرُ وغيرُ المعلوم وعددُ الإيداعات غيرِ المنشورة.

    لا قراراتٍ مفتوحةً ولا ما في الدفتر المحلّيّ (لا يراه الخادم) ولا رقمٌ مخمَّن: ما لم تُجمَع لوحتُه يُسمّى «غيرَ معلوم».
    """
    reds = [p["title"] for p in panels if p["status"] == contract.BAD]
    warns = sum(1 for p in panels if p["status"] == contract.WARN)
    unknown = sum(1 for p in panels if p["status"] == contract.UNKNOWN)
    pulls = next((p for p in panels if p["key"] == "pulls"), None)
    unpublished = (
        next((m["value"] for m in pulls["metrics"] if m["label"] == "إيداعاتٌ غيرُ منشورة"), None)
        if pulls
        else None
    )
    return {"reds": reds, "warns": warns, "unknown": unknown, "unpublished": unpublished}
