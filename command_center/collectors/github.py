"""جلبُ واجهة GitHub العامّة لمجمِّعَي CI والطلبات — بلا رمزٍ ولا سرّ (المستودعُ عامّ).

الحدُّ غيرُ المصادَق 60 طلباً في الساعة لكلّ IP مشترك، فكلُّ جلبٍ **شرطيّ**: يُحفظ ETag مع **الخلاصة** التي حسبها المجمِّعُ
(أرقامٌ لا نصوصٌ من طرفٍ ثالث: لا عنوانَ طلبٍ ولا اسمَ كاتب) وردُّ 304 يعيد الخلاصةَ المحفوظةَ ولا يُحتسب ضمن الحدّ.
عطلُ الجلب (شبكةٌ أو 403/429 أو ردٌّ غيرُ مفهوم) يعيد None فيبقى المجمِّعُ على آخر قيمةٍ سليمةٍ ويُعلَّم اللوحةَ «انتبه».
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_REPO = "sh-school/shschool_mvp"
_TIMEOUT = (3.05, 5)
_TTL = 7 * 24 * 3600
Reducer = Callable[[Any], dict[str, Any] | None]


def repo() -> str:
    return str(getattr(settings, "BACKUP_STATUS_REPO", DEFAULT_REPO))


def epoch(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def cache_key(path: str) -> str:
    url = f"https://api.github.com/repos/{repo()}/{path}"
    return "qcc:gh:" + hashlib.sha256(url.encode()).hexdigest()[:20]


def fetch(path: str, reduce: Reducer) -> dict[str, Any] | None:
    """`path` تحت `/repos/<repo>/` ← خلاصةُ `reduce(json)` أو None عند العطل."""
    url = f"https://api.github.com/repos/{repo()}/{path}"
    key = cache_key(path)
    cached = cache.get(key)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "schoolos-command-center"}
    if isinstance(cached, dict) and cached.get("etag"):
        headers["If-None-Match"] = str(cached["etag"])
    try:
        response = requests.get(url, headers=headers, timeout=_TIMEOUT)
        if response.status_code == 304 and isinstance(cached, dict):
            summary = cached.get("summary")
            return summary if isinstance(summary, dict) else None
        if response.status_code != 200:
            logger.warning("command center: GitHub answered %s", response.status_code)
            return None
        summary = reduce(response.json())
    except (requests.RequestException, ValueError):
        logger.warning("command center: could not reach GitHub", exc_info=True)
        return None
    if summary is None:
        logger.warning("command center: unreadable GitHub reply")
        return None
    etag = response.headers.get("ETag", "")
    if etag:
        cache.set(key, {"etag": etag, "summary": summary}, _TTL)
    return summary
