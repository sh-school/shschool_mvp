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
    missing = [name for name, entry in schedule.items() if entry["task"] not in app.tasks]
    assert not missing, f"مهامٌّ مجدولةٌ لا وجودَ لها: {missing}"


def test_data_retention_is_scheduled_weekly_at_dawn():
    """سياسةُ الاحتفاظ (PDPPL م.7 و10) تُنفَّذ أسبوعيّاً فجراً — لا وعدٌ في وثيقة."""
    app.loader.import_default_modules()
    entries = [
        e for e in app.conf.beat_schedule.values() if e["task"] == "core.enforce_data_retention"
    ]
    assert len(entries) == 1, "مهمّةُ الاحتفاظ بالبيانات ليست في الجدول — أو فيه مرّتين"
    when = entries[0]["schedule"]
    assert len(when.day_of_week) == 1, "أسبوعيّاً: يومٌ واحدٌ في الأسبوع"
    assert max(when.hour) <= 5, "فجراً: قبل بداية الدوام"


def test_worker_heartbeat_runs_every_five_minutes_or_less():
    """P4-9: غيابُ النبضة عن Sentry Crons هو الإنذار — فترةٌ أطول تُبطئ الاكتشاف."""
    app.loader.import_default_modules()
    entries = [e for e in app.conf.beat_schedule.values() if e["task"] == "core.worker_heartbeat"]
    assert len(entries) == 1, "لا نبضةَ عاملٍ في الجدول — أو فيها مرّتين"
    when = entries[0]["schedule"]
    minutes = sorted(when.minute)
    gaps = [b - a for a, b in zip(minutes, minutes[1:])] or [60]
    gaps.append(60 - minutes[-1] + minutes[0])
    assert max(gaps) <= 5, "فجوةٌ بين نبضتين أطولُ من خمس دقائق"


def test_sentry_watches_the_scheduled_tasks_in_production_and_staging():
    """بلا `monitor_beat_tasks=True` توقّفُ العامل صامتٌ — لا فائدةَ من نبضةٍ لا يراها أحد."""
    for module in ("production", "staging"):
        source = pathlib.Path(f"shschool/settings/{module}.py").read_text(encoding="utf-8")
        assert "monitor_beat_tasks=True" in source, module
