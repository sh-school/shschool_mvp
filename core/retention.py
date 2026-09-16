"""الاحتفاظُ بالبيانات — ما يُحذف بعد مدّته، وما يُحفظ بحكم القانون.

قانونُ حماية البيانات الشخصيّة القطريّ (13/2016) يُلزم بألّا تُحفظ البياناتُ
أطولَ ممّا يقتضيه غرضُها (المادّتان 7 و10). وكان `PDPPL_DATA_RETENTION_DAYS`
معلَناً في `.railway/railway.ts` ولا يقرؤه أحد — وعداً بلا مُنفِّذ.

السياسةُ المكتوبةُ في `docs/privacy/data_retention.md` هي المرجع: كلُّ جدولٍ
فيها بقرارٍ وسبب. وهذا الملفُّ يُنفِّذ شطرَ «يُحذف» منها وحدَه؛ أمّا شطرُ «يُحفظ»
فحارسُه `tests/test_data_retention.py`: لا جدولَ يُلمَس إلّا ما هنا، ولا جدولَ
بلا حكمٍ في الوثيقة.

أصنافُ الحذف اثنان:

* **ينتهي بذاته** — جلسةٌ منتهية ورمزُ JWT منقضٍ: عمرُه في داخله، ولا يخدم
  شيئاً بعد انقضائه، فيُحذف عند الانقضاء لا بعد N يوماً.
* **يُحذف بعد N يوماً** — أثرُ تشغيلٍ حمل بياناتٍ شخصيّة (عنوانَ IP، بريداً،
  نصَّ رسالة) وانقضى غرضُه: محاولاتُ الدخول، وسجلّاتُ التسليم، وإشعاراتُ الجرس.

**والصفرُ يعطّل**: `PDPPL_DATA_RETENTION_DAYS=0` فلا يُحذف شيء — لا افتراضٌ
خفيّ. والحذفُ دفعاتٌ (ألفُ صفٍّ في الجملة) كي لا يُقفَل جدولٌ حيٌّ دقائق،
وثابتُ التكرار: تشغيلٌ ثانٍ على قاعدةٍ نُفِّذت عليها السياسةُ لا يحذف شيئاً.

ولا يُحذف سجلُّ التدقيق قطّ — بل يُكتب فيه ملخّصُ كلّ تنفيذٍ بالأعداد لا الأسماء
(`AuditLog(action="delete")`)، فحذفُ البيانات نفسُه واقعةٌ تُدقَّق.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.db.models.deletion import ProtectedError
from django.utils import timezone

logger = logging.getLogger(__name__)

#: كم صفّاً يُحذف في الجملة الواحدة — صغيرٌ بما يكفي ألّا يُقفَل جدولٌ حيٌّ طويلاً.
BATCH_SIZE = 1000

Candidates = Callable[[datetime, datetime], "QuerySet[Any]"]


@dataclass(frozen=True)
class Rule:
    """قاعدةُ حذفٍ واحدة: مفتاحٌ للتقرير، وجدولٌ للوثيقة، ومرشِّحٌ للصفوف.

    `expires_on_its_own` يقول إنّ الصفَّ يحمل أجلَه في داخله فلا يُنتظر به N.
    """

    key: str
    table: str
    label: str
    candidates: Candidates
    expires_on_its_own: bool = False


# ── ينتهي بذاته ────────────────────────────────────────────────────────


def _expired_sessions(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from django.contrib.sessions.models import Session

    return Session.objects.filter(expire_date__lt=now)


def _expired_jwt_tokens(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    """الرموزُ المنقضية — والمحظورةُ منها تتبعها بالتسلسل (`CASCADE`)."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    return OutstandingToken.objects.filter(expires_at__lt=now)


# ── محاولاتُ الدخول (django-axes) ───────────────────────────────────────


