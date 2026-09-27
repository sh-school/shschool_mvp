"""لوحةُ «الإشعارات والرسائل» — سلامةُ التسليم بأعدادٍ لا أسماء (قرارُ المالك 2026-09-27).

كانت بطاقتُها في رئيسيّة الإدارة وأُخرجت من «صحّة الإنتاج» لأنّ جدولَيها بسياسة RLS لكلّ مدرسة؛ والمجمِّعُ يعمل في عاملٍ مربوطٍ بمدرسته فيقرؤها.
- **أحمرُ**: رسالةٌ فاشلةٌ غيرُ محلولةٍ في `DeadLetterMessage` (استنفدت محاولاتِها) — كالبطاقة القائمة.
- **«انتبه»**: استنفادُ محاولاتٍ في آخر 24 ساعة، أو تسليمٌ عالقٌ (لم يُسلَّم بعد ساعةٍ من إنشائه)، أو «نتيجةٌ غيرُ معروفة».
- **ليس فشلاً**: `undeliverable` (لا وجهةَ صالحةٌ للمستلم على القناة — النظامُ سليم، DBT-11): يُعرض رقماً ولا يُنذر.
ما يُخزَّن أعدادٌ فقط — لا مستلمَ ولا نصَّ رسالة ولا وجهة.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from command_center import contract
from command_center.collectors.publish import publish, score, worst

PANEL = "messaging"
WINDOW = timedelta(hours=24)
STUCK_AFTER = timedelta(hours=1)
WAITING = ("pending", "retry_wait", "in_progress")


def level(dead_unresolved: int, exhausted: int, stuck: int, unknown: int) -> str:
    if dead_unresolved:
        return contract.BAD
    return contract.WARN if (exhausted or stuck or unknown) else contract.OK


def collect(now=None) -> None:
    from notifications.models import DeadLetterMessage, NotificationDelivery

    moment = now or timezone.now()
    recent = dict(
        NotificationDelivery.objects.filter(created_at__gte=moment - WINDOW)
        .values_list("status")
        .annotate(n=Count("pk"))
    )
    stuck = NotificationDelivery.objects.filter(
        status__in=WAITING, created_at__lt=moment - STUCK_AFTER
    ).count()
    dead = DeadLetterMessage.objects.filter(resolved=False).count()
    sent = recent.get("sent", 0)
    total = sum(recent.values())
    exhausted = recent.get("dead_lettered", 0)
    unknown = recent.get("unknown_outcome", 0)
    undeliverable = recent.get("undeliverable", 0)
    waiting = sum(recent.get(status, 0) for status in WAITING)
    overall = level(dead, exhausted, stuck, unknown)
    if dead:
        headline = f"{dead} رسالةً فاشلةً غيرَ محلولة"
    elif overall != contract.OK:
        headline = "تسليمٌ بحاجةٍ إلى نظر"
    else:
        headline = "التسليمُ سليم" if total else "لا إشعاراتٍ في آخر 24 ساعة"
    publish(
        PANEL,
        status=worst([overall]),
        headline=headline,
        gauge=score([overall]),
        metrics=(
            ("سُلّمت / 24س", f"{sent} من {total}"),
            ("بانتظار", f"{waiting} ({stuck} عالقة)" if stuck else waiting),
            ("فاشلةٌ غيرُ محلولة", dead),
            ("بلا وجهةٍ صالحة", undeliverable),
        ),
    )
