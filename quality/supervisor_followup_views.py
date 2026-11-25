"""شاشاتُ متابعة أداء المشرف الإداريّ (نموذج 19) — القراءةُ في selectors والكتابةُ في services.

المديرُ والنائبُ الإداريّ يُنشئان ويعدّلان؛ والمشرفُ يقرأ متابعاته المحفوظةَ وحدَها؛ وغيرُهم 403.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core.audit_export import log_export
from core.audit_repr import masked_repr
from core.capabilities import capability_required, has_capability
from core.exports import messages as export_messages
from core.exports.services import error_response, respond_export
from core.models import CustomUser
from core.pdf_utils import content_disposition

from . import supervisor_followup_exports as exports
from . import supervisor_followup_selectors as selectors
from . import supervisor_followup_services as services
from .supervisor_followup_indicators import INDICATORS, RATINGS
from .supervisor_followup_models import SupervisorFollowUp

logger = logging.getLogger(__name__)

VIEW = "quality.supervisor_followup_view"
MANAGE = "quality.supervisor_followup"


def _form_context(
    request: HttpRequest,
    pk: uuid.UUID,
    supervisor: CustomUser,
    followup: SupervisorFollowUp | None,
    data: services.FormData | None = None,
) -> dict[str, Any]:
    """`data` ما أُرسل ورُفض (فلا يضيع)، وإلا فمن المتابعة المحفوظة."""
    school = request.school  # type: ignore[attr-defined]
    day = followup.follow_date if followup else timezone.localdate()
    if data is not None:
        try:
            day = dt.date.fromisoformat(data.follow_date)
        except ValueError:
            data.follow_date = day.isoformat()
    previous = selectors.previous_saved(school, supervisor, day, followup)
    items = selectors.review_items(school, followup, previous)
    detail = selectors.detail_context(school, followup) if followup else None
    if data is None:
        data = services.FormData(follow_date=day.isoformat())
        if followup and detail:
            data.strengths, data.improvements = followup.strengths, followup.improvements
            data.scores = {n: (s.rating, s.note) for n, s in detail["scores"].items()}
            data.recommendations = [(str(r.pk), r.text) for r in detail["recommendations"]]
            data.reviews = {
                str(r.pk): (r.status, r.note) for r in items if r.reviewed_in_id == followup.pk
            }
    # مفتاحُ المسودة المحلّيّة: معرّفاتٌ بلا أسماء؛ و`version` يُسقط مسودةً أقدمَ من المحفوظ.
    new_key = f"supervisor-followup:{request.user.pk}:new:{supervisor.pk}"
    edit_key = f"supervisor-followup:{request.user.pk}:{pk}"
    stamp = followup or previous
    return {
        "pk": pk,
        "followup": followup,
        "supervisor": supervisor,
        "data": data,
        "day": day,
        "summary": selectors.attendance_summary(school, supervisor, day, previous),
        "reviews": [(r, *data.reviews.get(str(r.pk), ("pending", ""))) for r in items],
        "rows": [(n, text, *data.scores.get(n, ("", ""))) for n, text in INDICATORS],
        "ratings": RATINGS,
        "today": timezone.localdate(),
        "draft_key": edit_key if followup else new_key,
        "draft_version": stamp.updated_at.isoformat() if stamp else "none",
        "draft_clear": f"{edit_key} {new_key}" if request.GET.get("saved") else "",
    }


@login_required
@capability_required(VIEW)
def supervisor_followup_list(request: HttpRequest) -> HttpResponse:
    own: Any = None if has_capability(request.user, MANAGE) else request.user
    context = selectors.list_context(request.school, own=own)  # type: ignore[attr-defined]
    return render(request, "quality/supervisor_followup_list.html", context)


@login_required
@capability_required(MANAGE)
def supervisor_followup_new(request: HttpRequest, supervisor_id: uuid.UUID) -> HttpResponse:
    school = request.school  # type: ignore[attr-defined]
    supervisor = selectors.supervisors(school).filter(pk=supervisor_id).first()
    if supervisor is None:
        raise Http404
    draft = selectors.open_draft(school, supervisor)
    if draft is not None:
        return redirect("supervisor_followup_edit", pk=draft.pk)
    context = _form_context(request, uuid.uuid4(), supervisor, None)
    return render(request, "quality/supervisor_followup_form.html", context)


@login_required
@capability_required(MANAGE)
def supervisor_followup_edit(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """GET لمتابعةٍ قائمة؛ وPOST ينشئها بهذا المعرّف أو يحدّثها."""
    school = request.school  # type: ignore[attr-defined]
    if request.method != "POST":
        followup = selectors.get_follow_up(school, pk)
        context = _form_context(request, pk, followup.supervisor, followup)
        return render(request, "quality/supervisor_followup_form.html", context)
    data = services.parse_post(request.POST)
    final = request.POST.get("action") == "save"
    try:
        followup = services.save_follow_up(
            school,
            pk,
            supervisor_id=request.POST.get("supervisor", ""),
            data=data,
            final=final,
            request=request,
        )
    except services.FollowUpError as error:
        messages.error(request, str(error))
        existing = selectors.follow_ups(school).filter(pk=pk).first()
        supervisor = (
            existing.supervisor
            if existing
            else selectors.get_supervisor(school, request.POST.get("supervisor", ""))
        )
        context = _form_context(request, pk, supervisor, existing, data)
        return render(request, "quality/supervisor_followup_form.html", context)
    done = followup.status == "saved"
    messages.success(request, "حُفظت المتابعة." if done else "حُفظت المسودة.")
    name = "supervisor_followup_detail" if done else "supervisor_followup_edit"
    return redirect(f"{reverse(name, args=[followup.pk])}?saved=1")


@login_required
@capability_required(VIEW)
def supervisor_followup_detail(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    school = request.school  # type: ignore[attr-defined]
    followup = selectors.readable_follow_up(school, request.user, pk)
    manage = has_capability(request.user, MANAGE)
    context = selectors.detail_context(school, followup)
    scores = context.pop("scores")
    context.update(
        followup=followup,
        can_manage=manage,
        rows=[(n, text, scores.get(n)) for n, text in INDICATORS],
        draft_clear=(
            f"supervisor-followup:{request.user.pk}:{pk} "
            f"supervisor-followup:{request.user.pk}:new:{followup.supervisor_id}"
            if request.GET.get("saved")
            else ""
        ),
    )
    return render(request, "quality/supervisor_followup_detail.html", context)


@login_required
@capability_required(VIEW)
@xframe_options_sameorigin
def supervisor_followup_pdf(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """نموذج 19 PDF: معاينةٌ inline (إطارٌ من الأصل نفسِه لهذه الاستجابة وحدَها)، و`?download=1` عبر مركز التصدير."""
    school = request.school  # type: ignore[attr-defined]
    followup = selectors.readable_follow_up(school, request.user, pk)
    params = QueryDict(mutable=True)
    params["pk"] = str(followup.pk)
    if request.GET.get("download"):
        return respond_export(request, exports.KIND, params=params)
    who = masked_repr(followup.supervisor)
    log_export(
        request,
        "quality.supervisor_followup_pdf",
        rows=1,
        object_id=followup.pk,
        object_repr=f"متابعة مشرف إداري — {who} — {followup.follow_date}",
    )
    try:
        result = exports.build_followup_pdf(school, request.user, params)
    except Exception:  # noqa: BLE001 — تعذُّرُ التوليد رسالةٌ ثابتةٌ لا 500 ولا نصَّ استثناء
        logger.error("supervisor_followup_pdf_failed id=%s", followup.pk)
        return error_response(request, 503, export_messages.FAILED)
    response = HttpResponse(result.content, content_type=result.content_type)
    response["Content-Disposition"] = content_disposition(result.filename, as_attachment=False)
    return response


@login_required
@capability_required(VIEW)
def supervisor_followup_pdf_view(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """صفحةٌ عارضةٌ حول الملفّ: رجوعٌ وتنزيلٌ وطباعة."""
    school = request.school  # type: ignore[attr-defined]
    followup = selectors.readable_follow_up(school, request.user, pk)
    return render(request, "quality/supervisor_followup_pdf_view.html", {"followup": followup})


@login_required
@capability_required(MANAGE)
@require_POST
def supervisor_followup_delete(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    followup = selectors.get_follow_up(request.school, pk)  # type: ignore[attr-defined]
    services.delete_follow_up(followup, request)
    messages.success(request, "حُذفت المتابعة.")
    return redirect("supervisor_followup_list")
