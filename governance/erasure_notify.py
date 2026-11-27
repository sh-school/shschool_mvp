"""إشعارُ موقّعي طلب المحو داخلَ المنصّة (U-11 المرحلة 2 ب).

داخلَ المنصّة وحدَها (لا بريدَ ولا رسائل)، ونصٌّ ثابتٌ بلا اسم طالبٍ ولا سببِ الطلب.
"""

import logging
from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.urls import reverse

from notifications.models import InAppNotification

logger = logging.getLogger("core")

TITLE = "طلبُ محو بيانات طالبٍ ينتظر توقيعك"
BODY = "راجع الطلبَ ثمّ وقّعه أو ارفضه من شاشة طلبات المحو."


def send_signature_request(erasure_request: Any, recipients: Iterable[Any]) -> None:
    """إشعارٌ لكلّ موقّعٍ باقٍ — وفشلُه يُسجَّل ولا يُسقط الطلبَ ولا التوقيع."""
    try:
        with transaction.atomic():
            InAppNotification.objects.bulk_create(
                [
                    InAppNotification(
                        user=user,
                        school=erasure_request.school,
                        title=TITLE,
                        body=BODY,
                        event_type="general",
                        priority="high",
                        related_object_id=str(erasure_request.pk),
                        related_url=reverse("erasure_requests"),
                    )
                    for user in recipients
                ]
            )
    except Exception:
        logger.exception("تعذّر إشعارُ موقّعي طلب المحو %s", erasure_request.pk)
