"""حصرُ توليد الجدول واعتماده بمطوّر المنصّة والاستثناءُ من القدرات (W-20261019-007، نُقل حرفاً)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.http import HttpRequest
from django.http.response import HttpResponseBase

from core.unrestricted_role import is_excluded_developer

# ── حصرُ توليد الجدول واعتماده بمطوّر المنصّة (W-20261010-034، أمرُ المالك 2026-10-10) ──────────
#: القدراتُ التي تولّد الجدولَ أو تعتمده. المنفذُ الواحدُ هنا لا في كلّ عرض: `capability_required` يلفّها،
#: و`has_capability` يردّها (فتُغلق `approve_v2` والقوالبُ)، و`approve_schedule` — وقدرتُه `schedule.settings`
#: الأوسعُ من الاعتماد — يلفّه `schedule_developer_only` صراحةً. والقراءةُ (`schedule.view`) لا تمسّ.
SCHEDULE_DEVELOPER_ONLY_CAPABILITIES = frozenset(
    {"schedule.admin", "schedule.operator", "schedule.approve"}
)
SCHEDULE_DEVELOPER_ONLY_MESSAGE = (
    "توليدُ الجدول واعتمادُه محصوران الآن بمطوّر المنصّة — أمرُ المالك. ويبقى لك اطّلاعٌ على الجدول."
)


def schedule_developer_only_active() -> bool:
    """مفتاحُ `SCHEDULE_DEVELOPER_ONLY` (البيئة، الافتراضيّ مشغَّل) — إطفاؤه يعيد السلوكَ السابق بلا شيفرة."""
    from django.conf import settings

    return bool(getattr(settings, "SCHEDULE_DEVELOPER_ONLY", True))


def schedule_developer_only_blocks(user: Any, key: str) -> bool:
    """أيُحجَب هذا المستخدمُ عن هذه القدرة بالحصر؟ — لغير مطوّر المنصّة، والمفتاحُ مشغَّل."""
    if key not in SCHEDULE_DEVELOPER_ONLY_CAPABILITIES or not schedule_developer_only_active():
        return False
    return bool(user.get_role() != "platform_developer")


def schedule_developer_only(key: str) -> Callable:
    """يلفّ عرضاً برفضٍ ظاهرِ السبب وتدقيقٍ بالدور والمسار (بلا اسم المستخدم) لغير مطوّر المنصّة."""
    from functools import wraps

    from core.permissions import _forbidden_response, log_denial

    def decorator(
        view_func: Callable[..., HttpResponseBase],
    ) -> Callable[..., HttpResponseBase]:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            user = request.user
            if user.is_authenticated and schedule_developer_only_blocks(user, key):
                from core.models import AuditLog

                role = user.get_role()
                log_denial(request, role=role, source="schedule_developer_only")
                AuditLog.log(
                    user=user,
                    action="view",
                    model_name="other",
                    object_repr="رُفض توليدُ/اعتمادُ الجدول: محصورٌ بمطوّر المنصّة",
                    changes={"role": role, "path": request.path, "capability": key},
                    school=getattr(request, "school", None),
                    request=request,
                )
                return _forbidden_response(request, SCHEDULE_DEVELOPER_ONLY_MESSAGE)
            return view_func(request, *args, **kwargs)

        for attr in ("_required_roles", "_grant"):
            if hasattr(view_func, attr):
                setattr(wrapper, attr, getattr(view_func, attr))
        return wrapper

    return decorator


def _refuse_excluded_developer(
    key: str, view_func: Callable[..., HttpResponseBase]
) -> Callable[..., HttpResponseBase]:
    """يردّ المطوّرَ عن قدرةٍ استثناها المالكُ (D-128م) قبل أيّ تحقّق آخر — ولو كان superuser."""
    from functools import wraps

    from core.permissions import _forbidden_response, log_denial

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if is_excluded_developer(request.user, key):
            log_denial(request, role="platform_developer", source="excluded_capability")
            return _forbidden_response(request, "رصدُ الحضور ليس للمطوّر — قرارُ المالك D-128م")
        return view_func(request, *args, **kwargs)

    for attr in ("_required_roles", "_grant"):
        if hasattr(view_func, attr):
            setattr(wrapper, attr, getattr(view_func, attr))
    return wrapper
