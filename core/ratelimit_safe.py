"""`@ratelimit` يفتح عند سقوط Redis — لا 500 على باب الدخول.

`django_ratelimit.core.get_usage` يلتقط `socket.gaierror` وحده حول
`cache.add()`؛ إعدادُ المكتبة `RATELIMIT_FAIL_OPEN` يعالج فرعاً آخر تماماً
(الـcache أعاد ``None``/``False`` بلا استثناء — مثل مفتاحٍ منتهٍ)، لا فشل
الاتّصال نفسِه. فحين يسقط Redis فعلاً ترفع `redis.exceptions.ConnectionError`
من داخل المكتبة قبل أن تصل شيفرتَنا، فيسقط العرضُ كلُّه (500) — على باب
الدخول تحديداً، حيث القفل الحقيقيّ عند axes (قاعدةُ بياناتٍ لا Redis) يبقى
عاملاً كاملاً بغضّ النظر.

فهذا المُزيِّن يلفّ ``ratelimit`` الأصليّ: خطأُ Redis يُعامَل كـ«غير محدود»
(فتحٌ صريح)، وأيّ استثناءٍ آخر — وأهمّه ``Ratelimited`` نفسُه عند تجاوز الحدّ
فعلاً — يمرّ كما هو.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

import redis
from django.http import HttpRequest, HttpResponse
from django_ratelimit.decorators import ratelimit as _ratelimit

logger = logging.getLogger(__name__)

_ViewFn = Callable[..., HttpResponse]

# سقوطُ Redis كان يُسجَّل بـ`warning` فقط — وSentry (production.py) يرفع
# LoggingIntegration إلى الأحداث عند `event_level="ERROR"` فما دونه، فلا
# يصل تنبيهٌ فعليّ لأحد حين يُفتح الباب فعلاً. لكن كلَّ طلبٍ يُخفق فيه Redis
# أثناء انقطاعٍ فعليّ يمرّ من هنا، فرفعُ المستوى وحده يُغرق Sentry بحادثةٍ
# واحدة مستمرّة — فتهدئةٌ محليّةٌ (بلا Redis، فهو المُنهار أصلاً) تحدّ التنبيه
# الحقيقيّ إلى مرّةٍ كلَّ 5 دقائق لكلّ عامل، والباقي يبقى في السجلّ فقط.
_ALERT_COOLOFF_SECONDS = 300
_last_alert_at = 0.0


def _report_fail_open(exc: Exception) -> None:
    global _last_alert_at
    now = time.monotonic()
    if now - _last_alert_at >= _ALERT_COOLOFF_SECONDS:
        _last_alert_at = now
        logger.error("ratelimit check failed open — redis unreachable: %s", exc)
    else:
        logger.warning("ratelimit check failed open — redis unreachable (throttled): %s", exc)


def ratelimit(*args: Any, **kwargs: Any) -> Callable[[_ViewFn], _ViewFn]:
    build = _ratelimit(*args, **kwargs)

    def decorator(fn: _ViewFn) -> _ViewFn:
        limited_fn: _ViewFn = build(fn)

        @functools.wraps(fn)
        def _fail_open(request: HttpRequest, *a: Any, **kw: Any) -> HttpResponse:
            try:
                return limited_fn(request, *a, **kw)
            except (OSError, ConnectionError, redis.exceptions.RedisError) as exc:
                _report_fail_open(exc)
                return fn(request, *a, **kw)

        return _fail_open

    return decorator
