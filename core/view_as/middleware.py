"""`ViewAsMiddleware` — يفحص علامةَ «العرض بصفة» في كلّ طلبٍ ويُلبس الطلبَ ما تقوله (W-20261009-032).

- **معاينةُ الدور**: يُلبس `request.user` الدورَ المعروض (`masking.mask_user`) — بعد RLS والجلسة وقبل حارس المسارات
  وكلِّ عرض، فكلُّ ما يقرأ الدورَ يرى المعروض. علامةٌ سقطت تُنهي المعاينة: صفحةُ القراءة تُعرض بصفته الحقيقيّة، وطلبُ
  الكتابة لا يُنفَّذ (قُصد بصلاحيّات دورٍ فلا يمرّ بصلاحيّات المطوّر الكاملة).
- **الحسابُ المرتبط**: الجلسةُ للمعلّم، والعلامةُ تحمل المطوّرَ وبصمةَ كلمة مروره؛ فتُفحص كاملةً كلَّ طلب، فإن انقضت
  مدّتُها أو أُوقف الربطُ أُعيد المطوّر، وإن لم يعد المطوّرُ كما كان أُغلقت الجلسة.

وفي الوضعين: صفحاتُ الحساب نفسِه محظورة، وكلُّ صفحةٍ تُفتح سطرُ `view_as_page` بمسارها وحدَه.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.urls import reverse
from django.utils.functional import LazyObject, empty

from . import linked, preview, state
from .audit import preview_label, record
from .masking import mask_user
from .policy import ACCOUNT_PREFIXES, UNLOGGED_PREFIXES

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

PREVIEW_ENDED = {
    "bad_token": "انتهت معاينةُ الدور: علامتُها لا تثبت.",
    "not_developer": "انتهت معاينةُ الدور: الحسابُ لم يعد مطوّرَ المنصّة الفاعل.",
    "role_removed": "انتهت معاينةُ الدور: الدورُ لم يعد في القائمة.",
    "cap": "انتهت معاينةُ الدور ببلوغ سقفها (ساعتان) — ابدأها من جديد إن شئت.",
    "idle": "انتهت معاينةُ الدور بعد نصف ساعةٍ بلا نشاط.",
}
LINKED_RESTORED = {
    "link_revoked": "أُعيدت الجلسةُ إلى حساب المطوّر: الربطُ أُوقف.",
    "cap": "أُعيدت الجلسةُ إلى حساب المطوّر ببلوغ سقف الحساب المرتبط (ساعة).",
    "idle": "أُعيدت الجلسةُ إلى حساب المطوّر بعد ربع ساعةٍ بلا نشاط.",
}
ACCOUNT_PAGE_DENIED = "صفحاتُ الحساب لا تُفتح أثناء العرض بصفة — عُد إلى حساب المطوّر أوّلاً."


def unwrap(user: Any) -> Any:
    """الكائنُ الحقيقيّ خلف `request.user` الكسول — فما يُلبَس له يراه كلُّ من يقرؤه."""
    if isinstance(user, LazyObject):
        if user._wrapped is empty:
            user._setup()
        return user._wrapped
    return user


def go(request: HttpRequest, url: str) -> HttpResponseBase:
    """تحويلٌ يفهمه htmx أيضاً: طلبُ جزءٍ يُحوَّل بترويسة `HX-Redirect` لا بجزءٍ من صفحةٍ أخرى."""
    if request.headers.get("HX-Request"):
        return HttpResponse(status=204, headers={"HX-Redirect": url})
    return HttpResponseRedirect(url)


def _is_page(request: HttpRequest, response: HttpResponseBase) -> bool:
    return (
        request.method == "GET"
        and response.status_code == 200
        and not request.headers.get("HX-Request")
        and str(response.get("Content-Type", "")).startswith("text/html")
        and not request.path.startswith(UNLOGGED_PREFIXES)
    )


class ViewAsMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        request.view_as = None  # type: ignore[attr-defined]
        # المنفّذُ الفعليّ: المطوّرُ في الوضعين — وفي الحساب المرتبط `request.user` هو المعلّم لا هو.
        request.view_as_actor = None  # type: ignore[attr-defined]
        session = getattr(request, "session", None)
        if session is None or (state.ROLE_KEY not in session and state.LINKED_KEY not in session):
            return self.get_response(request)
        if not request.user.is_authenticated:
            preview.clear(request)
            session.pop(state.LINKED_KEY, None)
            session.pop(state.LINKED_SEEN_KEY, None)
            return self.get_response(request)

        if state.LINKED_KEY in session:
            preview.clear(request)  # لا وضعان معاً: الدخولُ إلى الحساب المرتبط يُنهي المعاينة
            early = self._linked(request)
        else:
            early = self._preview(request)
        if early is not None:
            return early

        view_as: state.ViewAs | None = request.view_as  # type: ignore[attr-defined]
        actor = request.view_as_actor  # type: ignore[attr-defined]
        if view_as is not None and request.path.startswith(ACCOUNT_PREFIXES):
            record(
                request,
                "view_as_denied",
                actor=actor,
                acting=view_as.acting(),
                label=f"صفحةُ حسابٍ محظورةٌ أثناء العرض بصفة: {request.path}",
                why="account_page",
            )
            raise PermissionDenied(ACCOUNT_PAGE_DENIED)

        response = self.get_response(request)
        if view_as is not None and _is_page(request, response):
            try:
                record(
                    request,
                    "view_as_page",
                    actor=actor,
                    acting=view_as.acting(),
                    label=f"صفحةٌ أثناء العرض بصفة: {request.path}",
                )
            except Exception:  # noqa: BLE001 — سطرُ الصفحة لا يُسقط الصفحة
                logger.exception("view_as page audit failed path=%s", request.path)
        return response

    @staticmethod
    def _preview(request: HttpRequest) -> HttpResponseBase | None:
        real = unwrap(request.user)
        verdict, payload = preview.resume(request, real)
        if verdict == "ok" and payload is not None:
            mask_user(real, payload["r"])
            request.view_as_actor = real  # type: ignore[attr-defined]
            request.view_as = state.ViewAs(  # type: ignore[attr-defined]
                kind=state.PREVIEW,
                actor_id=str(real.pk),
                started=int(payload["s"]),
                role=payload["r"],
            )
            return None
        preview.clear(request)
        role = str((payload or {}).get("r") or "")
        record(
            request,
            "view_as_end",
            actor=real,
            acting={"actor": str(real.pk), "as_role": role},
            label=preview_label("انتهاءُ معاينة الدور", role),
            why=verdict,
        )
        messages.info(request, PREVIEW_ENDED[verdict])
        if request.method not in SAFE_METHODS:
            return go(request, reverse("dashboard"))
        return None

    @staticmethod
    def _linked(request: HttpRequest) -> HttpResponseBase | None:
        verdict, actor, payload = linked.resume(request)
        if verdict == "ok" and actor is not None and payload is not None:
            request.view_as_actor = actor  # type: ignore[attr-defined]
            request.view_as = state.ViewAs(  # type: ignore[attr-defined]
                kind=state.LINKED,
                actor_id=str(actor.pk),
                started=int(payload["s"]),
                target_id=str(payload["t"]),
                link_id=str(payload["l"]),
            )
            return None
        acting = {
            "actor": str(actor.pk) if actor is not None else str((payload or {}).get("a") or ""),
            "as_user": str(request.user.pk),
        }
        if verdict == "restore" and actor is not None and payload is not None:
            record(
                request,
                "view_as_linked_out",
                actor=actor,
                acting=acting,
                label="عودةٌ من الحساب المرتبط إلى حساب المطوّر",
                model_name="LinkedAccount",
                object_id=payload.get("l"),
                why=payload.get("why", ""),
                target=acting["as_user"],
            )
            linked.restore(request, actor, payload)
            messages.info(
                request, LINKED_RESTORED.get(payload.get("why", ""), LINKED_RESTORED["idle"])
            )
            return go(request, reverse("view_as_picker"))
        record(
            request,
            "view_as_denied",
            actor=actor if actor is not None else request.user,
            acting=acting,
            label="جلسةُ حسابٍ مرتبطٍ لا تثبت علامتُها — أُغلقت",
            why="linked_session_invalid",
        )
        linked.end_everything(request)
        return go(request, reverse("login"))
