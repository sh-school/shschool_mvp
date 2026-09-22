"""عروضُ خارطة التجويد — تستقبل وتردّ؛ التحقّقُ والكتابةُ والتدقيقُ في `services.py`.

كلُّها لمطوّر المنصّة وحدَه. والتحديثُ POST بجسم JSON صغير، برمز CSRF في الترويسة
`X-CSRFToken` (يُطبَّق `CsrfViewMiddleware` كما على كلّ مسار)، وأيُّ قيمةٍ مرفوضة
ترجع 400 بالحقل وسببه.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from core.developer_access import developer_only
from roadmap import services

_MAX_BODY = 8 * 1024


def _json_body(request: HttpRequest) -> Any:
    """جسمُ الطلب JSON صغيراً، وإلّا `None`."""
    if len(request.body) > _MAX_BODY:
        return None
    try:
        return json.loads(request.body or b"null")
    except ValueError:
        return None


def _apply(
    request: HttpRequest,
    code: str,
    action: Callable[..., dict[str, Any]],
    key: str | None = None,
) -> JsonResponse:
    body = _json_body(request)
    if key is not None:  # قيمةٌ مفردة: {"done": true}
        body = body.get(key) if isinstance(body, dict) and key in body else None
    try:
        row = action(code, body, user=request.user, request=request)
    except services.RoadmapNotFoundError:
        return JsonResponse({"error": "not_found"}, status=404)
    except services.RoadmapError as exc:
        return JsonResponse({"error": "invalid", "fields": exc.errors}, status=400)
    return JsonResponse({"ok": True, "row": row})


@developer_only
@require_GET
def improvement_roadmap(request: HttpRequest) -> HttpResponse:
    return render(request, "roadmap/roadmap.html", services.page_context())


@developer_only
@require_POST
def item_update(request: HttpRequest, code: str) -> JsonResponse:
    return _apply(request, code, services.update_item)


@developer_only
@require_POST
def decision_update(request: HttpRequest, code: str) -> JsonResponse:
    return _apply(request, code, services.update_decision)


@developer_only
@require_POST
def checklist_update(request: HttpRequest, code: str) -> JsonResponse:
    return _apply(request, code, services.set_checklist_done, key="done")


@developer_only
@require_POST
def item_create(request: HttpRequest) -> JsonResponse:
    try:
        row = services.create_item(_json_body(request), user=request.user, request=request)
    except services.RoadmapError as exc:
        return JsonResponse({"error": "invalid", "fields": exc.errors}, status=400)
    return JsonResponse({"ok": True, "row": row}, status=201)
