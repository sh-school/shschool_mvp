"""تنبيهاتُ مُهَل خرق البيانات: إشعارُ NCSA، وإخطارُ الأفراد (م.14)، واستكمالُ الإشعار المبدئي.

انتقل إلى هنا من `notifications/tasks.py` (W-20261010-014) لأنّ الملفَّ تجاوز سقفَ الحجم؛ والمهمّةُ
الساعيّةُ `notifications.check_breach_deadlines` ما زالت في `tasks.py` وتستدعي هذه الوحدة.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from core.models import BreachReport, CustomUser

logger = logging.getLogger(__name__)

#: عتباتُ تنبيه مُهَل الخرق بالساعات — مصدرٌ واحدٌ لا أرقامَ حرفيّةً في المنطق (W-20261010-014).
#: `pre_hours`: يبدأ التنبيهُ المبكّر قبل الموعد بهذه المدّة؛ وبعد الموعد: عند الموعد ثم يوماً بيوم.
#: هذه سياسةٌ تشغيليّة لا نصٌّ قانونيّ: م.14 بلا مدّةٍ لإخطار الأفراد، و72 ساعةً حدُّ إرشاد NCSA.
BREACH_ALERT_THRESHOLDS = {
    "ncsa": {"pre_hours": 12},
    "individuals": {"pre_hours": 24},
    "completion": {"pre_hours": 24},
}
#: المدّةُ بين تنبيهَين بعد فوات الموعد.
BREACH_ALERT_REPEAT_HOURS = 24


def _breach_open_stage_deadlines(breach: "BreachReport") -> list[tuple[str, Any]]:
    """المراحلُ المفتوحةُ للخرق وموعدُ كلٍّ منها: (المرحلة، الموعد). تتوقّف المرحلةُ بإنجازها أو بالإغلاق.

    ncsa         لم يُرسَل إشعارٌ أصلاً (موعدُه `ncsa_deadline` من الاكتشاف لا يتحرّك).
    individuals  الإخطارُ واجبٌ ولم يتمّ (غيرُ لازمٍ أو مُنجَزٌ أو لم يُقيَّم ← لا تنبيه).
    completion   إشعارٌ مبدئيٌّ ناقصٌ لم يُستكمل (موعدُه يحدّده المُرسِل).
    """
    if breach.status == "resolved":
        return []
    stages: list[tuple[str, Any]] = []
    if (
        breach.ncsa_deadline
        and breach.ncsa_notified_at is None
        and breach.ncsa_notice_stage == "none"
        and breach.status in ("discovered", "assessing")
    ):
        stages.append(("ncsa", breach.ncsa_deadline))
    if breach.individuals_status == "required" and breach.individuals_deadline:
        stages.append(("individuals", breach.individuals_deadline))
    if breach.ncsa_notice_stage == "initial" and breach.ncsa_completion_due_at:
        stages.append(("completion", breach.ncsa_completion_due_at))
    return stages


def breach_alert_events(breach: "BreachReport", now) -> list[dict[str, Any]]:
    """تنبيهاتُ هذه اللحظة للخرق: صفرٌ أو أكثر، واحدٌ لكلّ مرحلةٍ مفتوحةٍ بلغت عتبتَها.

    العتبةُ مفتاحٌ يُكتب في الإشعار فلا تتكرّر: `pre` (داخل نافذة ما قبل الموعد)، `due` (أوّلُ 24 ساعةً
    بعد الموعد)، ثمّ `day_N` يوماً بيوم. دالةٌ نقيّةٌ لا تكتب شيئاً ولا تغيّر الخرق.
    """
    from datetime import timedelta

    events = []
    for stage, deadline in _breach_open_stage_deadlines(breach):
        pre_hours = BREACH_ALERT_THRESHOLDS[stage]["pre_hours"]
        remaining = deadline - now
        if remaining > timedelta(hours=pre_hours):
            continue
        if remaining > timedelta(0):
            threshold, overdue, days_late = "pre", False, 0
        else:
            days_late = int((-remaining) / timedelta(hours=BREACH_ALERT_REPEAT_HOURS))
            threshold, overdue = ("due" if days_late == 0 else f"day_{days_late}"), True
        events.append(
            {
                "stage": stage,
                "threshold": threshold,
                "overdue": overdue,
                "hours_left": max(0, int(remaining.total_seconds() / 3600)),
                "days_late": days_late,
            }
        )
    return events


#: لا يُكرَّر تنبيهُ المنصّة لنفس المستلم والبلاغ قبل انقضاء هذه المدّة — والمهمّةُ ساعيّة.
BREACH_INAPP_REPEAT_HOURS = 12


def _breach_dpo_ids(breach: "BreachReport") -> set:
    """مسؤولُ حماية البيانات: `DPO_EMAIL` إن ضُبط، ودورُ مطوّر المنصّة في هذه المدرسة (هو من يمارس الدور اليوم)."""
    from django.conf import settings

    from core.models import CustomUser
    from core.models.access import TIER_SYSTEM, Membership

    ids = set(
        Membership.objects.filter(
            school=breach.school, is_active=True, role__name__in=TIER_SYSTEM
        ).values_list("user_id", flat=True)
    )
    dpo_email = getattr(settings, "DPO_EMAIL", "")
    if dpo_email:
        ids.update(CustomUser.objects.filter(email__iexact=dpo_email).values_list("pk", flat=True))
    return ids


def _breach_leadership_ids(breach: "BreachReport") -> set:
    from core.models.access import TIER_1_LEADERSHIP, Membership

    return set(
        Membership.objects.filter(
            school=breach.school, is_active=True, role__name__in=TIER_1_LEADERSHIP
        ).values_list("user_id", flat=True)
    )


def _breach_inapp_recipients(breach: "BreachReport") -> "QuerySet[CustomUser]":
    """من يصله تنبيهُ مهلة NCSA: المكلَّف والمُبلِّغ والمدير ومسؤولُ حماية البيانات.

    فلا يعتمد الوصولُ على مزوّد بريدٍ لم يُشترَ بعد.
    """
    from core.models import CustomUser

    ids = _breach_leadership_ids(breach) | _breach_dpo_ids(breach)
    if breach.assigned_to_id:
        ids.add(breach.assigned_to_id)
    if breach.reported_by_id:
        ids.add(breach.reported_by_id)
    return CustomUser.objects.filter(pk__in=ids, is_active=True)


def _breach_stage_recipients(breach: "BreachReport", overdue: bool) -> "QuerySet[CustomUser]":
    """مستلمو تنبيه إخطار الأفراد واستكمال الإشعار: المكلَّف وDPO، ويلحق المديرُ عند الفوات.

    المُبلِّغ لا يُنبَّه. وإن لم يوجد مكلَّفٌ ولا DPO نُبِّه المديرُ ولو قبل الفوات فلا يضيع التنبيه.
    """
    from core.models import CustomUser

    ids = _breach_dpo_ids(breach)
    if breach.assigned_to_id:
        ids.add(breach.assigned_to_id)
    if overdue or not ids:
        ids |= _breach_leadership_ids(breach)
    return CustomUser.objects.filter(pk__in=ids, is_active=True)


#: عنوانُ التنبيه لكلّ مرحلة: (قبل الموعد بـ{h} ساعة، بعد فواته).
_BREACH_STAGE_TITLES = {
    "ncsa": (
        "⚠️ بقي {h} ساعة على مهلة إشعار الجهة المختصّة عن خرق بيانات",
        "🚨 تجاوزتَ مهلةَ إشعار الجهة المختصّة عن خرق بيانات",
    ),
    "individuals": (
        "⚠️ بقي {h} ساعة على مهلة إخطار الأفراد المتأثّرين بخرق بيانات (م.14)",
        "🚨 تجاوزتَ مهلةَ إخطار الأفراد المتأثّرين بخرق بيانات (م.14)",
    ),
    "completion": (
        "⚠️ بقي {h} ساعة على موعد استكمال إشعار الجهة المختصّة عن خرق بيانات",
        "🚨 فات موعدُ استكمال إشعار الجهة المختصّة عن خرق بيانات",
    ),
}


def notify_breach_in_app(
    breach: "BreachReport",
    hours_left: float | None,
    overdue: bool = False,
    *,
    stage: str = "ncsa",
    threshold: str | None = None,
    days_late: int = 0,
) -> int:
    """تنبيهُ الخرق داخل المنصّة (الجرس) — لا يعتمد على مزوّد بريد.

    الإنذارُ كان بالبريد وحدَه، و`DPO_EMAIL` ومزوّدُ البريد غيرُ مضبوطَين في الإنتاج
    (DPIA R8)، فكان مؤقّتُ الـ72 ساعة يعمل ولا يصل أحداً. والنصُّ هنا بلا بياناتٍ
    شخصيّة ولا عنوانِ البلاغ: رقمٌ ومهلةٌ ورابط.

    مع `threshold` يُكتب مفتاحُ (خرق، مرحلة، عتبة) في `related_object_id`، فلا يتكرّر التنبيه لنفس
    المستلم ولو أُعيد تشغيلُ المهمّة؛ وبدونه نافذةُ منعٍ زمنيّةٌ (`BREACH_INAPP_REPEAT_HOURS`).
    """
    from datetime import timedelta

    from django.utils import timezone

    from notifications.models import InAppNotification

    before, after = _BREACH_STAGE_TITLES[stage]
    title = after if overdue else before.format(h=hours_left)
    body = f"الخطورة: {breach.get_severity_display()} — "
    if stage != "ncsa":
        body += f"عدد المتأثّرين: {breach.affected_count} — "
    if overdue and days_late:
        body += f"متأخّر منذ {days_late} يوم — "
    body += "افتح البلاغ لاتّخاذ الإجراء."

    if threshold is not None:
        key = f"{breach.pk}:{stage}:{threshold}"
        recipients = (
            _breach_inapp_recipients(breach)
            if stage == "ncsa"
            else _breach_stage_recipients(breach, overdue)
        )
        notified = set(
            InAppNotification.objects.filter(
                school=breach.school, related_object_id=key
            ).values_list("user_id", flat=True)
        )
    else:
        key = str(breach.pk)
        recipients = _breach_inapp_recipients(breach)
        since = timezone.now() - timedelta(hours=BREACH_INAPP_REPEAT_HOURS)
        notified = set(
            InAppNotification.objects.filter(
                school=breach.school, related_object_id=key, created_at__gte=since
            ).values_list("user_id", flat=True)
        )

    created = 0
    for user in recipients:
        if user.pk in notified:
            continue
        InAppNotification.objects.create(
            user=user,
            school=breach.school,
            title=title,
            body=body,
            event_type="general",
            priority="urgent",
            related_object_id=key,
            related_url=f"/breach/{breach.pk}/",
        )
        created += 1
    return created


def send_breach_alert(
    breach, hours_left, overdue=False, *, stage="ncsa", threshold=None, days_late=0
):
    """تنبيه الخرق: داخل المنصّة أوّلاً (لا يحتاج مزوّداً)، ثمّ بالبريد لمهلة NCSA وحدَها.

    إخطارُ الأفراد واستكمالُ الإشعار داخل المنصّة فقط: نصُّ البريد القائم خاصٌّ بإشعار NCSA.
    """
    from django.conf import settings
    from django.core.mail import send_mail

    try:
        notify_breach_in_app(
            breach,
            hours_left,
            overdue=overdue,
            stage=stage,
            threshold=threshold,
            days_late=days_late,
        )
    except Exception:  # noqa: BLE001 — الإنذارُ لا يسقط ببابٍ منه فيُحجب الآخر
        logger.error("breach in-app alert failed", exc_info=True)

    if stage != "ncsa":
        return

    subject = (
        f"🚨 [عاجل] تجاوز مهلة إشعار NCSA — {breach.title}"
        if overdue
        else f"⚠️ تنبيه: {hours_left} ساعة لإشعار NCSA — {breach.title}"
    )

    body = f"""
