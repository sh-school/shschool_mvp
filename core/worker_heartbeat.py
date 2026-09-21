"""core/worker_heartbeat.py — ختمُ نبضة العامل في Redis، ليقرأه فحصٌ خارجيّ.

Sentry Crons على الخطّة المجّانيّة مقعدٌ واحد وقد استنفدته مراقباتٌ أُنشئت تلقائياً
(2026-09-21)، فصارت `worker-heartbeat` بلا check-in أبداً: توقّفُ العامل لا يُنبّه
أحداً. فالنبضةُ تُختَم هنا أيضاً، ويقرؤها `/health/worker/` الذي يفحصه GitHub Actions
من خارج Railway (`.github/workflows/worker-heartbeat.yml`) — لا اعتمادَ على حصّة
طرفٍ ثالث.

الختمُ في الـcache (Redis في الإنتاج) لا في القاعدة: لا جدولَ جديد ولا RLS ولا وثيقةَ
احتفاظ، والعاملُ والويبُ يشتركان في Redis نفسه.
"""

from __future__ import annotations

import time

from django.core.cache import cache

CACHE_KEY = "worker:heartbeat"

#: النبضةُ كلَّ 5 دقائق؛ ثلاثةُ أضعافها كي لا يُنذَر بفوتِ نبضةٍ واحدة أو نشرٍ جارٍ.
MAX_AGE_SECONDS = 900

#: أسبوعٌ: يبقى الختمُ مقروءاً (قديماً) بدل أن يختفيَ فيُقرأ «غائباً» بلا عمر.
_TTL_SECONDS = 7 * 24 * 3600


def record(now: float | None = None) -> None:
    cache.set(CACHE_KEY, time.time() if now is None else now, timeout=_TTL_SECONDS)


def last_beat() -> float | None:
    value = cache.get(CACHE_KEY)
    return float(value) if value is not None else None
