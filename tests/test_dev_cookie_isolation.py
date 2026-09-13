"""
tests/test_dev_cookie_isolation.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
لا يُخرجك خادمُ جلسةٍ من خادمٍ آخر.

خوادمُ الجلسات كلُّها على `localhost`، والمتصفّحُ يُفرز الكوكي بالمضيف لا
بالمنفذ — فكانت تتقاسم `sessionid` و`csrftoken`. وكلُّ خادمٍ يحذف جلسةً لا
يعرفها. قِيس يومَ 2026-09-13:

    طلبٌ إلى 8000 بجلسةٍ من 8011  →  Set-Cookie: sessionid=""; Max-Age=0

فيكفي فتحُ صفحةٍ على منفذٍ ليُخرجك من آخر. وقطع ذلك مسحَ الهاتف مرّتين،
وأنتج سبعَ عمليّاتِ دخولٍ في أربعين دقيقة.

والإعداداتُ تُحمَّل في عمليّةٍ مستقلّة: حزمةُ الاختبار تعمل بـ`testing`، وهذا
عن `development` وحدَه.
"""

import json
import os
import subprocess
import sys

PROBE = (
    "import json, django;"
    "from django.conf import settings;"
    "print(json.dumps([settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME]))"
)


def _cookie_names(db_name: str) -> tuple[str, str]:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "shschool.settings.development",
        "DB_NAME": db_name,
    }
    env.setdefault("SECRET_KEY", "test-only-not-a-secret-0123456789abcdef")
    out = (
        subprocess.run(
            [sys.executable, "-c", PROBE],
            capture_output=True,
            text=True,
            env=env,
            check=True,
            timeout=120,
        )
        .stdout.strip()
        .splitlines()[-1]
    )
    session, csrf = json.loads(out)
    return session, csrf


def test_a_session_tree_server_gets_cookie_names_of_its_own():
    session, csrf = _cookie_names("ss_contrast_guard")
    assert session == "sessionid_ss_contrast_guard", session
    assert csrf == "csrftoken_ss_contrast_guard", csrf


def test_two_session_trees_never_share_a_cookie():
    a = _cookie_names("ss_wings")
    b = _cookie_names("ss_attendance")
    assert set(a).isdisjoint(b), f"شجرتان تتقاسمان كوكياً: {a} و{b}"


def test_the_main_stack_keeps_the_default_names():
    """الحزمةُ الأصليّة (`shschool_db`) لا تُمَسّ — ولا الإنتاج."""
    assert _cookie_names("shschool_db") == ("sessionid", "csrftoken")
