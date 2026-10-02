"""كتابةُ رسالة المطوّر الصادرة وتسليمُها — سجلٌّ واحدٌ + إشعارٌ لكلّ مستلِم.

التسليمُ عبر `notifications.InAppNotification` القائم (الجرسُ وصندوقُ الإشعارات
اللذان يملكهما كلُّ مستخدمٍ أصلاً) — لا صندوقَ واردٍ موازياً (تصحيحُ تصميمٍ
2026-09-30).
"""

from __future__ import annotations

from django.db import transaction

from developer_feedback.services.audience import (
    AudienceError,
    audience_label,
    resolve_recipients,
)
from notifications.models import InAppNotification


def preview_recipient_count(school, sender, target_kind: str, target_value: str) -> int:
    """عددُ المستلِمين قبل الإرسال — صفرٌ لهدفٍ غيرِ صالح."""
    try:
        return resolve_recipients(school, sender, target_kind, target_value).count()
    except AudienceError:
        return 0


def send_broadcast(school, sender, form, target_kind: str, target_value: str) -> int:
    """يحفظ السجلَّ ويُنشئ إشعاراً لكلّ مستلِم، ويُعيد عددَهم.

    يرفع `AudienceError` إن كان الهدفُ غيرَ صالحٍ أو بلا مستلِمين — فلا يُحفظ شيء.
    `form` نموذجُ نصّ الرسالة وقد اجتاز `is_valid()`.
    """
    recipient_ids = list(
        resolve_recipients(school, sender, target_kind, target_value).values_list("id", flat=True)
    )
    if not recipient_ids:
        raise AudienceError("لا يوجد مستلِمون مطابقون لهذا الاختيار.")

    with transaction.atomic():
        outbound = form.save(commit=False)
        outbound.sent_by = sender
        outbound.audience_label = audience_label(target_kind, target_value, len(recipient_ids))
        outbound.recipient_count = len(recipient_ids)
        outbound.save()
        InAppNotification.objects.bulk_create(
            [
                InAppNotification(
                    user_id=uid,
                    school=school,
                    title=outbound.subject,
                    body=outbound.body,
                    event_type="developer_message",
                    priority="medium",
                )
                for uid in recipient_ids
            ]
        )
    return len(recipient_ids)