def _axes_attempts(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from axes.models import AccessAttempt

    qs: QuerySet[Any] = AccessAttempt.objects.filter(attempt_time__lt=cutoff)
    return qs


def _axes_access_log(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from axes.models import AccessLog

    qs: QuerySet[Any] = AccessLog.objects.filter(attempt_time__lt=cutoff)
    return qs


def _axes_failure_log(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from axes.models import AccessFailureLog

    qs: QuerySet[Any] = AccessFailureLog.objects.filter(attempt_time__lt=cutoff)
    return qs


# ── الإشعارات — بترتيب الحماية: الابنُ قبل أبيه ─────────────────────────
#
# `NotificationLog` و`DeadLetterMessage` يحميان تسليمَهما (`PROTECT`)،
# والتسليمُ والنيّةُ يتبعان واقعتَهما (`CASCADE`). فيُحذف السجلُّ والرسالةُ
# الفاشلةُ أوّلاً، ثمّ ما لم يبقَ له ابنٌ من التسليمات، ثمّ الواقعةُ التي لم
# يبقَ لها شيء. وما ما زال حيّاً — تسليمٌ غيرُ نهائيّ، أو سجلٌّ أحدثُ من
# المدّة — يُبقي أباه معه.


def _notification_logs(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from notifications.models import NotificationLog

    return NotificationLog.objects.filter(sent_at__lt=cutoff)


def _resolved_dead_letters(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    """المحلولةُ وحدَها: غيرُ المحلولة طابورُ مشغّلٍ لم يُقرأ، لا أثرٌ انقضى."""
    from notifications.models import DeadLetterMessage

    return DeadLetterMessage.objects.filter(resolved=True, created_at__lt=cutoff)


def _finished_enqueue_intents(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    """نيّةٌ لم يبقَ لمستلمها تسليمٌ مفتوح — سواءٌ مُسح نصُّها أم لا."""
    from notifications.delivery_state import TERMINAL
    from notifications.models import NotificationDelivery, NotificationEnqueueIntent

    open_delivery = NotificationDelivery.objects.filter(
        dispatch_id=OuterRef("dispatch_id"),
        recipient_id=OuterRef("recipient_id"),
    ).exclude(status__in=TERMINAL)
    return NotificationEnqueueIntent.objects.filter(created_at__lt=cutoff).filter(
        ~Exists(open_delivery)
    )


def _terminal_deliveries(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from notifications.delivery_state import TERMINAL
    from notifications.models import DeadLetterMessage, NotificationDelivery, NotificationLog

    attempts = NotificationLog.objects.filter(delivery_id=OuterRef("pk"))
    dead_letter = DeadLetterMessage.objects.filter(delivery_id=OuterRef("pk"))
    return (
        NotificationDelivery.objects.filter(created_at__lt=cutoff, status__in=TERMINAL)
        .filter(~Exists(attempts))
        .filter(~Exists(dead_letter))
    )


def _childless_dispatches(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from notifications.models import (
        NotificationDelivery,
        NotificationDispatch,
        NotificationEnqueueIntent,
    )

    deliveries = NotificationDelivery.objects.filter(dispatch_id=OuterRef("pk"))
    intents = NotificationEnqueueIntent.objects.filter(dispatch_id=OuterRef("pk"))
    return (
        NotificationDispatch.objects.filter(created_at__lt=cutoff)
        .filter(~Exists(deliveries))
        .filter(~Exists(intents))
    )


def _in_app_notifications(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    from notifications.models import InAppNotification

    return InAppNotification.objects.filter(created_at__lt=cutoff)


def _dead_push_subscriptions(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    """اشتراكٌ مطفأٌ لم يُستعمل منذ المدّة — ونقطةُ نهايته ومفاتيحُه بياناتٌ شخصيّة."""
    from notifications.models import PushSubscription

    return PushSubscription.objects.filter(is_active=False).filter(
        Q(last_used__lt=cutoff) | Q(last_used__isnull=True, created_at__lt=cutoff)
    )


# ── السلوك ────────────────────────────────────────────────────────────


def _auto_infraction_notices(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    """علامةُ «أُبلغت الأسرة» — لا يُرجع إليها إلّا مسحُ الأيّام الخمسة الأخيرة."""
    from behavior.models import AutoInfractionNotice

    qs: QuerySet[Any] = AutoInfractionNotice.objects.filter(sent_at__lt=cutoff)
    return qs


# ── الاستيراد ─────────────────────────────────────────────────────────


def _import_logs(now: datetime, cutoff: datetime) -> QuerySet[Any]:
    """`error_log` يحمل الصفوفَ المرفوضةَ كما وردت — أسماءً وأرقاماً."""
    from staging.models import ImportLog

    return ImportLog.objects.filter(started_at__lt=cutoff)


#: القواعدُ بترتيب تنفيذها — والترتيبُ جزءٌ من الصواب (انظر الإشعارات أعلاه).
RULES: tuple[Rule, ...] = (
    Rule("sessions.expired", "django_session", "جلساتٌ منتهية", _expired_sessions, True),
    Rule(
        "jwt.expired",
        "token_blacklist_outstandingtoken",
        "رموزُ JWT منقضية",
        _expired_jwt_tokens,
        True,
    ),
    Rule("axes.attempts", "axes_accessattempt", "محاولاتُ دخولٍ (axes)", _axes_attempts),
    Rule("axes.access_log", "axes_accesslog", "سجلُّ الدخول (axes)", _axes_access_log),
    Rule("axes.failure_log", "axes_accessfailurelog", "سجلُّ الفشل (axes)", _axes_failure_log),
    Rule(
        "notifications.logs",
        "notifications_notificationlog",
        "سجلّاتُ محاولات التسليم",
        _notification_logs,
    ),
    Rule(
        "notifications.dead_letters",
        "notifications_deadlettermessage",
        "رسائلُ فاشلةٌ محلولة",
        _resolved_dead_letters,
    ),
    Rule(
        "notifications.intents",
        "notifications_notificationenqueueintent",
        "نوايا طبرٍ منتهية",
        _finished_enqueue_intents,
    ),
    Rule(
        "notifications.deliveries",
        "notifications_notificationdelivery",
        "تسليماتٌ نهائيّةٌ بلا أثرٍ باقٍ",
        _terminal_deliveries,
    ),
    Rule(
        "notifications.dispatches",
        "notifications_notificationdispatch",
        "وقائعُ إشعارٍ بلا تسليمات",
        _childless_dispatches,
    ),
    Rule(
        "notifications.in_app",
        "notifications_inappnotification",
        "إشعاراتُ الجرس",
        _in_app_notifications,
    ),
    Rule(
        "notifications.push_subscriptions",
        "notifications_pushsubscription",
        "اشتراكاتُ Push ميّتة",
        _dead_push_subscriptions,
    ),
    Rule(
        "behavior.auto_notices",
        "behavior_autoinfractionnotice",
        "علاماتُ إبلاغ الأسرة بمخالفات الرصد",
        _auto_infraction_notices,
    ),
    Rule("staging.import_logs", "staging_importlog", "سجلّاتُ الاستيراد", _import_logs),
)


def retention_days() -> int:
    """المدّةُ من الإعدادات — والصفرُ (أو ما دونه) تعطيل."""
    raw = getattr(settings, "PDPPL_DATA_RETENTION_DAYS", 0)
    try:
        days = int(raw or 0)
    except (TypeError, ValueError):
        return 0
    return max(days, 0)


@dataclass
class Report:
    """ما فعله تنفيذٌ واحد — أعدادٌ لا أسماء."""

    enabled: bool
    dry_run: bool
    retention_days: int
    cutoff: datetime | None
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def as_changes(self) -> dict[str, Any]:
        return {
            "event": "data_retention_enforced",
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "retention_days": self.retention_days,
            "cutoff": self.cutoff.isoformat() if self.cutoff else None,
            "deleted": dict(self.counts),
            "total": self.total,
        }


def _delete_in_batches(qs: QuerySet[Any], batch_size: int) -> int:
    """يحذف المرشَّحين دفعةً دفعة، ويُعيد عددَ صفوف **هذا** الجدول وحدَه.

    ما يتبع بالتسلسل (`CASCADE`) لا يُعدّ هنا كي لا يُنسب حذفُ ابنٍ إلى قاعدةِ
    أبيه. وصفٌّ يحميه ابنٌ ظهر بين الاختيار والحذف يُتخطّى لا يُسقط التنفيذ.
    """
    model = qs.model
    label = model._meta.label
    deleted = 0
    skipped: set[Any] = set()
    while True:
        pks = list(qs.exclude(pk__in=skipped).order_by().values_list("pk", flat=True)[:batch_size])
        if not pks:
            return deleted
        try:
            _, per_model = model._default_manager.filter(pk__in=pks).delete()
            deleted += per_model.get(label, 0)
        except ProtectedError:
            for pk in pks:
                try:
                    _, per_model = model._default_manager.filter(pk=pk).delete()
                    deleted += per_model.get(label, 0)
                except ProtectedError:
                    skipped.add(pk)


def enforce_retention(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    batch_size: int = BATCH_SIZE,
) -> Report:
    """يُنفِّذ السياسة (أو يعرضها بـ`dry_run`) ويكتب ملخّصَها في سجلّ التدقيق.

    `now` يُمرَّر في الاختبارات لتثبيت الزمن؛ والافتراضُ لحظةُ التنفيذ.
    """
    days = retention_days()
    now = now or timezone.now()
    if days <= 0:
        logger.info("data_retention: معطَّلٌ (PDPPL_DATA_RETENTION_DAYS=0) — لا حذف")
        return Report(enabled=False, dry_run=dry_run, retention_days=0, cutoff=None)

    cutoff = now - timedelta(days=days)
    report = Report(enabled=True, dry_run=dry_run, retention_days=days, cutoff=cutoff)

    for rule in RULES:
        candidates = rule.candidates(now, cutoff)
        if dry_run:
            report.counts[rule.key] = candidates.count()
        else:
            report.counts[rule.key] = _delete_in_batches(candidates, batch_size)

    if dry_run:
        logger.info("data_retention (عرض): %d مرشَّحاً بعد %d يوماً", report.total, days)
        return report

    _record(report)
    logger.info("data_retention: حُذف %d صفّاً بعد %d يوماً", report.total, days)
    return report


def _record(report: Report) -> None:
    """سطرٌ في التدقيق لكلّ تنفيذٍ فعليّ — ولو صفراً، فالتنفيذُ نفسُه واقعة."""
    from core.models.audit import AuditLog

    AuditLog.objects.create(
        user=None,
        school=None,
        action="delete",
        model_name="other",
        object_id="",
        object_repr=(
            f"إنفاذُ الاحتفاظ بالبيانات — {report.total} صفّاً بعد {report.retention_days} يوماً"
        )[:300],
        changes=report.as_changes(),
    )
