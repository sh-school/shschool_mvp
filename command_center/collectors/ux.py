"""لوحةُ «تجربة المستخدم الفعليّة» — p75 لـLCP وINP وCLS ميدانيّاً لكلّ جهازٍ من عدّادات `command_center/rum.py` (Q-04).

الأرقامُ من زوّارٍ حقيقيّين (عيّنةُ `RUM_SAMPLE_PERCENT`، آخرَ 7 أيّام) لا من المختبر — فتُقارَن بميزانيّة `tests/web_vitals.py`. الحكم على **الهاتف** (الأضعف) وتُعرض
أجهزةُ المكتب والجهاز اللوحيّ في سطر التفصيل. العتباتُ عتباتُ Core Web Vitals: جيّد (LCP ≤ 2500ms، INP ≤ 200ms، CLS ≤ 0.1) وضعيف (> 4000 و> 500 و> 0.25).
- **مطفأ** (`RUM_ENDPOINT` فارغ): «انتبه» بعنوانٍ صريحٍ يقول ما ينقص (مراجعةُ الـDPO وضبطُ المتغيّر) — لا سليمٌ زائف.
- **عيّنةٌ غيرُ كافية** (أقلَّ من 30 على الهاتف): «انتبه» بلا حكم. **ضعيفٌ يُحمَّر** فقط حين تبلغ العيّنةُ 100.
قراءةُ القرص = `score` من حكم المقاييس الثلاثة على الهاتف (100 ناقصاً 12 لكلّ «يحتاج تحسيناً» و35 لكلّ ضعيف).
"""

from __future__ import annotations

from django.conf import settings

from command_center import contract, rum
from command_center.collectors.publish import publish, score, worst

PANEL = "ux"
LABELS = {"lcp": "LCP", "inp": "INP", "cls": "CLS"}
DEVICE_NAMES = {"phone": "هاتف", "tablet": "لوحيّ", "desktop": "مكتب"}
LEVELS = {"good": contract.OK, "needs": contract.WARN, "poor": contract.BAD}


def _show(key: str, p75: float | None) -> str:
    if p75 is None:
        return "—"
    return f"{p75:g}" if key == "cls" else f"{int(p75)}ms"


def collect(now: float | None = None) -> None:
    if not getattr(settings, "RUM_ENDPOINT", ""):
        publish(
            PANEL,
            status=contract.WARN,
            headline="القياسُ الميدانيّ مطفأ (RUM_ENDPOINT فارغ)",
            gauge=None,
            detail="يلزمه موافقةُ الـDPO وضبطُ المتغيّر على الإنتاج (docs/rum_client_contract_2026-09.md)",
        )
        return
    by_device = {device: rum.summary(device, now=now) for device in rum.DEVICES}
    phone = by_device["phone"]
    rated = {
        key: rum.rating(key, phone[key]["p75"], int(phone[key]["n"] or 0)) for key in rum.METRICS
    }
    sample = max(int(phone[key]["n"] or 0) for key in rum.METRICS)
    total = sum(max(int(d[key]["n"] or 0) for key in rum.METRICS) for d in by_device.values())
    if all(value == "none" for value in rated.values()):
        publish(
            PANEL,
            status=contract.WARN,
            headline=f"عيّنةٌ غيرُ كافية على الهاتف ({sample} من {rum.MIN_SAMPLE})",
            gauge=None,
            metrics=(("عيّنات 7 أيّام (كلُّ الأجهزة)", total),),
        )
        return
    levels = [LEVELS[value] for value in rated.values() if value in LEVELS]
    status = worst(levels) if levels else contract.WARN
    weak = [LABELS[key] for key, value in rated.items() if value in ("needs", "poor")]
    headline = (
        "تجربةُ الهاتف جيّدةٌ في المقاييس الثلاثة"
        if not weak
        else "ضعفٌ على الهاتف: " + "، ".join(weak)
    )
    others = " · ".join(
        f"{DEVICE_NAMES[d]}: "
        + " ".join(f"{LABELS[k]} {_show(k, by_device[d][k]['p75'])}" for k in rum.METRICS)
        for d in ("desktop", "tablet")
    )
    publish(
        PANEL,
        status=status,
        headline=headline,
        gauge=score(levels),
        detail=others,
        metrics=(
            ("LCP p75 (هاتف)", _show("lcp", phone["lcp"]["p75"])),
            ("INP p75 (هاتف)", _show("inp", phone["inp"]["p75"])),
            ("CLS p75 (هاتف)", _show("cls", phone["cls"]["p75"])),
            ("عيّنات 7 أيّام", total),
        ),
    )
