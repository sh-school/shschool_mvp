"""[SENTRY] مراقبُ Cron واحد — النبضةُ وحدها — لتتّسع له حصّةُ الخطّة المجّانيّة.

`monitor_beat_tasks=True` تُنشئ مراقباً لكلّ مدخلٍ في `beat_schedule` (11 يومَ
2026-09-19)، والخطّةُ المجّانيّة تتّسع لواحد؛ فأعلنت لوحةُ Sentry «Usage Exceeded»
وحذّرت من فقد بيانات المراقبة. فيُستثنى كلُّ مدخلٍ عدا النبضة.
"""

from sentry_sdk.utils import match_regex_list

from core.sentry_config import SENTRY_EXCLUDE_BEAT_TASKS, SENTRY_MONITORED_BEAT_TASKS
from shschool.celery import app


def _excluded(name: str) -> bool:
    return bool(match_regex_list(name, SENTRY_EXCLUDE_BEAT_TASKS))


def test_every_monitored_task_is_a_real_beat_entry():
    """تسميةٌ تتقادم صامتةً: لو أُعيدت تسمية المدخل انقطعت المراقبةُ بلا إنذار."""
    entries = set(app.conf.beat_schedule)
    assert set(SENTRY_MONITORED_BEAT_TASKS) <= entries


def test_only_the_heartbeat_is_monitored():
    monitored = [name for name in app.conf.beat_schedule if not _excluded(name)]
    assert monitored == list(SENTRY_MONITORED_BEAT_TASKS)


def test_a_new_beat_entry_is_excluded_by_default():
    """مدخلٌ جديدٌ لا يستهلك الحصّةَ ما لم يُدرَج صراحةً في القائمة."""
    assert _excluded("some-future-task")
    assert _excluded("worker-heartbeat-2")
