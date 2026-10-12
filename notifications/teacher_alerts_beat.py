"""جدولةُ تنبيهَي المعلّم (W-20261010-042) — وحدةٌ بلا استيراد Django عمداً.

`shschool/celery.py` يُستورد عند إقلاع Django قبل تحميل التطبيقات، فلا يجوز أن يجرّ استيراداً للنماذج.
المهمّتان نفسُهما في `notifications/teacher_alerts.py`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def teacher_alerts_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلا `beat_schedule` — فارغٌ ما لم يكن `TEACHER_ALERTS_BEAT=1` (على نمط `ATTENDANCE_SWEEP_BEAT`).

    كلَّ خمس دقائق من 07:00 إلى 14:59 بتوقيت الدوحة، الأحد–الخميس (`0-4` في Celery: الأحدُ صفر).
    """
    env = environ if environ is not None else os.environ
    if env.get("TEACHER_ALERTS_BEAT", "") != "1":
        return {}
    when = crontab(minute="*/5", hour="7-14", day_of_week="0-4")
    return {
        "alert-teachers-unreturned-exits": {
            "task": "notifications.alert_teachers_unreturned_exits",
            "schedule": when,
        },
        "alert-teachers-unmarked-sessions": {
            "task": "notifications.alert_teachers_unmarked_sessions",
            "schedule": when,
        },
    }
