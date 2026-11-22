"""جدولةُ إلغاء طلبات التبديل المنتهية (W-20261123-002) — وحدةٌ بلا استيراد Django عمداً (كـ`clinic/autoclose_beat.py`).

`shschool/celery.py` يُستورد قبل تحميل التطبيقات، فلا يجوز أن يجرّ استيراداً للنماذج. المهمّةُ في `swap_tasks.py`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def swap_expiry_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلُ `beat_schedule` — فارغٌ ما لم يكن `SWAP_EXPIRY_BEAT=1`؛ كلَّ ربعِ ساعةٍ 6-15، الأحد–الخميس."""
    env = environ if environ is not None else os.environ
    if env.get("SWAP_EXPIRY_BEAT", "") != "1":
        return {}
    return {
        "operations-expire-stale-swaps": {
            "task": "operations.expire_stale_swaps",
            "schedule": crontab(minute="*/15", hour="6-15", day_of_week="0-4"),
        }
    }
