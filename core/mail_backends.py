"""core/mail_backends.py — بريدٌ لا يُسلِّم لا يدّعي التسليم.

الافتراضيُّ القديم في الإنتاج كان `console`: يطبع الرسالةَ كاملةً (اسمُ وليّ
الأمر واسمُ الطالب وعددُ الغياب) في سجلّ Railway، ويردّ «أُرسلت»، فيُسجَّل
`NotificationLog.status="sent"` وليس وراءه بريدٌ. هذا الـbackend يُسقط الرسالة
دون أن يكتب منها حرفاً، ويردّ صفراً — والمُستدعي يفحص الردّ.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class UndeliveredEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages: Sequence[Any]) -> int:
        if email_messages:
            logger.warning(
                "بريدٌ لم يُسلَّم: لا مزوّدَ بريدٍ مُهيَّأ (EMAIL_BACKEND) — %d رسالة أُسقطت",
                len(email_messages),
            )
        return 0
