"""مهامُّ Celery العامّة للمنصّة — ما ليس لوحدةٍ بعينها.

* `core.enforce_data_retention` انتقل تنفيذُه إلى `governance/tasks.py` (باسمه نفسه).
* `core.worker_heartbeat` — نبضةُ حياة العامل كلَّ خمس دقائق (P4-9)، ولا شيءَ
  آخر: `CeleryIntegration(monitor_beat_tasks=True)` (production.py، staging.py)
  يرسل فحصَ Sentry Crons تلقائيّاً لكلّ مهمّةٍ مجدولة — فغيابُها هو الإنذار،
  ولا حاجةَ لاستدعاءِ Sentry هنا.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(name="core.worker_heartbeat", ignore_result=True)
def worker_heartbeat() -> None:
    """نبضةٌ لا تفعل شيئاً غير النجاح.

    أيّ عملٍ حقيقيّ هنا يُخفي توقّفَ العامل خلف فشل ذلك العمل بالذات — والغرضُ
    توقّفَ العاملِ نفسَه، لا توقّفَ مهمّةٍ بعينها.
    """
    return None
