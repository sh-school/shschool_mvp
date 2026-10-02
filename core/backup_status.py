"""حالةُ النسخ الاحتياطيّ اليوميّ لبطاقة «النسخ الاحتياطيّ» في رئيسيّة الإدارة (OWN-23).

النسخُ يجري في GitHub Actions (`.github/workflows/backup.yml`، يوميّاً، pg_dump ← gpg ← R2)، لا داخل Django،
فالمنصّةُ لا ترى نتيجتَه بنفسها. والمستودعُ **عامّ** (قرارٌ نهائيّ 2026-09-03)، فواجهةُ GitHub العامّةُ تُخبر بآخر
تشغيلٍ ناجحٍ بلا مفتاحٍ ولا سرٍّ ولا تعديلِ workflow: تُجلب الحالةُ في مهمّة Celery كلَّ نصف ساعة إلى الـcache،
والبطاقةُ تقرأ الـcache وحدَه — لا طلبَ خارجيّاً عند رسم الصفحة (ما فوق 300ms خلفيّ).

ما يُخزَّن أرقامٌ وتصنيفٌ فقط (زمنا آخر نجاحٍ وآخر تشغيلٍ منتهٍ، ونتيجةُ الأخير، وزمنُ الجلب) — لا نصَّ من ردّ
GitHub، فردُّه بياناتٌ من طرفٍ خارجيٍّ لا تُعرَض. والرابطُ يُبنى من ثابتٍ لا من الردّ. الحدُّ غيرُ المصادَق 60 طلباً في الساعة
لكلّ IP مشترك، وطلبان في الساعة يكفيان؛ وإن رُفض الطلبُ (403) أو انقطع بقيت آخرُ حالةٍ معروفةٍ ووُسمت «قديمة» في البطاقة.

**لا رجوعَ إلى الوراء** (W-20260929-014، حادثة 09-29): ردٌّ بـ200 أعاد أحدثَ نجاحٍ إلى 09-24 وقد رُئي نجاحُ 09-29 قبله،
فتقلّبت البطاقةُ بين «9 ساعات» و«5 أيّام» بلا سطرِ خطأ (محتوًى قديمٌ من طبقة التخزين عند GitHub، قراءةُ 0601 للـcache الحيّ).
فأحدثُ نجاحٍ وأحدثُ تشغيلٍ لا ينقصان عمّا حُفظ — التشغيلاتُ لا تُمحى من الماضي — ويُسجَّل تحذيرٌ حين يصل ردٌّ أقدم.
والطلبُ يحمل `QCC_GITHUB_TOKEN` إن ضُبط (قراءةٌ فقط، لا يُخزَّن ولا يُسجَّل): حدٌّ أعلى وأقلُّ عرضةً للمحتوى المخزَّن.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_REPO = "sh-school/shschool_mvp"
WORKFLOW_FILE = "backup.yml"
CACHE_KEY = "backup:status"
#: أسبوع: الحالةُ تبقى مقروءةً (قديمةً) ولو انقطع الجلبُ بدل أن تختفي فتُقرأ «غيرَ معلومة».
_TTL_SECONDS = 7 * 24 * 3600
_TIMEOUT = (3.05, 5)
#: نتائجُ تُحسب فشلاً؛ و«cancelled»/«skipped» ليست نسخاً ولا فشلاً فلا تُحسب.
FAILED = ("failure", "timed_out")
_COUNTED = ("success", *FAILED)


def repo() -> str:
    return str(getattr(settings, "BACKUP_STATUS_REPO", DEFAULT_REPO))


def workflow_url() -> str:
    """صفحةُ الـworkflow في GitHub — ثابتٌ مبنيٌّ من المستودع لا من ردّ الطرف الخارجيّ."""
    return f"https://github.com/{repo()}/actions/workflows/{WORKFLOW_FILE}"


def _api_url() -> str:
    return (
        f"https://api.github.com/repos/{repo()}/actions/workflows/{WORKFLOW_FILE}/runs"
        "?status=completed&branch=main&per_page=10"
    )


def _epoch(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def parse(payload: Any) -> dict[str, Any] | None:
    """من ردّ GitHub إلى {success_at, latest_at, latest_ok} — أو None إن لم يكن الردُّ قابلاً للقراءة.

    الأحدثُ أوّلاً في الردّ. `success_at` زمنُ أحدث نجاح (أو None إن لم يُوجد في الصفحة)، و`latest_*` آخرُ تشغيلٍ
    حُسمت نتيجتُه (نجاحٌ أو فشل) — ويُتجاهل الملغى والمتخطّى.
    """
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None
    counted = [
        (_epoch(run.get("updated_at")), run.get("conclusion"))
        for run in runs
        if isinstance(run, dict) and run.get("conclusion") in _COUNTED
    ]
    counted = [(at, conclusion) for at, conclusion in counted if at is not None]
    success_at = next((at for at, conclusion in counted if conclusion == "success"), None)
    if not counted:
        return {"success_at": success_at, "latest_at": None, "latest_ok": None}
    latest_at, latest_conclusion = counted[0]
    return {
        "success_at": success_at,
        "latest_at": latest_at,
        "latest_ok": latest_conclusion == "success",
    }


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "schoolos-admin-monitor"}
    token = str(getattr(settings, "QCC_GITHUB_TOKEN", "") or "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _later(new: float | None, old: Any) -> float | None:
    """الأحدثُ من زمنين (None = غيرُ معلوم فيُؤخذ الآخر)."""
    if not isinstance(old, int | float):
        return new
    return old if new is None or new < old else new


def merge(parsed: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """يدمج ردّاً جديداً بالمحفوظ فلا يرجع أحدثُ نجاحٍ ولا أحدثُ تشغيلٍ إلى الوراء.

    نتيجةُ الأخير (`latest_ok`) تتبع التشغيلَ الذي بقي أحدث: إن كان المحفوظُ أحدثَ من الردّ بقيت نتيجتُه.
    """
    if not isinstance(previous, dict):
        return dict(parsed)
    old_success, old_latest = previous.get("success_at"), previous.get("latest_at")
    merged = dict(parsed)
    merged["success_at"] = _later(parsed.get("success_at"), old_success)
    latest = _later(parsed.get("latest_at"), old_latest)
    if latest != parsed.get("latest_at"):
        merged["latest_at"], merged["latest_ok"] = latest, previous.get("latest_ok")
    if merged["success_at"] != parsed.get("success_at") or latest != parsed.get("latest_at"):
        logger.warning(
            "backup status: GitHub reply is older than the stored status; kept the newer one"
        )
    return merged


def refresh(now: float | None = None) -> bool:
    """يجلب الحالةَ ويحفظها — يُعيد نجاحَ الجلب. عند الفشل تبقى آخرُ حالةٍ معروفة ولا يُرفع شيء."""
    moment = time.time() if now is None else now
    try:
        response = requests.get(_api_url(), headers=_headers(), timeout=_TIMEOUT)
        if response.status_code != 200:
            logger.warning("backup status: GitHub answered %s", response.status_code)
            return False
        parsed = parse(response.json())
    except (requests.RequestException, ValueError):
        logger.warning("backup status: could not reach GitHub", exc_info=True)
        return False
    if parsed is None:
        logger.warning("backup status: unreadable GitHub reply")
        return False
    cache.set(CACHE_KEY, {**merge(parsed, read()), "fetched_at": moment}, _TTL_SECONDS)
    return True


def read() -> dict[str, Any] | None:
    """آخرُ حالةٍ محفوظة: {success_at, latest_at, latest_ok, fetched_at} أو None قبل أوّل جلب."""
    value = cache.get(CACHE_KEY)
    return value if isinstance(value, dict) else None
