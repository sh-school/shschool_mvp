"""لوحةُ «قاعدة البيانات» — الحجمُ والاتّصالاتُ وأطولُ استعلامٍ يعمل، من `pg_stat_*` بلا نصِّ استعلامٍ ولا أسماء (قرارُ المالك 2026-09-27).

- **الاتّصالات** نسبةً إلى `max_connections`: «انتبه» من 70% وأحمرُ من 90% (نفادُها يُسقط المنصّةَ كلَّها).
- **أطولُ استعلامٍ نشط**: «انتبه» فوق 30 ثانيةً وأحمرُ فوق 120 (استعلامٌ عالقٌ يحجز صفوفاً وأقفالاً). لا يُخزَّن نصُّه.
- **الحجمُ ونموُّه**: عيّنةٌ يوميّةٌ في الـcache تقارَن بعيّنة قبل 7 أيّام — يُعرض ولا يُحكَم (لا عتبةَ معقولةٌ دون تاريخٍ أطول).
تعمل الاستعلاماتُ بدور العامل؛ غيرُ المشرف لا يرى حالةَ جلساتِ الآخرين فيُعدّ أطولُ استعلامٍ ممّا يراه. والقاعدةُ غيرُ PostgreSQL تفشل بـ`not_postgres` فلا يُخترَع رقم.
"""

from __future__ import annotations

import time

from django.core.cache import cache
from django.db import connection

from command_center import contract
from command_center.collectors.publish import failed, publish, score, worst

PANEL = "database"
CONN_WARN = 0.70
CONN_BAD = 0.90
QUERY_WARN_SECONDS = 30
QUERY_BAD_SECONDS = 120
SIZE_KEY = "qcc:db:size:{day}"
_SIZE_TTL = 10 * 24 * 3600


def connections_level(used: int, limit: int) -> str:
    share = used / limit if limit else 0
    if share >= CONN_BAD:
        return contract.BAD
    return contract.WARN if share >= CONN_WARN else contract.OK


def query_level(seconds: float) -> str:
    if seconds > QUERY_BAD_SECONDS:
        return contract.BAD
    return contract.WARN if seconds > QUERY_WARN_SECONDS else contract.OK


def _size_text(size: int) -> str:
    return f"{size / 1024 / 1024:,.0f}MB" if size < 10 * 1024**3 else f"{size / 1024**3:,.1f}GB"


def _growth(size: int, now: float) -> str:
    day = int(now // 86400)
    cache.add(SIZE_KEY.format(day=day), size, _SIZE_TTL)
    before = cache.get(SIZE_KEY.format(day=day - 7))
    if not before:
        return "—"
    return f"{(size - before) / before * 100:+.1f}%"


def collect(now: float | None = None) -> None:
    if connection.vendor != "postgresql":
        failed(PANEL, "not_postgres")
        return
    moment = time.time() if now is None else now
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        size = int(cursor.fetchone()[0])
        cursor.execute("SELECT current_setting('max_connections')::int")
        limit = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        used = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT coalesce(max(extract(epoch FROM now() - query_start)), 0) FROM pg_stat_activity "
            "WHERE datname = current_database() AND state = 'active' AND pid <> pg_backend_pid()"
        )
        longest = float(cursor.fetchone()[0])
    levels = [connections_level(used, limit), query_level(longest)]
    overall = worst(levels)
    headline = {
        contract.OK: "القاعدةُ سليمة",
        contract.WARN: "القاعدةُ بحاجةٍ إلى نظر",
        contract.BAD: "القاعدةُ في خطر",
    }[overall]
    publish(
        PANEL,
        status=overall,
        headline=headline,
        gauge=score(levels),
        metrics=(
            ("الحجم", f"{_size_text(size)} ({_growth(size, moment)} / 7 أيّام)"),
            ("الاتّصالات", f"{used} من {limit}"),
            ("أطولُ استعلامٍ نشط", f"{int(longest)} ث"),
        ),
    )
