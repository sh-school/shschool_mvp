"""جدولةُ تصعيد بطاقات الخروج التي لم تُستلَم — وحدةٌ بلا استيراد Django عمداً (كـ`operations/absence_reports_beat.py`).

`shschool/celery.py` يُستورد قبل تحميل التطبيقات، فلا يجوز أن يجرّ استيراداً للنماذج. المهمّةُ في `operations/tasks.py`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def exit_card_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلُ `beat_schedule` — فارغٌ ما لم يكن `EXIT_CARD_BEAT=1` (وبعد إعادة نشر beat بأمر المالك).

    كلَّ دقيقةٍ في ساعات الدوام بتوقيت الدوحة (07–15)، الأحد–الخميس (`0-4`: الأحدُ صفر)؛ والمهمّةُ ثابتةُ التكرار.
    """
    env = environ if environ is not None else os.environ
    if env.get("EXIT_CARD_BEAT", "") != "1":
        return {}
    return {
        "escalate-unreceived-exit-cards": {
            "task": "operations.escalate_unreceived_exit_cards",
            "schedule": crontab(minute="*", hour="7-15", day_of_week="0-4"),
        },
        "alert-clinic-returns": {
            "task": "operations.alert_clinic_returns",
            "schedule": crontab(minute="*", hour="7-15", day_of_week="0-4"),
        },
    }
