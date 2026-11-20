"""سياسةُ عنوان اشتراك Push: لا يُخزَّن ولا يُنادى إلّا مضيفُ مزوّدٍ معروف (SSRF).

وحدةٌ بذاتها لأنّ لها مستعملَين: مالكُ التسجيل (`push_subscriptions`) يردّ العنوانَ قبل
تخزينه، ومهمّةُ الإرسال (`tasks`) تعطّل ما خُزّن قبل هذا الفحص ولا تناديه.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings


def is_allowed_push_endpoint(endpoint: str) -> bool:
    """أهذا العنوانُ لمزوّد Push معروف؟ — `https` على منفذه، ومضيفٌ من القائمة أو تحتها.

    العنوانُ يكتبه المتصفّحُ في العادة، لكنّ الطلبَ يكتبه صاحبُه: من يرسل
    `http://<مضيفٌ داخليّ>:<منفذ>/` يجعل العاملَ يطرق ذلك العنوانَ من شبكته عند أوّل
    إشعار (SSRF أعمى). فلا يُخزَّن ولا يُنادى إلّا مضيفُ مزوّدٍ مسمّى في
    `PUSH_ENDPOINT_ALLOWED_HOSTS`؛ وعناوينُ IP الحرفيّة وبياناتُ الدخول في العنوان
    والمنافذُ غيرُ 443 تُردّ بحكم المطابقة نفسِها.
    """
    try:
        parts = urlsplit(endpoint or "")
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    if port not in (None, 443):
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return False
    return any(
        host == allowed or host.endswith(f".{allowed}")
        for allowed in settings.PUSH_ENDPOINT_ALLOWED_HOSTS
    )
