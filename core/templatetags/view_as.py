"""`{% view_as_state as va %}` — حالةُ «عرض بصفة» للترويسة والشريط (W-20261009-032).

لا يُحسب شيءٌ لغير المطوّر: الطلبُ بلا علامةٍ ولا دورِ مطوّرٍ يعود بقاموسٍ فارغٍ بلا استعلام. والقائمةُ والزرُّ
للمطوّر الفعليّ (ومنه من يعاين الآن بصفة دور)، والشريطُ لكلّ من في أحد الوضعين.
"""

from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def view_as_state(context: Any) -> dict[str, Any]:
    from core.view_as.policy import role_groups, role_label
    from core.view_as.views import is_real_developer

    request = context.get("request")
    if request is None or not getattr(request.user, "is_authenticated", False):
        return {}
    current = getattr(request, "view_as", None)
    can = is_real_developer(request)
    if current is None and not can:
        return {}
    state: dict[str, Any] = {"can": can, "current": current}
    if current is not None and current.is_preview:
        state["label"] = role_label(current.role)
    if can:
        from core.models import LinkedAccount

        state["groups"] = role_groups()
        state["links"] = list(
            LinkedAccount.objects.filter(developer_id=request.user.pk, is_active=True)
            .select_related("target")
            .order_by("created_at")
        )
    return state


@register.filter
def va_role_label(role: str) -> str:
    """اسمُ الدور العربيّ من مفتاحه — `{{ user.get_role|va_role_label }}`."""
    from core.view_as.policy import role_label

    return role_label(role or "")
