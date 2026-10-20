"""[RAILWAY] إقلاعُ الويب يتحقّق من دور قاعدة البيانات قبل `exec daphne` — fail-closed (W-20261004-007، توصية 0105).

بلا هذا التحقّق يعمل daphne بصمتٍ بدورٍ غير آمن (superuser أو bypassrls) فيُتجاوَز عزلُ المدارس RLS. و`railway-worker.sh` يفعل ذلك
للعامل؛ وهذا الحارسُ يجعل الويبَ مثلَه، بتشغيل السكربت فعلاً مع `python` و`daphne` مزيَّفَين: دورٌ مطابقٌ يُقلع، ومختلفٌ يُنهي
الإقلاعَ برمزٍ غير صفريّ ولا يصل إلى daphne أبداً، وبمتغيّرات daphne نفسها (دور shschool_app بلا DATABASE_URL).
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "railway-release.sh"
BASH = shutil.which("bash")
APP_PASSWORD = "s3cret-app"  # pragma: allowlist secret

pytestmark = pytest.mark.skipif(BASH is None, reason="يلزم bash")

FAKE_PYTHON = """#!/bin/sh
echo "python $*" >> "$TRACE"
case "$*" in
  *verify_runtime_db_role*)
    echo "VERIFY DB_USER=${DB_USER:-} DB_PASSWORD=${DB_PASSWORD:-} DATABASE_URL=${DATABASE_URL:-unset}" >> "$TRACE"
    exit "${FAKE_VERIFY_RC:-0}" ;;
esac
exit 0
"""
FAKE_DAPHNE = """#!/bin/sh
echo "DAPHNE_STARTED DB_USER=${DB_USER:-} DATABASE_URL=${DATABASE_URL:-unset}" >> "$TRACE"
exit 0
"""


def _run(tmp_path: Path, *, verify_rc: int = 0, env_extra: dict | None = None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("python", FAKE_PYTHON), ("daphne", FAKE_DAPHNE)):
        f = bin_dir / name
        f.write_text(body, encoding="utf-8", newline="\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    trace = tmp_path / "trace.log"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TRACE": str(trace),
        "FAKE_VERIFY_RC": str(verify_rc),
        "DJANGO_SETTINGS_MODULE": "shschool.settings.production",
        "APP_DB_PASSWORD": APP_PASSWORD,
        "DATABASE_URL": "postgres://owner:owner@db/shschool",
        **(env_extra or {}),
    }
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc, (trace.read_text(encoding="utf-8") if trace.exists() else "")


def test_a_matching_role_boots_daphne_after_the_verification(tmp_path):
    proc, trace = _run(tmp_path, verify_rc=0)
    assert proc.returncode == 0, proc.stderr
    assert "verify_runtime_db_role" in trace and "DAPHNE_STARTED" in trace
    assert trace.index("verify_runtime_db_role") < trace.index(
        "DAPHNE_STARTED"
    ), "التحقّق قبل exec daphne"


def test_a_different_role_stops_the_boot_before_daphne(tmp_path):
    proc, trace = _run(tmp_path, verify_rc=1)
    assert proc.returncode != 0
    assert "DAPHNE_STARTED" not in trace, "daphne أُقلع رغم دورٍ غير آمن"
    assert "الإقلاع مرفوض" in proc.stdout + proc.stderr


def test_the_verification_uses_the_same_variables_as_daphne(tmp_path):
    _, trace = _run(tmp_path, verify_rc=0)
    verify = next(line for line in trace.splitlines() if line.startswith("VERIFY"))
    started = next(line for line in trace.splitlines() if line.startswith("DAPHNE_STARTED"))
    assert "DB_USER=shschool_app" in verify and f"DB_PASSWORD={APP_PASSWORD}" in verify
    assert "DATABASE_URL=unset" in verify, "الدور يجب ألّا يسقط إلى DATABASE_URL المالك"
    assert "DB_USER=shschool_app" in started and "DATABASE_URL=unset" in started


def test_production_without_the_app_password_is_still_refused_without_verifying(tmp_path):
    proc, trace = _run(tmp_path, env_extra={"APP_DB_PASSWORD": ""})
    assert proc.returncode != 0
    assert "verify_runtime_db_role" not in trace and "DAPHNE_STARTED" not in trace
