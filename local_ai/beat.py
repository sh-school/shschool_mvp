"""جدولُ Beat للذكاء المحلّيّ — وحدةٌ خفيفة لا تستورد النماذج.

يُستورَد من `shschool/celery.py` أثناء إقلاع Django قبل جاهزية التطبيقات، فلا يجوز أن يمرّ على `models`.
"""

from __future__ import annotations

from typing import Any

from celery.schedules import crontab


def local_ai_beat() -> dict[str, dict[str, Any]]:
    """جدولُ Beat للتطبيق — يُدمج في `shschool/celery.py` كبقيّة الوحدات."""
    return {
        # كلَّ ساعةٍ في الدقيقة 20: ما رُفع والخادمُ مطفأ يُفهرَس حين يعود، دون انتظار الليل.
        "local-ai-index-pending-hourly": {
            "task": "local_ai.index_pending_documents",
            "schedule": crontab(minute=20),
            "kwargs": {"include_failed": False},
        },
        # ليلاً 02:40: إعادةُ محاولة ما فشل (خادمٌ مطفأ، نموذجٌ غيرُ محمَّل) خارج الدوام.
        "local-ai-retry-failed-nightly": {
            "task": "local_ai.index_pending_documents",
            "schedule": crontab(hour=2, minute=40),
            "kwargs": {"include_failed": True},
        },
    }
