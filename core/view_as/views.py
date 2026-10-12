"""صفحةُ «عرض بصفة» وأفعالُها — لمطوّر المنصّة الفعليّ وحدَه (W-20261009-032).

«الفعليّ»: مطوّرٌ بدوره الحقيقيّ، أو مطوّرٌ يعاين الآن بصفة دور (يبدّله أو ينهيه). أمّا الحسابُ المرتبط فلا يرى
القائمة — جلستُه للمعلّم — وفعلُه الوحيد هنا العودةُ إلى حساب المطوّر.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.models import CustomUser, LinkedAccount

from . import linked, preview, state
from .audit import preview_label, record
from .middleware import go
from .policy import (
    LINKED_SWITCHES_PER_HOUR,
    ROLE_SWITCHES_PER_HOUR,
    VIEWABLE_ROLES,
    role_groups,
)

NOT_DEVELOPER = "«عرض بصفة» لمطوّر المنصّة وحدَه."
LIMIT_TEMPLATE = "developer/view_as_limit.html"


def _view_as(request: HttpRequest) -> state.ViewAs | None:
    return getattr(request, "view_as", None)


def is_real_developer(request: HttpRequest) -> bool:
    view_as = _view_as(request)
    if view_as is not None:
        return view_as.is_preview
    return preview.can_start(request.user)


def _deny(request: HttpRequest, why: str, **extra: Any) -> None:
    """يسجّل الرفضَ ثمّ يرفع 403 — محاولةُ غير المطوّر أثرٌ في السجلّ لا صمت."""
    view_as = _view_as(request)
    acting = view_as.acting() if view_as is not None else {"actor": str(request.user.pk)}
    record(
        request,
        "view_as_denied",
        actor=request.user,
        acting=acting,
        label="رفضُ «عرض بصفة» لغير مطوّر المنصّة",
        why=why,
        **extra,
    )
    raise PermissionDenied(NOT_DEVELOPER)


def _real_actor(request: HttpRequest) -> CustomUser:
    """حسابُ المطوّر من القاعدة لا الكائنُ المقنَّع في الطلب — للتحقّق من دوره الحقيقيّ وكلمة مروره."""
    return CustomUser.objects.get(pk=request.user.pk)


def _limit(
    request: HttpRequest, *, actor: Any, acting: dict[str, str], kind: str, per_hour: int
) -> HttpResponseBase:
    record(
        request,
        "view_as_limit",
        actor=actor,
        acting=acting,
        label=f"تجاوزُ حدّ التبديل ({per_hour} في الساعة)",
        kind=kind,
    )
    return render(request, LIMIT_TEMPLATE, {"per_hour": per_hour}, status=429)


@login_required
@require_GET
def picker(request: HttpRequest) -> HttpResponseBase:
    if not is_real_developer(request):
        _deny(request, "picker")
    links = (
        LinkedAccount.objects.filter(developer_id=request.user.pk, is_active=True)
        .select_related("target")
        .order_by("created_at")
    )
    return render(
        request,
        "developer/view_as.html",
        {
            "groups": role_groups(),
            "current": _view_as(request),
            "links": links,
        },
    )


@login_required
@require_POST
def start(request: HttpRequest) -> HttpResponseBase:
    role = str(request.POST.get("role") or "")[:40]
    if not is_real_developer(request):
        _deny(request, "start", role=role)
    actor = request.user
    current = _view_as(request)
    acting = {"actor": str(actor.pk), "as_role": role}
    if role not in VIEWABLE_ROLES:
        _deny(request, "unknown_role", role=role)
    if not state.allow_switch(actor.pk, state.PREVIEW, ROLE_SWITCHES_PER_HOUR):
        return _limit(
            request, actor=actor, acting=acting, kind=state.PREVIEW, per_hour=ROLE_SWITCHES_PER_HOUR
        )
    view_as, previous = preview.start(request, actor, role)
    request.view_as = view_as  # type: ignore[attr-defined]
    switched = current is not None and bool(previous)
    record(
        request,
        "view_as_switch" if switched else "view_as_start",
        actor=actor,
        acting=view_as.acting(),
        label=preview_label("تبديلُ الدور المعروض" if switched else "بدءُ معاينة الدور", role),
        role=role,
        previous=previous if switched else "",
    )
    return go(request, reverse("dashboard"))


@login_required
@require_POST
def stop(request: HttpRequest) -> HttpResponseBase:
    view_as = _view_as(request)
    if view_as is None or not view_as.is_preview:
        return go(request, reverse("dashboard"))
    preview.clear(request)
    record(
        request,
        "view_as_end",
        actor=request.user,
        acting=view_as.acting(),
        label=preview_label("انتهاءُ معاينة الدور", view_as.role),
        why="user",
    )
    request.view_as = None  # type: ignore[attr-defined]
    messages.success(request, "انتهت معاينةُ الدور — الجلسةُ بصفة المطوّر من جديد.")
    return go(request, reverse("view_as_picker"))


def _active_link(actor: CustomUser, pk: Any) -> LinkedAccount:
    return get_object_or_404(
        LinkedAccount.objects.select_related("target"), pk=pk, developer=actor, is_active=True
    )


def _link_refused(
    request: HttpRequest, actor: CustomUser, link: LinkedAccount
) -> HttpResponseBase | None:
    """شروطُ الربط والدخول تُفحص عند كلّ تبديل لا عند الإنشاء وحدَه — قد يتغيّر الهدفُ بعده."""
    problems = linked.link_problems(actor, link.target, exclude_pk=link.pk)
    problems += linked.entry_problems(request, link.target)
    if not problems:
        return None
    record(
        request,
        "view_as_denied",
        actor=actor,
        acting={"actor": str(actor.pk), "as_user": str(link.target_id)},
        label="رفضُ التبديل إلى الحساب المرتبط",
        model_name="LinkedAccount",
        object_id=link.pk,
        why="link_problems",
        problems=problems,
    )
    for problem in problems:
        messages.error(request, problem)
    return go(request, reverse("view_as_picker"))


def _enter(request: HttpRequest, actor: CustomUser, link: LinkedAccount) -> HttpResponseBase:
    acting = {"actor": str(actor.pk), "as_user": str(link.target_id)}
    if not state.allow_switch(actor.pk, state.LINKED, LINKED_SWITCHES_PER_HOUR):
        return _limit(
            request,
            actor=actor,
            acting=acting,
            kind=state.LINKED,
            per_hour=LINKED_SWITCHES_PER_HOUR,
        )
    current = _view_as(request)
    if current is not None and current.is_preview:
        preview.clear(request)
        record(
            request,
            "view_as_end",
            actor=actor,
            acting=current.acting(),
            label=preview_label("انتهاءُ معاينة الدور", current.role),
            why="linked",
        )
    request.view_as = linked.enter(request, actor, link)  # type: ignore[attr-defined]
    record(
        request,
        "view_as_linked_in",
        actor=actor,
        acting=acting,
        label="دخولُ الحساب المرتبط بالمطوّر",
        model_name="LinkedAccount",
        object_id=link.pk,
        target=str(link.target_id),
    )
    return go(request, reverse("dashboard"))


@login_required
@require_POST
def linked_switch(request: HttpRequest, pk: Any) -> HttpResponseBase:
    if not is_real_developer(request):
        _deny(request, "linked_switch", link=str(pk))
    actor = _real_actor(request)
    link = _active_link(actor, pk)
    refused = _link_refused(request, actor, link)
    if refused is not None:
        return refused
    if link.confirmed_at is None or not linked.has_reauth(request, actor):
        return go(request, reverse("view_as_linked_confirm", args=[link.pk]))
    return _enter(request, actor, link)


@login_required
@require_http_methods(["GET", "POST"])
def linked_confirm(request: HttpRequest, pk: Any) -> HttpResponseBase:
    """إعادةُ تأكيد هويّة المطوّر نفسِه — أوّلَ تبديلٍ في الجلسة، وأوّلَ استعمالٍ لكلّ ربط."""
    if not is_real_developer(request):
        _deny(request, "linked_confirm", link=str(pk))
    actor = _real_actor(request)
    link = _active_link(actor, pk)
    refused = _link_refused(request, actor, link)
    if refused is not None:
        return refused
    error = ""
    status = 200
    if request.method == "POST":
        acting = {"actor": str(actor.pk), "as_user": str(link.target_id)}
        if linked.reauth_locked(actor):
            return _limit(request, actor=actor, acting=acting, kind="reauth", per_hour=0)
        if linked.verify_reauth(actor, str(request.POST.get("secret") or "")):
            linked.clear_reauth_failures(actor)
            linked.remember_reauth(request, actor)
            return _enter(request, actor, link)
        linked.note_reauth_failure(actor)
        record(
            request,
            "view_as_denied",
            actor=actor,
            acting=acting,
            label="تأكيدُ هويّة المطوّر لم يصحّ",
            model_name="LinkedAccount",
            object_id=link.pk,
            why="reauth_failed",
        )
        error = "لم يصحّ التأكيد — أعد المحاولة."
        status = 400
    return render(
        request,
        "developer/view_as_confirm.html",
        {
            "link": link,
            "second_factor": linked.uses_second_factor(actor),
            "error": error,
        },
        status=status,
    )


@login_required
@require_POST
def linked_exit(request: HttpRequest) -> HttpResponseBase:
    view_as = _view_as(request)
    if view_as is None or not view_as.is_linked:
        return go(request, reverse("dashboard"))
    payload = linked.current_payload(request)
    actor = CustomUser.objects.filter(pk=view_as.actor_id).first()
    if payload is None or actor is None:
        raise Http404
    record(
        request,
        "view_as_linked_out",
        actor=actor,
        acting=view_as.acting(),
        label="عودةٌ من الحساب المرتبط إلى حساب المطوّر",
        model_name="LinkedAccount",
        object_id=view_as.link_id,
        why="user",
        target=view_as.target_id,
    )
    linked.restore(request, actor, payload)
    request.view_as = None  # type: ignore[attr-defined]
    messages.success(request, "عادت الجلسةُ إلى حساب المطوّر.")
    return go(request, reverse("view_as_picker"))
