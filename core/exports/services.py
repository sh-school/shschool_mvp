"""مدخلُ التصدير الموحَّد: `respond_export(request, kind)` — قدرةٌ، ثمّ متزامنٌ أو صفٌّ ومهمّةٌ خلفيّة.

العقدُ مع الواجهة (`static/js/…`، مقعدُ VI-30أ) — بترويسة `X-Requested-With: XMLHttpRequest`:

* ملفٌّ مباشرٌ: `200` + `Content-Disposition: attachment` (نوعٌ متزامنٌ `direct`).
* مهمّةٌ: `202` + JSON `{"job", "job_id", "status_url", "poll_ms"}` ثمّ `GET status_url` → `{status, download_url, error}`.
* `429 busy` و`403 forbidden` و`400 unknown_kind`: JSON `{"error": {"code", "message"}}` — رسالةٌ عربيّةٌ ثابتة.

وبلا الترويسة (JS معطَّل، رابطٌ مفتوحٌ مباشرةً) يُحوَّل الطلبُ إلى صفحة المتابعة `export_page`.

سقوفٌ (عقدُ Backend): ثلاثةُ صفوفٍ نشطةٍ للمستخدم، وdedupe للضغطة المتكرّرة (المستخدم + kind + الاستعلام) خلال 60 ثانيةً تُعيد
الصفَّ نفسَه، وقائمةُ Celery مخصَّصةٌ اختياراً (`settings.EXPORT_JOB_QUEUE`، الافتراضيّ القائمةُ الافتراضيّة كي لا يلزم تغييرُ
أمر تشغيل العامل عند النشر).
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from core.audit_export import log_export
from core.capabilities import has_capability
from core.models import ExportJob

from . import messages, registry
from .timeouts import ACTIVE_STATUSES, EXPORT_JOB_TIMEOUT

logger = logging.getLogger(__name__)

MAX_ACTIVE_PER_USER = 3
DEDUPE_SECONDS = 60
POLL_MS = 2000
#: قفلُ المتزامن: تصديرٌ متزامنٌ واحدٌ للمستخدم في آنٍ — وينتهي وحدَه إن مات الطلب.
DIRECT_LOCK_SECONDS = 15


def is_xhr(request: Any) -> bool:
    return bool(request.headers.get("X-Requested-With") == "XMLHttpRequest")


def error_response(request: Any, status: int, code: str) -> HttpResponse:
    """خطأٌ بلا نصّ استثناءٍ: JSON للـXHR، ونصٌّ عربيٌّ ثابتٌ لغيره."""
    if is_xhr(request):
        return JsonResponse({"error": messages.error_payload(code)}, status=status)
    return HttpResponse(
        messages.message_for(code), status=status, content_type="text/plain; charset=utf-8"
    )


def status_payload(job: ExportJob) -> dict:
    """شكلُ `GET status_url` في العقد: `{status, download_url, error}`."""
    if job.status == "done":
        return {
            "status": "done",
            "download_url": reverse("export_download", args=[job.id]),
            "error": None,
        }
    if job.status == "failed":
        return {
            "status": "failed",
            "download_url": None,
            "error": messages.error_payload(messages.stored_code(job.error_message)),
        }
    return {"status": job.status, "download_url": None, "error": None}


def respond_export(request: Any, kind_name: str, *, params: Any = None) -> HttpResponse:
    """`params` (QueryDict) يحلّ محلَّ `request.GET` حين يحمل المسارُ معاملاً خارج الاستعلام (`class_id` من الرابط)؛ فيُحفظ في
    صفّ التصدير كلُّه ويصل البنّاءَ في العامل."""
    spec = registry.get(kind_name)
    if spec is None:
        # خطأُ برمجةٍ لا خطأُ مستخدم: يفشل مغلقاً برمزٍ ثابتٍ لا بتوليدٍ متزامنٍ صامت (ADR-0004 §2).
        logger.error("export_unknown_kind kind=%s", kind_name)
        return error_response(request, 400, messages.UNKNOWN_KIND)
    if not has_capability(request.user, spec.capability):
        if is_xhr(request):
            return error_response(request, 403, messages.FORBIDDEN)
        raise PermissionDenied
    params = request.GET if params is None else params
    query = params.urlencode()
    if spec.mode == "direct":
        return _respond_direct(request, spec, query, params)
    return _start_job(request, spec, query)


def _start_job(request: Any, spec: registry.ExportKind, query: str) -> HttpResponse:
    now = timezone.now()
    mine = ExportJob.objects.filter(school=request.school, requested_by=request.user)

    # الضغطةُ المتكرّرة (المستخدم + kind + الاستعلام) خلال 60ث: الصفُّ نفسُه، لا مهمّةٌ ثانية.
    twin = (
        mine.filter(
            kind=spec.kind,
            query_string=query,
            created_at__gte=now - timedelta(seconds=DEDUPE_SECONDS),
        )
        .exclude(status="failed")
        .order_by("-created_at")
        .first()
    )
    if twin is not None:
        return _started(request, twin)

    active = mine.filter(
        status__in=ACTIVE_STATUSES, created_at__gte=now - EXPORT_JOB_TIMEOUT
    ).count()
    if active >= MAX_ACTIVE_PER_USER:
        return error_response(request, 429, messages.BUSY)

    log_export(request, spec.kind, object_repr=f"{spec.kind}?{query}")
    job = ExportJob.objects.create(
        school=request.school, requested_by=request.user, kind=spec.kind, query_string=query
    )
    from core.tasks import run_export_job

    run_export_job.apply_async(
        args=(str(job.id),), queue=getattr(settings, "EXPORT_JOB_QUEUE", "celery")
    )
    return _started(request, job)


def _started(request: Any, job: ExportJob) -> HttpResponse:
    if is_xhr(request):
        return JsonResponse(
            {
                "job": str(job.id),
                "job_id": str(job.id),  # الاسمُ القديم — تتّكئ عليه واجهةٌ لم تُحدَّث بعدُ
                "status_url": reverse("export_status", args=[job.id]),
                "poll_ms": POLL_MS,
            },
            status=202,
        )
    return redirect(reverse("export_page", args=[job.id]))


def _respond_direct(
    request: Any, spec: registry.ExportKind, query: str, params: Any
) -> HttpResponse:
    """النمطُ المتزامن (300–1000ms مقيسةً p95 دافئاً) — لا يُسجَّل نوعٌ بلا قياسٍ مثبَّت (`registry.register`).

    تصديرٌ متزامنٌ واحدٌ للمستخدم في آنٍ، ومدّةُ البناء تُسجَّل لترقيته آليّاً إلى `job` إن تجاوز السقف؛
    وحدُّ الخمس ثوانٍ الصلبُ غيرُ مفروضٍ هنا (لا مهلةَ آمنةً داخل طلبِ ASGI) — فهذا سببٌ آخرُ لشرط القياس.
    """
    lock = f"export:direct:{request.user.pk}"
    if not cache.add(lock, "1", timeout=DIRECT_LOCK_SECONDS):
        return error_response(request, 429, messages.BUSY)
    started = time.monotonic()
    try:
        result = spec.build(request.school, request.user, params)
    except Exception:  # noqa: BLE001 — لا نصَّ استثناءٍ في السجلّ ولا في الردّ (رموزٌ ثابتة)
        logger.error("export_direct_failed kind=%s code=%s", spec.kind, messages.FAILED)
        return error_response(request, 500, messages.FAILED)
    finally:
        cache.delete(lock)
    ms = round((time.monotonic() - started) * 1000)
    if len(result.content) > spec.max_bytes:
        logger.warning("export_direct_too_large kind=%s ms=%d", spec.kind, ms)
        return error_response(request, 413, messages.TOO_LARGE)
    logger.info("export_direct kind=%s ms=%d bytes=%d", spec.kind, ms, len(result.content))
    log_export(request, spec.kind, object_repr=f"{spec.kind}?{query}")
    return file_response(result.content, result.content_type, result.filename)


def file_response(content: bytes, content_type: str, filename: str) -> HttpResponse:
    from urllib.parse import quote

    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = (
        f"attachment; filename=export; filename*=UTF-8''{quote(filename)}"
    )
    return response
