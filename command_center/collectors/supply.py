"""لوحةُ «الفحص الأمنيّ والاعتماديّات» — `security-scan` (GitHub العامّ) وتنبيهاتُ الأمن الثلاثة إن ضُبط رمزُ القراءة.

- **الفحصُ**: آخرُ تشغيلٍ محسومٍ لـ`security-scan.yml` (SAST وثغراتُ PyPI، أسبوعيٌّ ويومَ الدفع). فشلُه «انتبه» ثمّ أحمرُ بعد 24 ساعةً بلا إصلاح (كـCI)،
  وأقدمُ من 9 أيّامٍ «انتبه» (الجدولُ أسبوعيّ) وأقدمُ من 16 أحمر.
- **التنبيهات** (`QCC_GITHUB_TOKEN` اختياريّ): أحمرُ إن وُجد `critical` مفتوحٌ و«انتبه» لـ`high`. **بلا رمزٍ لا تُعرض** (واجهةُ التنبيهات لا تعمل بلا مصادقة) —
  فيُكتب «غيرُ مفعَّلة» لا صفر. أعدادٌ فقط، لا اسمُ حزمةٍ ولا وصف.
- **فحصُ الشيفرة والأسرار** (الرمزُ نفسُه، D-50م: كانت «0203 · الرصد والإنذارات» تقرؤها يدويّاً بـ`gh api`): `code-scanning` بدرجته الأمنيّة
  (`critical` أحمرُ و`high` «انتبه»؛ قواعدُ الجودة بلا درجةٍ أمنيّةٍ لا تُعدّ)، وأيُّ سرٍّ مكشوفٍ مفتوحٍ في `secret-scanning` **أحمر**.
  وتعذّرُ أحدِها (رمزٌ بلا صلاحيّته) يُكتب «غيرُ متاح» ولا يُسقط غيرَه ولا يُحسب سليماً. أعدادٌ فقط: لا قاعدةَ ولا مسارَ ولا نوعَ سرّ.
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
CODE_PATH = "code-scanning/alerts?state=open&per_page=100"
LEAKS_PATH = "secret-scanning/alerts?state=open&per_page=100"
SEVERITIES = ("critical", "high", "medium", "low")
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
    return {name: severities.count(name) for name in SEVERITIES}


def reduce_code(payload: Any) -> dict[str, Any] | None:
    """تنبيهاتُ فحص الشيفرة بدرجتها الأمنيّة وحدَها — نتائجُ الجودة (`warning`/`note` بلا `security_severity_level`) ليست ثغرات."""
    if not isinstance(payload, list):
        return None
    levels = [
        (a.get("rule") or {}).get("security_severity_level") for a in payload if isinstance(a, dict)
    ]
    return {name: levels.count(name) for name in SEVERITIES}


def reduce_secrets(payload: Any) -> dict[str, Any] | None:
    return (
        {"open": sum(1 for a in payload if isinstance(a, dict))}
        if isinstance(payload, list)
        else None
    )


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


def secrets_level(secrets: dict[str, int]) -> str:
    return contract.BAD if secrets["open"] else contract.OK


def code_secrets_text(code: dict[str, int] | None, secrets: dict[str, int] | None) -> str:
    """«حرجةٌ/عاليةٌ في الشيفرة · أسرارٌ مكشوفة» — وما تعذّر جلبُه «غيرُ متاح» لا صفر."""
    code_text = "غيرُ متاح" if code is None else f"{code['critical']} / {code['high']}"
    secrets_text = "غيرُ متاح" if secrets is None else str(secrets["open"])
    return f"{code_text} · أسرار {secrets_text}"


def collect(now: float | None = None) -> None:
    moment = time.time() if now is None else now
    scan = github.fetch(SCAN_PATH, reduce_scan)
    if scan is None:
        failed(PANEL, "github")
        return
    levels = [scan_level(scan, moment)]
    alerts = code = secrets = None
    token = bool(getattr(settings, "QCC_GITHUB_TOKEN", ""))
    if token:
        alerts = github.fetch(ALERTS_PATH, reduce_alerts)
        code = github.fetch(CODE_PATH, reduce_code)
        secrets = github.fetch(LEAKS_PATH, reduce_secrets)
        levels += [alerts_level(x) for x in (alerts, code) if x is not None]
        if secrets is not None:
            levels.append(secrets_level(secrets))
    overall = worst(levels)
    scan_text = "لم يُشغَّل" if scan["at"] is None else ("ناجح" if scan["ok"] else "فشل")
    age_days = None if scan["at"] is None else max(0, int((moment - float(scan["at"])) // 86400))
    if secrets is not None and secrets["open"]:
        headline = f"{secrets['open']} سرّاً مكشوفاً في المستودع"
    elif alerts is not None and alerts["critical"]:
        headline = f"{alerts['critical']} تنبيهاً حرجاً في الاعتماديّات"
    elif code is not None and code["critical"]:
        headline = f"{code['critical']} تنبيهاً حرجاً في فحص الشيفرة"
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
            (
                "الشيفرة حرجة / عالية · الأسرار",
                code_secrets_text(code, secrets) if token else "غيرُ مفعَّلة (بلا رمز)",
            ),
        ),
    )
