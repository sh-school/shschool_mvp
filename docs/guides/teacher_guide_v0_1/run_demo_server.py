"""خادمُ تصوير «دليل المعلّم»: ساعتُه مثبَّتةٌ على الإثنين 2026-10-05 الساعة 09:20 بتوقيت الدوحة.

الحصّةُ لا يُرصَد فيها إلّا ضمن نافذتها، فتصويرُها بعد الدوام يُظهر «الإدخالُ مغلق». والتثبيتُ على ساعة الدرس يُريك الشاشةَ كما يراها المعلّم أثناء عمله.
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")

from django.utils import timezone  # noqa: E402

_FIXED = timezone.make_aware(dt.datetime(2026, 10, 5, 9, 20, 0))
_START = dt.datetime.now(dt.UTC)


def _now():
    return _FIXED + (dt.datetime.now(dt.UTC) - _START)


timezone.now = _now

from django.core.management import execute_from_command_line  # noqa: E402

execute_from_command_line(
    [
        "manage.py",
        "runserver",
        "--noreload",
        "--nothreading",
        sys.argv[1] if len(sys.argv) > 1 else "8765",
    ]
)
