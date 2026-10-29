"""مهمّة تقارير الغياب الدوريّة (W-20261020-005 الخطوة 5) — عملُ خلفيّةٍ لا يُستدعى من طلب.

مدخلٌ واحدٌ يُشغَّل كلَّ ساعةٍ في الدوام وبعده، ويُولّد ما استحقّ فقط (`due_specs`) وهو ثابتُ التكرار: التشغيلُ الثاني
لا يجد لقطةً ناقصةً فلا يكتب شيئاً. **الجدولةُ معطَّلةٌ افتراضياً** — `ABSENCE_REPORTS_BEAT=1` وحدَه يُدخلها
`beat_schedule` (`absence_reports_beat.py`)، وبعد إعادة نشر خدمة beat بأمر المالك، على نمط `TEACHER_ALERTS_BEAT`.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(name="operations.generate_due_absence_reports")
def generate_due_absence_reports_task() -> dict[str, int]:
    """مدرسةً مدرسةً بنطاق RLS؛ مدرسةٌ معطوبةٌ تُسجَّل ولا تُسقط غيرَها."""
    from core.models import School
    from operations.services.absence_snapshots import generate_due

    now = timezone.localtime()
    created = failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                created += len(generate_due(school, now))
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("generate_due_absence_reports: تعذّر في المدرسة %s", school.pk)
    return {"created": created, "failed_schools": failed}


@shared_task(name="operations.recompute_absence_report")
def recompute_absence_report_task(
    school_id: str, kind: str, scope: str, start: str, end: str, user_id: str
) -> int:
    """نسخةٌ جديدةٌ من لقطةٍ بزرّ «أعد الحساب الآن» — الأقدمُ تبقى في الأرشيف."""
    import datetime as dt

    from core.models import CustomUser, School
    from operations.services.absence_snapshots import ReportSpec, generate

    school = School.objects.get(pk=school_id)
    user = CustomUser.objects.filter(pk=user_id).first()
    spec = ReportSpec(kind, scope, dt.date.fromisoformat(start), dt.date.fromisoformat(end))
    with school_rls_scope(school.id):
        return generate(school, spec, user=user).revision
