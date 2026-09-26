"""لوحةُ «صحّة الإنتاج والنشر» — تُجمَع من بطاقاتِ مراقبة المطوّر القائمة (`roadmap/admin_monitor.py`) بلا تكرار منطقها.

أربعُ بطاقاتٍ تُحسَب كلٌّ في دالّتها (قاعدةُ البيانات والـcache، والعاملُ ونبضتُه، وأخطاءُ 5xx، والنسخُ الاحتياطيّ)
+ الهجراتُ المعلَّقة. وبطاقتا «الإشعارات» و«الأمان» **خارجَ** المجمِّع عمداً: جدولاهما بسياسة RLS لكلّ مدرسة، والمجمِّعُ يعمل بلا
سياقِ مدرسةٍ فيقرأ صفراً كاذباً — تبقيان في رئيسيّة الإدارة حيث للطلب مدرسة. وبطاقةٌ تتعطّل لا تُسقط اللوحة: تُعدّ فحصاً «انتبه». الهجرةُ المعلَّقةُ أكثرَ من
عشر دقائقَ (الإيداعُ نُشر ولم تُطبَّق هجرتُه) أحمرُ — فأوّلُ ظهورٍ لها يُختَم في الـcache ويُقاس منه.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from command_center import contract
from command_center.collectors.publish import publish, score, worst
from roadmap import admin_monitor

logger = logging.getLogger(__name__)

PANEL = "production"
PENDING_SINCE_KEY = "qcc:migrations:pending_since"
#: هجرةٌ معلَّقةٌ فوق هذا الحدّ (ثوانٍ) بعد ظهورها = أحمر.
PENDING_BAD_AFTER = 10 * 60

CARDS: tuple[Callable[[], admin_monitor.Card], ...] = (
    admin_monitor.platform_health,
    admin_monitor.worker,
    admin_monitor.server_errors,
    admin_monitor.backup,
)


def pending_migrations() -> int:
    """عددُ الهجراتِ التي لم تُطبَّق بعد على القاعدة الحاليّة."""
    executor = MigrationExecutor(connection)
    return len(executor.migration_plan(executor.loader.graph.leaf_nodes()))


def migrations_level(pending: int, now: float | None = None) -> str:
    """ok بلا معلَّق؛ وإلّا warn ثمّ bad متى مضت عليه أكثرُ من `PENDING_BAD_AFTER` منذ أوّل مشاهدة."""
    moment = time.time() if now is None else now
    if not pending:
        cache.delete(PENDING_SINCE_KEY)
        return contract.OK
    cache.add(PENDING_SINCE_KEY, moment, 7 * 24 * 3600)
    since = float(cache.get(PENDING_SINCE_KEY) or moment)
    return contract.BAD if moment - since > PENDING_BAD_AFTER else contract.WARN


def _cards() -> list[admin_monitor.Card | None]:
    cards: list[admin_monitor.Card | None] = []
    for build in CARDS:
        try:
            cards.append(build())
        except Exception:  # noqa: BLE001 — بطاقةٌ معطوبةٌ تُعدّ فحصاً «انتبه» ولا تُسقط اللوحة
            logger.warning("command center: card %s failed", build.__name__, exc_info=True)
            cards.append(None)
    return cards


def collect(now: float | None = None) -> None:
    cards = _cards()
    pending = pending_migrations()
    levels = [card.level if card else contract.WARN for card in cards]
    levels.append(migrations_level(pending, now))
    status = worst(levels)
    troubled = sum(1 for level in levels if level != contract.OK)
    headline = (
        "كلُّ فحوص الإنتاج سليمة"
        if not troubled
        else f"{troubled} من {len(levels)} فحوصٍ بحاجةٍ إلى نظر"
    )
    by_title = {card.title: card for card in cards if card}
    commit = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:7]

    def value(title: str) -> str:
        return by_title[title].value if title in by_title else "؟"

    publish(
        PANEL,
        status=status,
        headline=headline,
        gauge=score(levels),
        detail=f"الإيداع {commit}" if commit else "الإيداعُ غيرُ معلوم هنا (خارج Railway)",
        metrics=(
            ("العامل", value("العامل (Celery)")),
            ("أخطاء 5xx / 24س", value("أخطاء الخادم")),
            ("آخر نسخٍ احتياطيّ", value("النسخ الاحتياطيّ")),
            ("هجراتٌ معلَّقة", pending),
        ),
    )
