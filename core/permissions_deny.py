"""استبعادُ دورٍ بعينه عن شاشةٍ، صراحةً — ملفٌّ مستقلٌّ عن `core/permissions.py` (حدُّ 1000 سطر).

`deny_role` وحيدةٌ هنا؛ باقي الحرّاس (role_required، capability_required، إلخ) في
core/permissions.py كما هي.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import HttpRequest
from django.http.response import HttpResponseBase

from core.permissions import _forbidden_response, log_denial


def deny_role(
    role: str, *, reason: str
) -> Callable[[Callable[..., HttpResponseBase]], Callable[..., HttpResponseBase]]:
    """استبعادٌ صريحٌ لدورٍ بعينه عن شاشةٍ — ولو كان `is_superuser` (`role_required` يُمرّره دائماً).

    حارسُ `role_required`/`capability_required` العاديّ يعتمد على **غياب** الدور عن مجموعة
    الأدوار المسموحة؛ وهذا هشٌّ أمام تجاوز `is_superuser` الذي يمرّ قبل أيّ تحقّقٍ من الدور
    (`platform_developer` قد يحمل `is_superuser=True` في بيئةٍ ما). فحين يكون الاستبعادُ
    قرارَ سياسةٍ مقصوداً — لا نتيجةً عرضيّةً لعدم الإدراج — يُطبَّق هذا الديكوريتورُ **قبل**
    `role_required`/`capability_required` ليحجب الدورَ بالاسم مهما كانت صفاتُ الحساب الأخرى.

    Usage:
        @deny_role("platform_developer", reason="تحليلاتُ المدرسة محجوبةٌ عنه — قرارُ المالك D-98م")
        @login_required
        @capability_required("analytics.school")
        def my_view(request): ...
    """

    def decorator(view_func: Callable[..., HttpResponseBase]) -> Callable[..., HttpResponseBase]:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if request.user.is_authenticated and request.user.get_role() == role:
                log_denial(request, role=role, source="deny_role")
                return _forbidden_response(request, reason)
            return view_func(request, *args, **kwargs)

        wrapper._denied_role = role  # type: ignore[attr-defined]
        return wrapper

    return decorator
