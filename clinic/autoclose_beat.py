"""جدولةُ الإغلاق التلقائيّ لزيارات العيادة — وحدةٌ بلا استيراد Django عمداً (كـ`notifications/teacher_alerts_beat.py`).

`shschool/celery.py` يُستورد قبل تحميل التطبيقات، فلا يجوز أن يجرّ استيراداً للنماذج. المهمّةُ في `tasks.py`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def clinic_autoclose_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلُ `beat_schedule` — فارغٌ ما لم يكن `CLINIC_AUTOCLOSE_BEAT=1`؛ كلَّ ربعِ ساعةٍ في ساعات الدوام، الأحد–الخميس."""
    env = environ if environ is not None else os.environ
    if env.get("CLINIC_AUTOCLOSE_BEAT", "") != "1":
        return {}
    return {
        "clinic-auto-close-stale-visits": {
            "task": "clinic.auto_close_stale_visits",
            "schedule": crontab(minute="*/15", hour="7-16", day_of_week="0-4"),
        }
    }
