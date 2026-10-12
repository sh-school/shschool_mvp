"""معاينةُ الدور — المطوّرُ يرى المنصّةَ ويعمل فيها بصلاحيّات دورٍ من الكادر، وهويّتُه هي هويّتُه (D-303م وD-304م).

العلامةُ في الجلسة الخادميّة موقَّعةٌ وتحمل الفاعلَ والدورَ ولحظةَ البدء الأولى (التبديلُ بين الأدوار لا يمدّ السقف)،
وتُفحص في كلّ طلبٍ في `ViewAsMiddleware`: تسقط إن لم يعد صاحبُها مطوّراً فاعلاً، أو خرج الدورُ من القائمة، أو بلغت
سقفَها (ساعتان) أو خمولَها (نصفُ ساعة).
"""

from __future__ import annotations

from typing import Any

from core.unrestricted_role import has_unrestricted_role

from . import state
from .policy import ROLE_CAP_SECONDS, ROLE_IDLE_SECONDS, VIEWABLE_ROLES


def can_start(user: Any) -> bool:
    """مطوّرُ المنصّة الفاعلُ بدوره الحقيقيّ — لا من يعاين الآن بصفة دور، ولا حسابٌ مرتبطٌ انتُحل."""
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and getattr(user, "view_as_role", None) is None
        and has_unrestricted_role(user)
    )


def current_payload(request: Any) -> dict[str, Any] | None:
    return state.unsign(request.session.get(state.ROLE_KEY), state.ROLE_SALT)


def start(request: Any, actor: Any, role: str) -> tuple[state.ViewAs, str]:
    """يبدأ المعاينةَ أو يبدّل دورَها، ويعيد `(الحالة، الدور السابق أو "")`. السقفُ من البدء الأوّل."""
    previous = current_payload(request)
    same_actor = previous is not None and previous.get("a") == str(actor.pk)
    started = int(previous["s"]) if same_actor and previous.get("s") else state.now()
    moment = state.now()
    request.session[state.ROLE_KEY] = state.sign(
        {"a": str(actor.pk), "r": role, "s": started}, state.ROLE_SALT
    )
    request.session[state.ROLE_SEEN_KEY] = moment
    view_as = state.ViewAs(kind=state.PREVIEW, actor_id=str(actor.pk), started=started, role=role)
    return view_as, (str(previous.get("r") or "") if same_actor else "")


def clear(request: Any) -> None:
    request.session.pop(state.ROLE_KEY, None)
    request.session.pop(state.ROLE_SEEN_KEY, None)


def resume(request: Any, user: Any) -> tuple[str, dict[str, Any] | None]:
    """يفحص المعاينةَ القائمة ويعيد `(الحكم، الحمولة)`: `ok` أو سببُ سقوطها.

    الأسباب: `bad_token` علامةٌ لا تثبت، و`not_developer` صاحبُها لم يعد مطوّراً فاعلاً أو ليس هو من في الجلسة،
    و`role_removed` دورٌ خرج من القائمة، و`cap` السقف، و`idle` الخمول.
    """
    payload = current_payload(request)
    if payload is None:
        return "bad_token", None
    if payload.get("a") != str(user.pk) or not can_start(user):
        return "not_developer", payload
    if payload.get("r") not in VIEWABLE_ROLES:
        return "role_removed", payload
    moment = state.now()
    started = int(payload.get("s") or 0)
    seen = int(request.session.get(state.ROLE_SEEN_KEY) or started)
    if moment - started > ROLE_CAP_SECONDS:
        return "cap", payload
    if moment - seen > ROLE_IDLE_SECONDS:
        return "idle", payload
    request.session[state.ROLE_SEEN_KEY] = moment
    return "ok", payload
