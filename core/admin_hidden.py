"""جدولا رموز JWT خارجَ لوحة الإدارة ما دام JWT مغلقاً (OWN-19).

`rest_framework_simplejwt.token_blacklist` مثبَّتٌ لأنّ رايةَ `API_JWT_ENABLED` قد تُفتح يوماً، وبابُ JWT مغلقٌ منذ
P1-1 فلم يُصدَر منه رمزٌ واحد — فجدولاه فارغان دائماً. وكانا في الإدارة صفحتين فارغتين باسمَين إنجليزيَّين
(«Outstanding Tokens»، «Blacklisted Tokens») يظهران في كلّ صفحةٍ بفهرس بحث القائمة، ولا يُصلح عنوانَهما
كتالوجٌ عربيّ (الحزمةُ بلا ترجمة، وملفُّ .po لا يصل الإنتاج).

فيُلغى تسجيلُهما هنا حين تكون الرايةُ مطفأة، ويعود بها. والقائمةُ الأفقيّة (`core/admin_menu.py:JWT_TABLES`) تتبع الرايةَ
نفسَها فلا يبقى رابطٌ إلى صفحةٍ غيرِ موجودة. ولا تُمَسّ الصلاحيّاتُ ولا المجموعاتُ: صلاحيّاتُهما باقيةٌ خاملة.

يجري في `CoreConfig.ready()` كالوحات axes: تسجيلُ لوحات التطبيقات التلقائيُّ في `ready()` تطبيق الإدارة، قبل `core`.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin


def hide_unused_jwt_tables() -> None:
    """يُلغي تسجيلَ جدولَي الرموز من الإدارة إن كان JWT مغلقاً — آمنٌ لتكراره."""
    if settings.API_JWT_ENABLED:
        return
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    for model in (OutstandingToken, BlacklistedToken):
        if admin.site.is_registered(model):
            admin.site.unregister(model)
