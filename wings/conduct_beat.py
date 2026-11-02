"""جدولةُ توليد اقتراحات المخالفة — وحدةٌ بلا استيراد Django عمداً (كـ`operations/absence_reports_beat.py`)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def conduct_proposals_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلُ `beat_schedule` — فارغٌ ما لم يكن `CONDUCT_PROPOSALS_BEAT=1` (بأمر المالك بعد إعادة نشر beat).

    الساعة 15:10 بتوقيت الدوحة، الأحد–الخميس، بعد إغلاق الرصد؛ والتشغيلُ ثابتُ التكرار.
    """
    env = environ if environ is not None else os.environ
    if env.get("CONDUCT_PROPOSALS_BEAT", "") != "1":
        return {}
    return {
        "generate-conduct-proposals": {
            "task": "wings.generate_conduct_proposals",
            "schedule": crontab(minute=10, hour=15, day_of_week="0-4"),
        }
    }
