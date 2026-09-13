"""لكلّ مهمّةٍ مجدولةٍ خدمةٌ تُرسلها — وإلّا فالجدولُ وعدٌ لا يُنفَّذ.

`shschool/celery.py` يعرّف خمسَ مهامّ (تنبيهاتُ الغياب صباحاً، مهلُ الخروقات كلَّ ساعة،
إلغاءُ الصلاحيّات المؤقّتة كلَّ دقيقة، تقريرُ KPI الشهريّ، فحصُ الخطر السلوكيّ)، ولم
تكن على Railway إلّا خدمتان: الويب والعامل — ولا أحدَ يرسل. فلم يعمل شيءٌ من ذلك في
الإنتاج قطّ، ولا اختبارَ لاحظ (سواط 2026-09-14).
"""

import pathlib
import re

from shschool.celery import app

IAC = pathlib.Path(".railway/railway.ts")
SCRIPT = pathlib.Path("scripts/railway-beat.sh")


def test_the_iac_declares_a_beat_service_that_runs_the_beat_script():
    text = IAC.read_text(encoding="utf-8")
    beat = re.search(r'service\("celery-beat",\s*\{(.*?)\}\);', text, re.S)
    assert beat, "لا خدمةَ `celery-beat` في railway.ts — الجدولُ بلا مُرسِل"
    assert 'start: "bash scripts/railway-beat.sh"' in beat.group(1)
    assert re.search(r"resources:\s*\[[^\]]*\bbeat\b", text), "الخدمةُ معرَّفةٌ ولا تدخل المشروع"


def test_the_beat_script_starts_beat_and_refuses_to_run_blind():
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"celery -A shschool beat", text)
    for guard in ("REDIS_URL", "CELERY_ASYNC_ENABLED", "APP_DB_PASSWORD"):
        assert guard in text, f"السكربتُ لا يتحقّق من {guard}"
    assert "unset DATABASE_URL" in text, "Beat يجب ألّا يسقط إلى دور المالك"


def test_every_scheduled_task_exists_and_the_schedule_is_not_empty():
    app.loader.import_default_modules()
    schedule = app.conf.beat_schedule
    assert len(schedule) >= 5
    missing = [
        name for name, entry in schedule.items() if entry["task"] not in app.tasks
    ]
    assert not missing, f"مهامٌّ مجدولةٌ لا وجودَ لها: {missing}"
