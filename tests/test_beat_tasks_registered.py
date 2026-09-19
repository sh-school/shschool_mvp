"""كلُّ مهمّةٍ في جدول Beat مسجَّلةٌ فعلاً — فنقلُ تنفيذٍ بين التطبيقات لا يُسقط جدولةً بصمت.

انتقلت `core.enforce_data_retention` من `core` إلى `governance` (ADR-0004) وبقي اسمُها؛
ولو انتقلت مهمّةٌ أخرى بلا اسمٍ صريحٍ لصار اسمُها الافتراضيُّ مساراً جديداً، فيبقى Beat
يُرسل اسماً لا عاملَ له ولا يظهر ذلك في أيّ اختبارٍ ولا سجلّ.
"""

from __future__ import annotations

from shschool.celery import app


def test_every_beat_task_is_registered():
    app.loader.import_default_modules()
    scheduled = {entry["task"] for entry in app.conf.beat_schedule.values()}

    assert scheduled - set(app.tasks) == set()


def test_the_retention_task_kept_its_public_name():
    app.loader.import_default_modules()

    assert "core.enforce_data_retention" in app.tasks
