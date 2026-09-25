"""مهامُّ Celery العامّة للمنصّة — ما ليس لوحدةٍ بعينها.

* `core.enforce_data_retention` انتقل تنفيذُه إلى `governance/tasks.py` (باسمه نفسه).
* `core.worker_heartbeat` — نبضةُ حياة العامل كلَّ خمس دقائق (P4-9).
  `CeleryIntegration(monitor_beat_tasks=True)` (production.py، staging.py) يرسل فحصَ
  Sentry Crons تلقائيّاً — لكنّ خطّة Sentry المجّانيّة مقعدُها واحدٌ فلا يُعتمد عليه
  وحدَه. فتُختَم النبضةُ أيضاً في Redis (`core/worker_heartbeat.py`) ويفحصها
  `/health/worker/` من GitHub Actions.
* `core.refresh_backup_status` — حالةُ النسخ الاحتياطيّ اليوميّ (GitHub Actions) إلى الـcache كلَّ نصف ساعة
  لبطاقة «النسخ الاحتياطيّ» في الإدارة (OWN-23) — راجع `core/backup_status.py`.
"""

from __future__ import annotations

from celery import shared_task

from core import backup_status
from core import worker_heartbeat as heartbeat


@shared_task(name="core.worker_heartbeat", ignore_result=True)
def worker_heartbeat() -> None:
    """يختم النبضةَ في Redis ولا شيءَ غيرَه.

    فشلُ الختم يُسقط المهمّةَ فيظهر في السجلّ وSentry، وغيابُ الختم يُنذَر به من
    الخارج على أيّ حال — فلا يُخفي عملٌ آخرُ هنا توقّفَ العامل.
    """
    heartbeat.record()


@shared_task(name="core.refresh_backup_status", ignore_result=True)
def refresh_backup_status() -> None:
    """يجلب حالةَ آخر نسخٍ احتياطيّ من واجهة GitHub العامّة إلى الـcache.

    عطلُ الجلب (انقطاعٌ أو حدُّ الطلبات) لا يُسقط المهمّة: تبقى آخرُ حالةٍ معروفةٍ وتُوسَم «قديمة» في البطاقة،
    وهي التي تُنذر — لا فشلُ مهمّةٍ خلفيّةٍ ثانويّة.
    """
    backup_status.refresh()
