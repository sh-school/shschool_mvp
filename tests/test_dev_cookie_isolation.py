"""
tests/test_dev_cookie_isolation.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
لا يُخرجك خادمُ جلسةٍ من خادمٍ آخر، ولا تسقط المعاينةُ بترويسةٍ متضخّمة.

خوادمُ الجلسات كلُّها على `localhost`، والمتصفّحُ يُفرز الكوكي بالمضيف لا
بالمنفذ — فكانت تتقاسم `sessionid` و`csrftoken`. وكلُّ خادمٍ يحذف جلسةً لا
يعرفها. قِيس يومَ 2026-09-13:

    طلبٌ إلى 8000 بجلسةٍ من 8011  →  Set-Cookie: sessionid=""; Max-Age=0

فيكفي فتحُ صفحةٍ على منفذٍ ليُخرجك من آخر. وقطع ذلك مسحَ الهاتف مرّتين،
وأنتج سبعَ عمليّاتِ دخولٍ في أربعين دقيقة.

ثمّ تضخّمت الكوكيز: كلُّ شجرةٍ دُخل بها تترك زوجاً من الاسمين الطويلين، فتجاوزت
ترويسةُ Cookie حدَّ nginx (8 كيلوبايت) على 8500 بخطأ 400 (2026-11-14). فالاسمان
صارا قصيرين (`sid_` و`csrf_` وستّةُ أحرفٍ من التجزئة)، ونفحصُ أن واجهةَ nginx
المولَّدة ترفع حدَّ الترويس.

والإعداداتُ تُحمَّل في عمليّةٍ مستقلّة: حزمةُ الاختبار تعمل بـ`testing`، وهذا
عن `development` وحدَه.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PREVIEW_SCRIPT = ROOT / "scripts" / "preview.sh"
# المسارُ المحلولُ لا الاسمُ: على ويندوز يجد `bash` الاسمُ المجرّدُ أوّلاً في System32 (WSL) لا Git Bash.
BASH = shutil.which("bash") or "bash"

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


def test_a_session_tree_server_gets_short_cookie_names_of_its_own():
    session, csrf = _cookie_names("ss_contrast_guard")
    assert session.startswith("sid_") and len(session) == len("sid_") + 6, session
    assert csrf.startswith("csrf_") and len(csrf) == len("csrf_") + 6, csrf


def test_two_session_trees_never_share_a_cookie():
    a = _cookie_names("ss_wings")
    b = _cookie_names("ss_attendance")
    assert set(a).isdisjoint(b), f"شجرتان تتقاسمان كوكياً: {a} و{b}"


def test_session_cookie_names_stay_short_so_a_pile_of_trees_fits_nginx():
    """ترويسةُ Cookie تتراكم بزوجٍ لكلّ شجرة: كلُّ اسمٍ أقصرُ من 20 حرفاً."""
    for db in ("ss_contrast_guard", "ss_wings", "ss_attendance"):
        for name in _cookie_names(db):
            assert len(name) < 20, f"{db}: {name} ({len(name)} حرفاً)"


def test_the_main_stack_keeps_the_default_names():
    """الحزمةُ الأصليّة (`shschool_db`) لا تُمَسّ — ولا الإنتاج."""
    assert _cookie_names("shschool_db") == ("sessionid", "csrftoken")


@pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash في هذه البيئة")
def test_front_conf_raises_the_request_header_buffer_limit(tmp_path: Path):
    """واجهةُ nginx المولَّدة تحمل حدَّ ترويسٍ أوسعَ من الافتراضيّ (8k) لتتّسع الكوكيز المتراكمة."""
    # مجلّدُ الحالة مؤقّت، وhost.docker.internal ثابتٌ بدل استعلام docker.
    program = (
        f'source "{PREVIEW_SCRIPT.as_posix()}"\n'
        f'STATE_DIR="{tmp_path.as_posix()}"\n'
        "front_host_v4() { printf '%s' host.docker.internal; }\n"
        "front_conf 8500\n"
    )
    env = {**os.environ, "PREVIEW_DIR": str(tmp_path), "SCHOOLOS_ROOT": str(tmp_path)}
    subprocess.run(
        [BASH, "-c", program], env=env, capture_output=True, text=True, check=True, timeout=60
    )

    conf = (tmp_path / "front" / "default.conf").read_text(encoding="utf-8")
    assert "large_client_header_buffers 4 32k;" in conf, conf
    assert "proxy_pass http://host.docker.internal:8500;" in conf, conf
