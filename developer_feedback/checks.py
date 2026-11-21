"""فحص Django يحذّر عند غياب `DEVELOPER_FEEDBACK_RECIPIENT` في الإنتاج (W-20261121-005).

بلا مستلِم تُعلَّم كلُّ رسالة «فاشلة» بصمت وتبقى سطرَ سجلّ فقط. هذا التحذير يظهر عند
`manage.py check` وعند الإقلاع، فيعرف المالك قبل أن تضيع الرسائل.
لا يُكتب بريدٌ افتراضيّ هنا: الضبط على المنصّة وحدَها.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import CheckMessage, Tags, Warning, register

W_RECIPIENT_MISSING = "developer_feedback.W001"


@register(Tags.security)
def check_developer_recipient(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    """يُرجع تحذيراً واحداً إن كان المستلِم فارغاً في إنتاج المنصّة.

    يقتصر على بيئة Railway الفعليّة (`RAILWAY_ENVIRONMENT`) لأنّ فحص النشر في CI
    يفشل عند أيّ تحذير ولا مستلِم هناك.
    """
    if getattr(settings, "DEBUG", False) or not os.environ.get("RAILWAY_ENVIRONMENT"):
        return []
    if getattr(settings, "DEVELOPER_FEEDBACK_RECIPIENT", ""):
        return []
    return [
        Warning(
            "DEVELOPER_FEEDBACK_RECIPIENT غير مضبوط في الإنتاج: كل ملاحظة إلى المطوّر "
            "ستُسجَّل «فاشلة» دون إشعار.",
            hint="اضبط المتغيّر على المنصّة، ثم أعد إرسال الإشعارات الفاشلة بالأمر "
            "resend_developer_notifications.",
            id=W_RECIPIENT_MISSING,
        )
    ]
