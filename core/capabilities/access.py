"""فحصُ القدرة وحارسُ الشاشة بها (W-20261019-007، نُقل حرفاً من السجلّ)."""

from __future__ import annotations

from core.capabilities.acting import _grant_or_acting, acting_holds, acting_transferable
from core.capabilities.base import Capability
from core.capabilities.registry import registry
from core.capabilities.schedule_developer_only import (
    SCHEDULE_DEVELOPER_ONLY_CAPABILITIES,
    _refuse_excluded_developer,
    schedule_developer_only,
    schedule_developer_only_blocks,
)
from core.permissions import role_required
from core.unrestricted_role import (
    DEVELOPER_EXCLUDED_CAPABILITIES,
    has_unrestricted_role,
    is_excluded_developer,
)


def capability(key: str) -> Capability:
    try:
        return registry()[key]
    except KeyError:
        raise KeyError(f"لا قدرةَ باسم «{key}» في core/capabilities") from None


def has_capability(user, key: str) -> bool:
    """أيملك هذا المستخدمُ هذه القدرة؟ — بالوراثة نفسِها التي يفحص بها الحارس."""
    if user is None or not user.is_authenticated:
        return False
    if is_excluded_developer(user, key):
        return False
    if schedule_developer_only_blocks(user, key):
        return False
    if user.is_superuser or has_unrestricted_role(user):
        return True
    cap = capability(key)
    return user.get_role() in cap.expanded_roles or cap.granted(user) or acting_holds(user, cap)


def capability_required(key: str):
    """حارسُ الشاشة بالقدرة — ``role_required`` بأعضائها، ويحمل اسمَها لمن يقرأ.

    ويُسقط الخطأُ في الاسم عند الاستيراد لا عند الطلب: قدرةٌ مكتوبةٌ خطأً لا تمرّ صامتة.
    """
    cap = capability(key)

    def decorator(view_func):
        if cap.grant is None and not acting_transferable(cap):
            wrapped = role_required(cap.roles, not_inherited_by=cap.not_inherited_by)(view_func)
        else:
            wrapped = _roles_or_grant(cap, view_func)
        if key in DEVELOPER_EXCLUDED_CAPABILITIES:
            wrapped = _refuse_excluded_developer(key, wrapped)
        if key in SCHEDULE_DEVELOPER_ONLY_CAPABILITIES:
            wrapped = schedule_developer_only(key)(wrapped)
        wrapped._capability = key
        return wrapped

    return decorator


def _roles_or_grant(cap: Capability, view_func):
    """``role_required`` نفسُه — ويمرّ معه من مُنح القدرةَ بتكليفه (``cap.grant``).

    والأدوارُ تبقى على الدالّة (``_required_roles``) كما هي: السجلُّ والقائمةُ وحارسُ
    «كلُّ مسارٍ محروس» تقرؤها، والمنحُ في ``_grant`` يُسأل عنه لكلّ مستخدمٍ على حدة.
    """
    from functools import wraps

    from django.shortcuts import redirect

    from core.permissions import _forbidden_response, log_denial

    expanded = cap.expanded_roles

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect("login")
        if (
            user.is_superuser
            or has_unrestricted_role(user)
            or user.get_role() in expanded
            or cap.granted(user)
            or acting_holds(user, cap)
        ):
            return view_func(request, *args, **kwargs)
        role = user.get_role()
        log_denial(request, role=role, required=expanded)
        return _forbidden_response(request, f"ليس لديك صلاحية الوصول — دورك: {role or 'غير محدد'}")

    wrapper._required_roles = tuple(expanded)
    wrapper._grant = _grant_or_acting(cap)
    return wrapper
