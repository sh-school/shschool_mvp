"""مهامُّ Celery العامّة للمنصّة — ما ليس لوحدةٍ بعينها.

* `core.enforce_data_retention` انتقل تنفيذُه إلى `governance/tasks.py` (باسمه نفسه).
* `core.worker_heartbeat` — نبضةُ حياة العامل كلَّ خمس دقائق (P4-9).
  `CeleryIntegration(monitor_beat_tasks=True)` (production.py، staging.py) يرسل فحصَ
  Sentry Crons تلقائيّاً — لكنّ خطّة Sentry المجّانيّة مقعدُها واحدٌ فلا يُعتمد عليه
  وحدَه. فتُختَم النبضةُ أيضاً في Redis (`core/worker_heartbeat.py`) ويفحصها
  `/health/worker/` من GitHub Actions.
"""

from __future__ import annotations

from celery import shared_task

from core import worker_heartbeat as heartbeat


@shared_task(name="core.worker_heartbeat", ignore_result=True)
def worker_heartbeat() -> None:
    """يختم النبضةَ في Redis ولا شيءَ غيرَه.

    فشلُ الختم يُسقط المهمّةَ فيظهر في السجلّ وSentry، وغيابُ الختم يُنذَر به من
    الخارج على أيّ حال — فلا يُخفي عملٌ آخرُ هنا توقّفَ العامل.
    """
    heartbeat.record()
