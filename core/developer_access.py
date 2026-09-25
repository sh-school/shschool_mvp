"""مطوّرُ المنصّة — من يرى «أدوات المطوّر» (دليلُ الهويّة، خارطةُ التجويد).

قرارُ المالك 2026-09-20: superuser أو عضوُ مجموعة `developers`. وكان التعريفُ
مكرَّراً في ثلاثة مواضع (مُزيِّنُ دليل الهويّة، ومعالجُ السياق الذي يُظهر القائمةَ،
وصندوقُ رسائل المطوّر) فصار هذا الملفُّ مرجعَه الوحيد للأوّلَين، كي لا تظهر
القائمةُ لمن ترفضه الصفحةُ أو العكس.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

DEVELOPERS_GROUP = "developers"

_View = TypeVar("_View", bound=Callable[..., HttpResponse])


def is_platform_developer(user: Any) -> bool:
    """superuser أو مجموعة `developers` — ولا شيء لمجهولٍ."""
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser or user.groups.filter(name__iexact=DEVELOPERS_GROUP).exists())


def developer_only(view: _View) -> _View:
    """يسمح لمطوّر المنصّة وحدَه: مجهولٌ يُحوَّل إلى الدخول، وغيرُ المطوّر 403."""

    @wraps(view)
    @login_required
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not is_platform_developer(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped  # type: ignore[return-value]
