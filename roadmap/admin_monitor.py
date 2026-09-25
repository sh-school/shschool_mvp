"""بطاقاتُ مراقبةِ المطوّر في الصفحة الرئيسيّة للإدارة — `{% dev_cards %}`.

قراءةٌ فقط من جداولَ قائمة والـcache (نبضةُ العامل وعدّادُ 5xx) — لا جدولَ جديد، وبلا هويّاتِ أشخاصٍ ولا أسمائهم: أرقامٌ
وحالاتٌ تكفي المطوّرَ ليعرف أين ينظر، ولا تُعرّض بياناتٍ شخصيّةً (PDPPL).
كلُّ بطاقةٍ تُحسَب في دالّةٍ مستقلّةٍ تُعيد `Card` أو `None`، وتعطُّل واحدةٍ لا يُسقط اللوحة.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

OK, WARN, BAD = "ok", "warn", "bad"
FAILED_LOGINS_WARN = 10


@dataclass(frozen=True)
class Card:
    title: str
    value: str
    detail: str
    level: str = OK
    url: str = ""


def _trend(now_count: int, before_count: int) -> str:
    """مقارنةٌ بالأربع والعشرين ساعةً السابقة لها — الاتجاهُ أدلُّ من الرقم وحده."""
    if now_count > before_count:
        return f"↑ أمس {before_count}"
    if now_count < before_count:
        return f"↓ أمس {before_count}"
    return f"= أمس {before_count}"


def _link(name: str, query: str = "") -> str:
    try:
        return reverse(name) + query
    except NoReverseMatch:
        return ""


def platform_health() -> Card:
    problems = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 — البطاقةُ تُبلغ عن أيّ عطل
        problems.append("قاعدة البيانات")
    try:
        cache.set("_adm_health", "1", timeout=5)
        if cache.get("_adm_health") != "1":
            problems.append("الذاكرة المؤقّتة")
    except Exception:  # noqa: BLE001
        problems.append("الذاكرة المؤقّتة")
    version = getattr(settings, "PLATFORM_VERSION", "")
    if problems:
        return Card("صحّة المنصّة", "عطل", "تعذّر: " + "، ".join(problems), BAD)
    return Card("صحّة المنصّة", "سليمة", f"قاعدة البيانات والذاكرة تعملان · الإصدار {version}", OK)


def security(now=None) -> Card:
    from axes.models import AccessAttempt

    from core.models import AuditLog

    now = now or timezone.now()
    failed = AuditLog.objects.filter(
        action__in=("login_failed", "mfa_failed"), timestamp__gte=now - timedelta(hours=24)
    ).count()
    before = AuditLog.objects.filter(
        action__in=("login_failed", "mfa_failed"),
        timestamp__gte=now - timedelta(hours=48),
        timestamp__lt=now - timedelta(hours=24),
    ).count()
    limit = getattr(settings, "AXES_FAILURE_LIMIT", 5)
    cooloff = getattr(settings, "AXES_COOLOFF_TIME", timedelta(minutes=5))
    locked = AccessAttempt.objects.filter(
        failures_since_start__gte=limit, attempt_time__gte=now - cooloff
    ).count()
    level = WARN if locked or failed >= FAILED_LOGINS_WARN else OK
    return Card(
        "الأمان",
        str(failed),
        f"محاولة دخول فاشلة آخر 24 ساعة ({_trend(failed, before)}) · مقفولٌ الآن {locked}",
        level,
        _link("admin:core_auditlog_changelist", "?action__exact=login_failed"),
    )


def worker() -> Card:
    import time

    from core import worker_heartbeat

    beat = worker_heartbeat.last_beat()
    if beat is None:
        return Card("العامل (Celery)", "غائب", "لا نبضةَ مسجَّلة — المهامُّ الخلفيّة لا تعمل", BAD, "")
    minutes = int((time.time() - beat) // 60)
    if time.time() - beat > worker_heartbeat.MAX_AGE_SECONDS:
        return Card("العامل (Celery)", "متوقّف", f"آخرُ نبضةٍ قبل {minutes} دقيقة", BAD, "")
    return Card("العامل (Celery)", "يعمل", f"آخرُ نبضةٍ قبل {minutes} دقيقة", OK, "")


def notifications(now=None) -> Card:
    from notifications.models import DeadLetterMessage, NotificationDelivery

    now = now or timezone.now()
    since = now - timedelta(hours=24)
    counts: dict[str, int] = {}
    for row in NotificationDelivery.objects.filter(created_at__gte=since).values_list(
        "status", flat=True
    ):
        counts[row] = counts.get(row, 0) + 1
    total = sum(counts.values())
    sent = counts.get("sent", 0)
    waiting = counts.get("pending", 0) + counts.get("retry_wait", 0) + counts.get("in_progress", 0)
    dead = DeadLetterMessage.objects.filter(resolved=False).count()
    level = BAD if dead else (WARN if counts.get("dead_lettered", 0) else OK)
    return Card(
        "الإشعارات",
        f"{sent} من {total}",
        f"سُلّمت آخر 24 ساعة · بانتظار {waiting} · رسائل فاشلة غير محلولة {dead}",
        level,
        _link("admin:notifications_deadlettermessage_changelist", "?resolved__exact=0"),
    )


#: خطأٌ واحدٌ يستحقّ النظر (أصفر)، وعشرةٌ في 24 ساعةً انفجارٌ (أحمر).
SERVER_ERRORS_WARN = 1
SERVER_ERRORS_BAD = 10


def _ago(seconds: float) -> str:
    minutes = max(int(seconds // 60), 0)
    if minutes < 120:
        return f"{minutes} دقيقة"
    if minutes < 48 * 60:
        return f"{minutes // 60} ساعة"
    return f"{minutes // (24 * 60)} يوماً"


def server_errors(now: float | None = None) -> Card:
    """أخطاءُ الخادم (5xx) في آخر 24 ساعة من عدّادٍ ذاتيٍّ لا من Sentry — راجع `core/error_counter.py`."""
    import time

    from core import error_counter

    moment = time.time() if now is None else now
    recent, earlier = error_counter.counts(moment)
    last = error_counter.last_error()
    parts = [f"استجابةُ 5xx آخر 24 ساعة ({_trend(recent, earlier)})"]
    if last:
        what = last.get("exc") or "استجابةٌ بلا استثناء"
        parts.append(f"آخرُها {last.get('route', '')} · {what} قبل {_ago(moment - last['at'])}")
    parts.append("Sentry مضبوط" if getattr(settings, "SENTRY_DSN", "") else "Sentry غير مضبوط هنا")
    url = getattr(settings, "SENTRY_ISSUES_URL", "")
    level = BAD if recent >= SERVER_ERRORS_BAD else (WARN if recent >= SERVER_ERRORS_WARN else OK)
    return Card(
        "أخطاء الخادم",
        str(recent),
        " · ".join(parts),
        level,
        url if url.startswith("https://") else "",
    )


def developer_messages() -> Card:
    from developer_feedback.models import DeveloperMessage, MessageStatus

    open_states = (MessageStatus.NEW, MessageStatus.SEEN, MessageStatus.IN_PROGRESS)
    new = DeveloperMessage.objects.filter(status=MessageStatus.NEW).count()
    unfinished = DeveloperMessage.objects.filter(status__in=open_states).count()
    return Card(
        "ملاحظات المطوّر",
        str(new),
        f"جديدةٌ لم تُقرأ · غير منتهيةٍ في المجموع {unfinished}",
        WARN if new else OK,
        _link("admin:developer_feedback_developermessage_changelist", "?status__exact=new"),
    )


def roadmap_status() -> Card:
    from roadmap.models import ItemStatus, RoadmapItem, RoadmapRisk

    today = timezone.localdate()
    items = RoadmapItem.objects.all()
    overdue = items.filter(end_date__lt=today).exclude(status=ItemStatus.DONE).count()
    blocked = items.filter(status=ItemStatus.BLOCKED).count()
    done, total = items.filter(status=ItemStatus.DONE).count(), items.count()
    return Card(
        "خارطة التجويد",
        f"{overdue} متأخّر",
        f"محجوب {blocked} · مُغلَق {done} من {total} · مخاطر {RoadmapRisk.objects.count()}",
        WARN if overdue or blocked else OK,
        "/roadmap/",
    )


def pending_migrations() -> Card:
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    if pending:
        return Card("الهجرات", f"{pending} معلّقة", "هجراتٌ لم تُطبَّق على هذه القاعدة", BAD)
    return Card("الهجرات", "مطبَّقة", "لا هجراتٍ معلّقة", OK)


def sensitive_actions(now=None) -> Card:
    from core.models import AuditLog

    now = now or timezone.now()
    midnight = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    base = AuditLog.objects.filter(timestamp__gte=midnight)
    deletes = base.filter(action="delete").count()
    exports = base.filter(action="export").count()
    return Card(
        "إجراءات حسّاسة اليوم",
        str(deletes + exports),
        f"حذف {deletes} · تصدير {exports}",
        WARN if deletes else OK,
        _link("admin:core_auditlog_changelist", "?action__exact=delete"),
    )


BUILDERS: tuple[Callable[[], Card], ...] = (
    platform_health,
    worker,
    security,
    notifications,
    server_errors,
    sensitive_actions,
    pending_migrations,
    developer_messages,
    roadmap_status,
)

_SEVERITY = {BAD: 0, WARN: 1, OK: 2}


def build_cards() -> list[Card]:
    cards = []
    for build in BUILDERS:
        try:
            cards.append(build())
        except Exception:  # noqa: BLE001 — تعطُّل بطاقةٍ لا يُسقط الصفحة الرئيسيّة للإدارة
            logger.exception("admin monitor card failed: %s", build.__name__)
    return sorted(
        cards, key=lambda c: _SEVERITY[c.level]
    )  # الأخطرُ أوّلاً، والترتيبُ الأصليّ يثبت بين المتساوين
