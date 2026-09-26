"""ما يجري في العامل لصفّ تصدير: قدرةٌ، بناءٌ، سقفُ حجم، ورموزُ خطأٍ ثابتة.

**لا نصَّ استثناءٍ في أيّ مكان** (عقدُ Backend، 2026-09-26): `str(exc)` كان يُخزَّن في `ExportJob.error_message` (2000 حرفاً)
ويُعاد للعميل، و`logger.exception` كان يُنتج حدثَ Sentry بإطاراتٍ فيها متغيّراتٌ محلّيّةٌ (`ctx`، `get_params`، `content`)
لا يُنقّيها `before_send` (يُنقّي بالمفتاح لا بقيم القواميس الكبيرة). فيُسجَّل هنا معرّفُ الصفّ وkind ورمزُ الخطأ والمدّةُ
والحجمُ وحدَها، بلا `exc_info`.
"""

from __future__ import annotations

import logging
import time

from celery.exceptions import SoftTimeLimitExceeded
from django.http import QueryDict
from django.utils import timezone

from core.capabilities import has_capability
from core.celery_tasks import school_rls_scope
from core.models import ExportJob

from . import messages, registry

logger = logging.getLogger(__name__)


def _fail(job: ExportJob, code: str, started: float) -> dict:
    ms = round((time.monotonic() - started) * 1000)
    ExportJob.objects.filter(pk=job.pk).update(
        status="failed", error_message=code, finished_at=timezone.now()
    )
    # رسالةٌ ثابتةٌ بقيمٍ آمنةٍ فقط — يجمعها Sentry بقالبها لا بنصٍّ متغيّر.
    logger.error("export_job_failed kind=%s job=%s code=%s ms=%d", job.kind, job.id, code, ms)
    return {"ok": False, "code": code}


def run_job(job_id: str) -> dict:
    job = ExportJob.objects.select_related("school", "requested_by").filter(pk=job_id).first()
    if job is None:
        logger.warning("export_job_missing job=%s", job_id)
        return {"ok": False, "code": "job_not_found"}

    # يلتقط الصفَّ `pending` وحدَه ذرّيّاً: عاملان متزاحمان أو مهمّةٌ أُعيد تسليمُها لا تبنيان مرّتين، ومن انتهت مهلتُه لا يُبنى.
    if not ExportJob.objects.filter(pk=job.pk, status="pending").update(status="running"):
        logger.info("export_job_skipped kind=%s job=%s reason=not_pending", job.kind, job.id)
        return {"ok": False, "code": "not_pending"}

    started = time.monotonic()
    try:
        with school_rls_scope(job.school_id):
            spec = registry.get(job.kind)
            if spec is None:
                return _fail(job, messages.FAILED, started)
            # القدرةُ تُفحص ثانيةً هنا: صلاحيّةٌ سُحبت بين الطلب والتنفيذ لا يُنتَج بها ملفّ.
            if not has_capability(job.requested_by, spec.capability):
                return _fail(job, messages.FORBIDDEN, started)
            result = spec.build(job.school, job.requested_by, QueryDict(job.query_string))
            if len(result.content) > spec.max_bytes:
                return _fail(job, messages.TOO_LARGE, started)
    except SoftTimeLimitExceeded:
        return _fail(job, messages.TIMEOUT, started)
    except Exception:  # noqa: BLE001 — لا `exc_info` ولا نصَّ استثناء (انظر رأس الملفّ)
        return _fail(job, messages.FAILED, started)

    ms = round((time.monotonic() - started) * 1000)
    ExportJob.objects.filter(pk=job.pk).update(
        status="done",
        content=result.content,
        content_type=result.content_type,
        filename=result.filename,
        finished_at=timezone.now(),
    )
    logger.info(
        "export_job_done kind=%s job=%s ms=%d bytes=%d", job.kind, job.id, ms, len(result.content)
    )
    return {"ok": True, "filename": result.filename}
