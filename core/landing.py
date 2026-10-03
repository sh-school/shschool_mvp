"""وجهةُ المستخدم الافتراضيّة — لا فخَّ في /dashboard/ (W-20261003-024، P1).

كان كلُّ مصادَقٍ يُوجَّه إلى /dashboard/ بعد الدخول وعلى `/auth/login/`، والعرضُ يشترط القدرةَ `dashboard.open`.
فدورٌ بلا هذه القدرة (`specialist`، «أخصائي (قديم)»: في المنصّة موظّفٌ لكنّ جدولَ القدرات نسيه) يدور:
login ← /dashboard/ ← 403 ← «العودة للرئيسية» ← /dashboard/ ← 403. وهو يملك `behavior.committee` فيُفتح له
/behavior/committee/ بلا مشكلة.

فالوجهةُ تُحسب من **القدرة الفعليّة**: `dashboard` لمن يملك `dashboard.open`، وإلّا أوّلُ وجهةٍ من `ROLE_LANDINGS` لدوره
**يملك القدرةَ المرافقةَ لها فعلاً** (لا جدولَ ثابتاً يتجاوز الصلاحيات)، وإلّا لا وجهةَ (`None`) فيبقى المنعُ بصفحته
وفيها زرُّ الخروج. و`tests/test_default_landing.py` يمرّ على كلّ دورٍ فيفشل إن أُضيف دورٌ بلا لوحةٍ ولا وجهة.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from django.shortcuts import redirect
from django.urls import reverse

from core.capabilities import has_capability

#: دورٌ بلا لوحة ← وجهاتُه بالترتيب، كلٌّ بالقدرة التي يجب أن يملكها لتُعاد. (اسمُ المسار، القدرة).
ROLE_LANDINGS: dict[str, tuple[tuple[str, str], ...]] = {
    "specialist": (("behavior:committee", "behavior.committee"),),
}


def default_landing(user: Any) -> str | None:
    """رابطُ أوّل وجهةٍ مسموحةٍ للمستخدم، أو `None` إن لم تكن له وجهة."""
    if has_capability(user, "dashboard.open"):
        return reverse("dashboard")
    for url_name, capability in ROLE_LANDINGS.get(user.get_role(), ()):
        if has_capability(user, capability):
            return reverse(url_name)
    return None


def landing_or_denied(view: Callable[..., HttpResponseBase]) -> Callable[..., HttpResponseBase]:
    """مَن لا يملك `dashboard.open` ولدوره وجهةٌ يُحوَّل إليها بدل 403 — فلا حلقةَ بين الدخول والمنع.

    يُوضَع **فوق** `capability_required("dashboard.open")` فيبقى العرضُ محروساً بقدرته (المنعُ لمن لا وجهةَ له).
    """

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        user = request.user
        if user.is_authenticated and not has_capability(user, "dashboard.open"):
            destination = default_landing(user)
            if destination:
                return redirect(destination)
        return view(request, *args, **kwargs)

    return wrapper
