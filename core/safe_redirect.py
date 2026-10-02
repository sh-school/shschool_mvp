"""إعادةُ توجيهٍ تُبنى من قيمٍ مُتحقَّقٍ منها لا من مُدخَل الطلب (py/url-redirection).

W-20261002-004: لا يُمرَّر `request.get_full_path()` ولا نصٌّ خامٌ في الرابط؛ يُعاد البناءُ
من اسم المسار ومعاملاتٍ تُرمَّز بـ`urlencode`، ثمّ يُتحقَّق من أنّ الناتج على المضيف نفسِه.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(
    request: HttpRequest,
    view_name: str,
    params: dict[str, str],
    *,
    args: list | None = None,
    fallback: str | None = None,
) -> HttpResponseRedirect:
    """يعيد التوجيهَ إلى `view_name` بمعاملاتٍ مرمَّزة، أو إلى `fallback` إن لم يكن الناتجُ آمناً."""
    target = f"{reverse(view_name, args=args)}?{urlencode(params)}"
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(fallback or view_name)
    return redirect(target)
