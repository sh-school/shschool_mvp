"""[CI] إعداداتُ Claude المحلّيّة خارج التتبّع (REP-11): `.claude/settings.local.json` لا يُودَع.

كان الملفُّ متتبَّعاً وغيرَ متجاهَل، وكلُّ موافقةٍ «اسمح دائماً» في أيّ جلسةٍ تكتب فيه — فيبقى تعديلاً عالقاً في كلّ شجرةٍ، ويرفض `git merge origin/main`
أن يمرّ عليه، ويُنشر في مستودعٍ عامّ ما وافق عليه مستخدمٌ واحدٌ في جلسةٍ واحدة. والإعدادُ المشترك (`.claude/settings.json`: الـhooks) يبقى متتبَّعاً وغيرَ متجاهَل
— فالحارسُ الذي يقوم عليه لا يصل الجلساتِ بغير ذلك. الاختباراتُ تحتاج `git` فتُتخطّى بدونه.
"""

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCAL = ".claude/settings.local.json"
SHARED = ".claude/settings.json"

pytestmark = pytest.mark.skipif(
    not shutil.which("git") or not (ROOT / ".git").exists(), reason="يحتاج git ومستودعاً"
)


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False
    )


def test_the_local_settings_file_is_not_tracked():
    assert _git("ls-files", "--", LOCAL).stdout.strip() == ""


def test_the_local_settings_file_is_ignored():
    assert _git("check-ignore", "-q", LOCAL).returncode == 0


def test_the_shared_settings_file_stays_tracked_and_is_not_ignored():
    assert _git("ls-files", "--", SHARED).stdout.strip() == SHARED
    assert _git("check-ignore", "-q", SHARED).returncode == 1
