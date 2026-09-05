"""
conftest.py (root)
━━━━━━━━━━━━━━━━━━
يُخبر pytest بتجاهل مجلدات لا تحتوي على اختبارات pytest، ويحرس بيئةَ التشغيل.
"""

import os

import pytest

# ✅ v5.4: Locust (loadtest) و Playwright (e2e) يحتاجان مكتبات خاصة
# غير مثبّتة في بيئة الاختبار العادية — نستثنيها من الجمع
collect_ignore_glob = [
    "tests/loadtest/**",
    "tests/e2e/**",
]

#: إعداداتُ الاختبار كما يعرفها CI — وهي ما في pytest.ini.
_TESTING_SETTINGS = "shschool.settings.testing"


def pytest_sessionstart(session):
    """اختبارٌ يخضرّ كاذباً أسوأُ من اختبارٍ يحمرّ.

    داخل حاوية التطوير يكون `DJANGO_SETTINGS_MODULE=…development` في البيئة،
    والبيئةُ تتغلّب على pytest.ini. وإعداداتُ التطوير تجعل Celery غيرَ فوريّ
    حين يوجد Redis — فمهمّةُ توليد الجدول تذهب إلى العامل الحقيقيّ خارج معاملة
    الاختبار، ويرى الاختبارُ «queued» ويسقط، بينما CI أخضر. وأخطرُ منه العكس:
    اختبارٌ يمرّ محلّياً لأنّ العامل أنجز شيئاً لم يُقَس.

    فإن لم يكن Celery فوريّاً أُوقف التشغيلُ ببيانٍ لا بتخمين. والطريقُ الصحيح:
    `make test-docker`.
    """
    from django.conf import settings

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return

    module = os.environ.get("DJANGO_SETTINGS_MODULE", "?")
    pytest.exit(
        f"\nأُوقف: Celery غيرُ فوريّ تحت {module} — مهامُّ الخلفيّة ستُنفَّذ خارج "
        f"معاملة الاختبار فتكذب النتائج.\n"
        f"شغّل الاختبارات كما يفعل CI: `make test-docker` أو `.\\scripts\\test-docker.ps1` "
        f"(أو DJANGO_SETTINGS_MODULE={_TESTING_SETTINGS} مع TEST_DB_HOST=db).\n",
        returncode=3,
    )
