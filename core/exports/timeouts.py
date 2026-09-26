"""مهلةُ صفوف التصدير الخلفيّ — مهمّةٌ لا تنتهي لا تُبقي الصفحةَ تُحدِّث نفسَها إلى الأبد.

صفحةُ المتابعة (`export_page`) والحالةُ (`export_status`) تُسأل ما دامت الحالةُ `pending` أو `running`.
فلو لم يلتقط عاملٌ المهمّةَ (لا عاملَ يعمل، أو يقرأ قاعدةً أخرى كما في خوادم الجلسات المتوازية) أو ماتت في
منتصفها، بقيت الصفحةُ تسأل بلا نهاية ولا رسالة. فالصفُّ الذي تجاوز `EXPORT_JOB_TIMEOUT` يُحوَّل إلى `failed`
برمز `timeout`، فيتوقّف السؤالُ ويظهر السببُ (`messages.py`) ورابطُ العودة.

المهلةُ 3 دقائق: سقفُ المهمّة نفسِها 170 ثانيةً (`time_limit` في `core.export.run_job`) وما بقي هامشٌ لانتظار
الطابور. والعاملُ يتخطّى أصلاً كلَّ صفٍّ ليس `pending`، فمهمّةٌ انتهت مهلتُها ثمّ التقطها عاملٌ متأخّراً لا تُنفَّذ.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from core.models import ExportJob

EXPORT_JOB_TIMEOUT = timedelta(minutes=3)

ACTIVE_STATUSES = ("pending", "running")


def expire_if_stale(job: ExportJob, *, now: datetime | None = None) -> bool:
    """يحوّل صفَّ تصديرٍ عالقاً إلى `failed` برمز `timeout`؛ يُعيد `True` إن غيّره هذه المرّة.

    التحديثُ مشروطٌ بأنّ الحالةَ ما زالت نشطةً في القاعدة، فلا يطغى على صفٍّ أنهاه
    العاملُ للتوّ (`done`/`failed`). وعند خسارة السباق يُعاد تحميلُ الصفّ ليعكس الواقع.
    """
    if job.status not in ACTIVE_STATUSES:
        return False
    moment = now or timezone.now()
    if moment - job.created_at < EXPORT_JOB_TIMEOUT:
        return False
    changed = ExportJob.objects.filter(pk=job.pk, status__in=ACTIVE_STATUSES).update(
        status="failed", error_message="timeout", finished_at=moment
    )
    job.refresh_from_db(fields=["status", "error_message", "finished_at"])
    return bool(changed)
