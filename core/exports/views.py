"""حالةُ التصدير وتنزيلُه وصفحةُ متابعته — كلُّها محصورةٌ بصاحب الطلب في مدرسته.

`get_object_or_404(job, school=request.school, requested_by=request.user)`: صفٌّ لغير صاحبه أو في مدرسةٍ أخرى 404 كأنّه لم يكن.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from core.audit_export import log_export
from core.models import ExportJob

from . import messages
from .services import file_response, status_payload
from .timeouts import expire_if_stale


def _own_job(request: Any, job_id: Any) -> ExportJob:
    job = get_object_or_404(ExportJob, id=job_id, school=request.school, requested_by=request.user)
    expire_if_stale(job)  # عالقٌ أكثرَ من المهلة → يفشل برمز timeout فيتوقّف السؤال
    return job


@login_required
@require_GET
def export_status(request: Any, job_id: Any) -> JsonResponse:
    """JSON دائماً (بلا `?format=json`) — الوسيطُ القديمُ يُتجاهل."""
    return JsonResponse(status_payload(_own_job(request, job_id)))


@login_required
@require_GET
def export_download(request: Any, job_id: Any) -> HttpResponse:
    """الملفُّ نفسُه؛ قابلٌ للإعادة ما دام الصفُّ حيّاً (24 ساعةً ثمّ يُحذف الصفُّ فيردّ 404). كلُّ جلبةٍ تُدقَّق."""
    job = _own_job(request, job_id)
    if job.status != "done":
        return JsonResponse({"status": job.status, "download_url": None, "error": None}, status=409)
    log_export(request, job.kind, object_repr=f"{job.kind}:download")
    return file_response(bytes(job.content or b""), job.content_type, job.filename)


@login_required
@require_GET
def export_page(request: Any, job_id: Any) -> HttpResponse:
    """صفحةُ المتابعة لمن بلا JS: تُحدِّث نفسَها كلَّ ثانيتين، وحين يجهز الناتجُ يُرجع الرابطُ الملفَّ نفسَه."""
    job = _own_job(request, job_id)
    if job.status == "done":
        return redirect(reverse("export_download", args=[job.id]))
    error = (
        messages.message_for(messages.stored_code(job.error_message))
        if job.status == "failed"
        else ""
    )
    return render(request, "core/export_status.html", {"job": job, "error": error})
