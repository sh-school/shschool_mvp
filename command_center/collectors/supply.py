"""لوحةُ «الفحص الأمنيّ والاعتماديّات» — `security-scan` (GitHub العامّ) وتنبيهاتُ Dependabot إن ضُبط رمزُ القراءة.

- **الفحصُ**: آخرُ تشغيلٍ محسومٍ لـ`security-scan.yml` (SAST وثغراتُ PyPI، أسبوعيٌّ ويومَ الدفع). فشلُه «انتبه» ثمّ أحمرُ بعد 24 ساعةً بلا إصلاح (كـCI)،
  وأقدمُ من 9 أيّامٍ «انتبه» (الجدولُ أسبوعيّ) وأقدمُ من 16 أحمر.
- **التنبيهات** (`QCC_GITHUB_TOKEN` اختياريّ): أحمرُ إن وُجد `critical` مفتوحٌ و«انتبه» لـ`high`. **بلا رمزٍ لا تُعرض** (واجهةُ التنبيهات لا تعمل بلا مصادقة) —
  فيُكتب «غيرُ مفعَّلة» لا صفر. أعدادٌ فقط، لا اسمُ حزمةٍ ولا وصف.
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings

from command_center import contract
from command_center.collectors import github
from command_center.collectors.publish import failed, publish, score, worst

PANEL = "supply"
SCAN_PATH = "actions/workflows/security-scan.yml/runs?status=completed&per_page=10"
ALERTS_PATH = "dependabot/alerts?state=open&per_page=100"
FAILURES = ("failure", "timed_out")
COUNTED = ("success", *FAILURES)
WARN_DAYS, BAD_DAYS = 9, 16
RED_BAD_AFTER = 24 * 3600


def reduce_scan(payload: Any) -> dict[str, Any] | None:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    counted = [
        (github.epoch(r.get("updated_at")), r.get("conclusion"))
        for r in runs
        if isinstance(r, dict) and r.get("conclusion") in COUNTED
    ]
    counted = [(t, c) for t, c in counted if t is not None]
    if not counted:
        return {"at": None, "ok": None}
    return {"at": counted[0][0], "ok": counted[0][1] == "success"}


def reduce_alerts(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    severities = [
        (a.get("security_advisory") or {}).get("severity") for a in payload if isinstance(a, dict)
    ]
    return {name: severities.count(name) for name in ("critical", "high", "medium", "low")}


def scan_level(scan: dict[str, Any], now: float) -> str:
    if scan["at"] is None:
        return contract.WARN
    age = now - float(scan["at"])
    if scan["ok"] is False:
        return contract.BAD if age > RED_BAD_AFTER else contract.WARN
    if age > BAD_DAYS * 86400:
        return contract.BAD
    return contract.WARN if age > WARN_DAYS * 86400 else contract.OK


def alerts_level(alerts: dict[str, int]) -> str:
    if alerts["critical"]:
        return contract.BAD
    return contract.WARN if alerts["high"] else contract.OK


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    scan = github.fetch(SCAN_PATH, reduce_scan)
    if scan is None:
        failed(PANEL, "github")
        return
    levels = [scan_level(scan, moment)]
    alerts = None
    if getattr(settings, "QCC_GITHUB_TOKEN", ""):
        alerts = github.fetch(ALERTS_PATH, reduce_alerts)
        if alerts is not None:
            levels.append(alerts_level(alerts))
    overall = worst(levels)
    scan_text = "لم يُشغَّل" if scan["at"] is None else ("ناجح" if scan["ok"] else "فشل")
    age_days = None if scan["at"] is None else max(0, int((moment - float(scan["at"])) // 86400))
    if alerts is not None and alerts["critical"]:
        headline = f"{alerts['critical']} تنبيهاً حرجاً في الاعتماديّات"
    elif overall == contract.OK:
        headline = "الفحصُ الأمنيُّ نظيف"
    else:
        headline = "الفحصُ الأمنيُّ بحاجةٍ إلى نظر"
    alerts_text = (
        "غيرُ مفعَّلة (بلا رمز)" if alerts is None else f"{alerts['critical']} / {alerts['high']}"
    )
    publish(
        PANEL,
        status=overall,
        headline=headline,
        gauge=score(levels),
        metrics=(
            ("آخرُ فحص", scan_text),
            ("عمرُه", "—" if age_days is None else f"{age_days} يوماً"),
            ("تنبيهاتٌ حرجة / عالية", alerts_text),
        ),
    )
