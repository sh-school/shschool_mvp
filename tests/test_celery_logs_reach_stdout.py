"""سجلّاتُ العامل وBeat تصل stdout في الإنتاج — مستورةً.

كان `railway logs` على العامل يُظهر اللافتةَ ثمّ صمتاً: لا `Task … received`
ولا `succeeded`، وعلى Beat لا `Scheduler: Sending due task`. و`production.py`
يوجّه `celery` إلى `console` بمستوى INFO، فالإعدادُ يبدو سليماً — والعطبُ في
ما يفعله Celery **بعد** الإعداد: يُفرغ معالِجاتِ `celery` (اختطافُ الجذر)،
و`propagate: False` يمنع الصعودَ، فتسقط سطورُ INFO في الفراغ.

وهذا الاختبارُ يُعيد ما يقع عند البدء حرفيّاً في عمليّةٍ فرعيّة بإعدادات
الإنتاج: `django.setup()` ثمّ `app.log.setup()` — ما يستدعيه العاملُ وBeat —
ثمّ يسجّل على المسجِّلات الأربعة التي تحمل دورةَ حياة المهامّ، ويقرأ stdout.
والرقمُ المزروعُ في الرسالة يجب أن يخرج مستوراً: الإصلاحُ لا يفتح باباً كان
فلترُ `pii_masking` يغلقه.
"""

import os
import subprocess
import sys
from pathlib import Path

from tests.test_production_runtime_settings import _REQUIRED_ENV

PLANTED_ID = "99900000001"
MASKED_ID = "999*****01"

#: (المسجِّل، الرسالة) — ما يكتبه Celery نفسُه عند استلام مهمّةٍ وإنهائها وإرسالها.
LIFECYCLE = (
    ("celery.worker.strategy", "Task operations.revoke_expired_temp_permissions[abc] received"),
    ("celery.app.trace", "Task operations.revoke_expired_temp_permissions[abc] succeeded in 0.1s"),
    ("celery.beat", "Scheduler: Sending due task revoke-expired-temp-permissions"),
    ("celery.task", f"task logger sees {PLANTED_ID}"),
)

_PROBE = f"""
import logging, sys
import django
django.setup()
from shschool.celery import app
app.log.setup(loglevel=logging.INFO, logfile=None)
for name, message in {LIFECYCLE!r}:
    logging.getLogger(name).info(message)
for handler in logging.getLogger().handlers:
    handler.flush()
sys.stdout.flush()
"""


def _run_probe():
    env = os.environ.copy()
    for key in ("REDIS_URL", "CELERY_ASYNC_ENABLED", "USE_REDIS_SESSIONS"):
        env.pop(key, None)
    env.update(_REQUIRED_ENV)
    env["DJANGO_SETTINGS_MODULE"] = "shschool.settings.production"
    return subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_celery_lifecycle_lines_reach_stdout_masked():
    result = _run_probe()
    assert result.returncode == 0, result.stderr

    for _name, message in LIFECYCLE[:3]:
        assert message in result.stdout, (
            f"سطرٌ من دورة حياة المهامّ لم يبلغ stdout: «{message}»\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
    assert MASKED_ID in result.stdout, "سطرُ مسجِّل المهمّة لم يصل — أو وصل بلا ستر"
    assert (
        PLANTED_ID not in result.stdout + result.stderr
    ), "الرقمُ خرج كاملاً — فلتر pii_masking غائب"


def test_the_receiver_is_what_stops_celery_from_hijacking():
    """الآليّةُ لا الصدفة: مستقبِلُ `setup_logging` موصولٌ في تطبيق Celery نفسِه."""
    import weakref

    from celery.signals import setup_logging

    from shschool import celery as celery_module

    receivers = [
        receiver() if isinstance(receiver, weakref.ReferenceType) else receiver
        for _key, receiver in setup_logging.receivers
    ]
    assert celery_module._log_through_django in receivers
