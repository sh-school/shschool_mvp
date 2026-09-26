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

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class UndeliveredEmailBackend(BaseEmailBackend):
    #: لا مزوّدَ حقيقيّاً وراءه: ما يُسقطه لا يُعاد ولا يدخل DLQ ولا يبلغ Sentry (DBT-11)؛ انظر `provider_configured`.
    delivers = False

    def send_messages(self, email_messages: Sequence[Any]) -> int:
        if email_messages:
            logger.warning(
                "بريدٌ لم يُسلَّم: لا مزوّدَ بريدٍ مُهيَّأ (EMAIL_BACKEND) — %d رسالة أُسقطت",
                len(email_messages),
            )
        return 0


def provider_configured() -> bool:
    """هل وراء `EMAIL_BACKEND` مزوّدٌ فعليّ؟ — الافتراضيُّ في الإنتاج بلا مزوّدٍ هو `UndeliveredEmailBackend`.

    بريدٌ لا يُسلَّم في غياب مزوّدٍ ليس عطلاً يُعاد ولا حدثاً يُبلَّغ: تعريفُ المالك (DBT-11) أنّ الإعادة وDLQ وSentry
    لأعطال مزوّدٍ **حقيقيّ** وحدَها. فالبريدُ حينئذٍ يُوسَم `undeliverable` بتحذيرٍ واحدٍ فقط (يكتبه الـbackend نفسُه).
    وأيُّ backend لا يعلن `delivers = False` يُعدّ مزوّداً (SMTP والـlocmem في الاختبارات).
    """
    return bool(getattr(import_string(settings.EMAIL_BACKEND), "delivers", True))
