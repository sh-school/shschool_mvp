"""[BACKUP] حارسُ `auto_backup.ps1`: تحذيرُ git برمز خروج 0 لا يُعدّ فشلاً، ورمزٌ غيرُ صفرٍ يفشل مسموعاً (W-20261002-010).

عدّ السكربتُ تحذيرَ «LF will be replaced by CRLF» (stderr برمز 0) فشلاً ثلاث ليالٍ (09-29..10-01)؛ أُصلحت `Git-Run` في 10-02 بلا اختبار.
السكربتُ خارج المستودع (`~/.claude/scripts/`) ويثبّت `$ClaudeRoot` من `$env:USERPROFILE`، فيُشغَّل هنا بـ`USERPROFILE` مؤقّتٍ فيه
`.claude` مستودعُ git على فرع `scoped` — **لا يلمس نسخةَ الذاكرة الحقيقيّة ولا `BACKUP_FAILED.txt` الحقيقيّ**.

اختبارٌ محلّيٌّ للمضيف (ويندوز + PowerShell + السكربت): يُتخطّى في CI لغيابها. تشغيلُه بسطرٍ واحد:

    python -m pytest tests/test_auto_backup_git_warning.py -q -p no:cacheprovider

والنسخةُ القديمة `auto_backup.ps1.bak_2026-10-02` (قبل الإصلاح) إن وُجدت تُثبت أنّ الاختبار يسقط بلا الإصلاح (إعادةُ التعطيل).
المقبضُ `Global\\ClaudeBackupMutex` مشتركٌ مع النسخ الحقيقيّ: إن كان يعمل وقتَ الاختبار تخطّى السكربتُ (رمز 0 بلا حالة) فيُتخطّى الاختبار.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path.home() / ".claude" / "scripts"
CURRENT = SCRIPTS / "auto_backup.ps1"
BEFORE_FIX = SCRIPTS / "auto_backup.ps1.bak_2026-10-02"
POWERSHELL = shutil.which("powershell")

pytestmark = pytest.mark.skipif(
    POWERSHELL is None or not CURRENT.exists() or shutil.which("git") is None,
    reason="يلزم ويندوز وPowerShell وgit وسكربتُ النسخ في ~/.claude/scripts (اختبارٌ محلّيٌّ للمضيف)",
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    """USERPROFILE مؤقّت: `.claude` مستودعٌ على الفرع scoped بإيداعٍ أوّل، وautocrlf يُصدر التحذيرَ عند add."""
    claude = tmp_path / "home" / ".claude"
    claude.mkdir(parents=True)
    _git(claude, "init", "-q", "-b", "scoped")
    for key, value in (
        ("user.email", "t@test.local"),
        ("user.name", "t"),
        ("core.autocrlf", "true"),
        ("core.safecrlf", "warn"),
    ):
        _git(claude, "config", key, value)
    (claude / "seed.txt").write_bytes(b"seed\r\n")
    _git(claude, "add", "seed.txt")
    _git(claude, "commit", "-q", "-m", "seed")
    return tmp_path / "home"


def _run(script: Path, home: Path) -> tuple[int, dict | None, Path]:
    env = {**os.environ, "USERPROFILE": str(home)}
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    backups = home / ".claude" / "backups"
    status_file = backups / "LAST_STATUS.json"
    status = (
        json.loads(status_file.read_text(encoding="utf-8-sig")) if status_file.exists() else None
    )
    return done.returncode, status, backups / "BACKUP_FAILED.txt"


def _write_lf_file(home: Path) -> None:
    # ملفٌّ جديدٌ بنهايات LF: git add يحذّر «LF will be replaced by CRLF» برمز 0
    (home / ".claude" / "memory.md").write_bytes(b"line one\nline two\n")


def _skip_if_real_backup_held_the_mutex(status: dict | None, code: int) -> None:
    if status is None and code == 0:
        pytest.skip("نسخٌ حقيقيٌّ يعمل الآن ويمسك المقبض — أعد التشغيل")


def test_a_git_warning_with_exit_code_zero_is_not_a_failure(fake_home: Path):
    _write_lf_file(fake_home)
    code, status, fail_file = _run(CURRENT, fake_home)
    _skip_if_real_backup_held_the_mutex(status, code)
    assert code == 0, status
    assert status is not None and status["ok"] is True and status["commit"]
    assert not fail_file.exists()


def test_a_nonzero_git_exit_fails_loudly(fake_home: Path):
    _write_lf_file(fake_home)
    _git(fake_home / ".claude", "remote", "add", "origin", str(fake_home / "no-such-remote.git"))
    code, status, fail_file = _run(CURRENT, fake_home)
    _skip_if_real_backup_held_the_mutex(status, code)
    assert code == 1
    assert status is not None and status["ok"] is False and "رمز" in status["error"]
    assert fail_file.exists() and "فشل نسخُ" in fail_file.read_text(encoding="utf-8-sig")


@pytest.mark.skipif(not BEFORE_FIX.exists(), reason="نسخةُ ما قبل الإصلاح غائبة")
def test_the_old_script_fails_the_warning_case_so_the_test_catches_a_regression(
    fake_home: Path, tmp_path: Path
):
    _write_lf_file(fake_home)
    old = tmp_path / "auto_backup_before_fix.ps1"  # PowerShell يرفض -File بلا امتداد ps1
    shutil.copyfile(BEFORE_FIX, old)
    code, status, fail_file = _run(old, fake_home)
    _skip_if_real_backup_held_the_mutex(status, code)
    assert code == 1 and status is not None and status["ok"] is False
    assert fail_file.exists()