تقرير خرق البيانات: {breach.title}
المدرسة: {breach.school.name}
الخطورة: {breach.get_severity_display()}
البيانات المتأثرة: {breach.get_data_type_affected_display()}
عدد الأشخاص: {breach.affected_count}
وقت الاكتشاف: {breach.discovered_at}
موعد NCSA: {breach.ncsa_deadline}
الحالة: {"⛔ تجاوز المهلة" if overdue else f"⚠️ {hours_left} ساعة متبقية"}

الإجراء الفوري: {breach.immediate_action or "—"}

رابط المراجعة: /breach/{breach.pk}/

PDPPL م.11 — يجب إشعار NCSA خلال 72 ساعة من الاكتشاف.
    """.strip()

    # جمع المستلمين: المسؤول (DPO) + المُبلِّغ
    recipients = []
    # مسؤولُ حماية البيانات من الإعدادات (البيئة) — وإن لم يُضبط بقي المُبلِّغُ والمكلَّف.
    dpo_email = getattr(settings, "DPO_EMAIL", "")
    if dpo_email:
        recipients.append(dpo_email)
    if breach.assigned_to and breach.assigned_to.email:
        recipients.append(breach.assigned_to.email)
    if breach.reported_by and breach.reported_by.email:
        recipients.append(breach.reported_by.email)

    if recipients:
        try:
            delivered = send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=list(set(recipients)),
                fail_silently=True,
            )
            if not delivered:
                logger.error("تنبيه الخرق لم يُسلَّم بالبريد — مهلة NCSA قائمة، تابِعه يدوياً")
        except (OSError, RuntimeError, ValueError) as e:
            logger.error("breach alert email failed error=%s", type(e).__name__, exc_info=True)
