"""جدولةُ تقارير الغياب الدوريّة — وحدةٌ بلا استيراد Django عمداً (كـ`notifications/teacher_alerts_beat.py`).

`shschool/celery.py` يُستورد قبل تحميل التطبيقات، فلا يجوز أن يجرّ استيراداً للنماذج. المهمّةُ في `absence_reports_tasks.py`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from celery.schedules import crontab


def absence_reports_beat(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """مدخلُ `beat_schedule` — فارغٌ ما لم يكن `ABSENCE_REPORTS_BEAT=1`.

    عند الدقيقة ٤٠ من كلّ ساعةٍ بين 09:00 و19:00 بتوقيت الدوحة، الأحد–الخميس (`0-4`: الأحدُ صفر)؛ فيلتقط اليوميُّ
    والأسبوعيُّ والشهريُّ والربعُ سنويُّ ما استحقّ من أوّل ساعةٍ بعد استحقاقه.
    """
    env = environ if environ is not None else os.environ
    if env.get("ABSENCE_REPORTS_BEAT", "") != "1":
        return {}
    return {
        "generate-due-absence-reports": {
            "task": "operations.generate_due_absence_reports",
            "schedule": crontab(minute=40, hour="9-19", day_of_week="0-4"),
        }
    }
