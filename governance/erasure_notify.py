"""إشعارُ موقّعي طلب المحو داخل المنصّة (U-11) — بلا اسم الطالب ولا سبب الطلب في نصّه."""

import logging

from django.db import transaction
from django.urls import reverse

from core.models import ErasureRequest
from notifications.models import InAppNotification

logger = logging.getLogger("core")

TITLE = "طلب محو بيانات ينتظر توقيعك"
BODY = "يوجد طلب محو بيانات طالب ينتظر توقيعك أو رفضك. افتح طلبات المحو للمراجعة."


def notify_awaiting_signers(erasure_request: ErasureRequest) -> None:
    """إشعارٌ لمن بقي توقيعُه. تعذّرُه لا يُسقط الطلبَ ولا التوقيعَ المسجَّل."""
    from governance.erasure_service import awaiting_signers

    try:
        with transaction.atomic():
            for user in awaiting_signers(erasure_request):
                InAppNotification.objects.create(
                    user=user,
                    school=erasure_request.school,
                    title=TITLE,
                    body=BODY,
                    event_type="general",
                    priority="urgent",
                    related_object_id=str(erasure_request.pk),
                    related_url=reverse("governance:erasure_requests"),
                )
    except Exception:
        logger.exception("تعذّر إشعارُ موقّعي طلب المحو %s", erasure_request.pk)
