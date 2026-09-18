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
from collections.abc import Callable
from typing import Any

import redis
from django.http import HttpRequest, HttpResponse
from django_ratelimit.decorators import ratelimit as _ratelimit

logger = logging.getLogger(__name__)

_ViewFn = Callable[..., HttpResponse]


def ratelimit(*args: Any, **kwargs: Any) -> Callable[[_ViewFn], _ViewFn]:
    build = _ratelimit(*args, **kwargs)

    def decorator(fn: _ViewFn) -> _ViewFn:
        limited_fn: _ViewFn = build(fn)

        @functools.wraps(fn)
        def _fail_open(request: HttpRequest, *a: Any, **kw: Any) -> HttpResponse:
            try:
                return limited_fn(request, *a, **kw)
            except (OSError, ConnectionError, redis.exceptions.RedisError) as exc:
                logger.warning("ratelimit check failed open — redis unreachable: %s", exc)
                return fn(request, *a, **kw)

        return _fail_open

    return decorator
