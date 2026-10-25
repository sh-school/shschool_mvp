"""جدولةُ تنبيه صلاحية مستلزمات العيادة (W-20261020-040) — وحدةٌ بلا استيراد Django عمداً (كـ`autoclose_beat.py`)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def clinic_supply_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلُ `beat_schedule` — فارغٌ ما لم يكن `CLINIC_SUPPLY_BEAT=1`؛ مرّةً صباحاً (07:30) الأحد–الخميس."""
    env = environ if environ is not None else os.environ
    if env.get("CLINIC_SUPPLY_BEAT", "") != "1":
        return {}
    return {
        "clinic-alert-supply-expiry": {
            "task": "clinic.alert_supply_expiry",
            "schedule": crontab(minute="30", hour="7", day_of_week="0-4"),
        }
    }
