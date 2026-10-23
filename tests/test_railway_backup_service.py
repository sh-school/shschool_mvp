"""خدمةُ النسخ الاحتياطي داخل Railway (W-20261023-018): الشبكةُ الخاصّة فقط، تشفيرٌ مطابقٌ لـ backup.yml، وفشلٌ صريح.

يحرس العقدَ لا الشبكة: لا Railway ولا قاعدةَ هنا — الاختبارُ السلوكيّ يُشغّل السكربتَ بمتغيّراتٍ ناقصةٍ/خاطئةٍ
ويتوقّع خروجاً ≠ 0 قبل أيّ اتصال.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "railway-backup.sh"
DOCKERFILE = ROOT / "Dockerfile.backup"
IAC = ROOT / ".railway" / "railway.ts"
LEGACY = ROOT / ".github" / "workflows" / "backup.yml"

GOOD_ENV = {
    "DATABASE_URL": "postgresql://u:p@postgres.railway.internal:5432/railway",
    "BACKUP_PASSPHRASE": "x" * 32,
    "BACKUP_S3_ENDPOINT": "https://example.invalid",
    "BACKUP_S3_BUCKET": "b",
    "BACKUP_S3_ACCESS_KEY_ID": "k",
    "BACKUP_S3_SECRET_ACCESS_KEY": "s",
}


def _run(**overrides):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash غير متوفّر")
    env = {"PATH": os.environ["PATH"], **GOOD_ENV}
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [bash, str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def test_script_encryption_spec_matches_the_legacy_workflow():
    """نفسُ المواصفة ليفكّها backup-restore-test.yml وrestore-prod-locally.sh بلا تغيير."""
    script = SCRIPT.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")
    for token in (
        "--cipher-algo AES256",
        "--s2k-mode 3",
        "--s2k-count 65011712",
        "--s2k-digest-algo SHA512",
        "--no-owner --no-privileges",
        "gzip -9",
    ):
        assert token in script, f"السكربت يفتقد {token}"
        assert token in legacy, f"backup.yml تغيّر ({token}) — أعد مطابقة السكربت"
    assert "-ge 32" in script, "حدُّ عبارة التشفير 32 حرفاً يجب أن يبقى"


def test_script_verifies_and_fails_loudly():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "--decrypt" in script and "gunzip" in script
    assert "PostgreSQL database dump complete" in script
    assert "head-object" in script, "لا مطابقةَ لحجم الملف المرفوع"
    assert "exit 1" in script


def test_script_prunes_only_after_upload_and_only_own_pattern():
    script = SCRIPT.read_text(encoding="utf-8")
    assert script.index("head-object") < script.index("s3 s3 rm"), "التقليمُ قبل التحقّق من الرفع"
    assert re.search(r"schoolos-\(\[0-9\]\{6\}\)", script), "التقليمُ بلا نمطٍ صارم"


@pytest.mark.parametrize(
    "bad_url",
    [
        "postgresql://u:p@junction.proxy.rlwy.net:58325/railway",
        "postgresql://u:p@db.example.com:5432/railway",
    ],
)
def test_script_refuses_public_database_url(bad_url):
    result = _run(DATABASE_URL=bad_url)
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr and "railway.internal" in result.stderr


def test_script_refuses_short_passphrase():
    result = _run(BACKUP_PASSPHRASE="short")
    assert result.returncode != 0
    assert "32" in result.stderr


@pytest.mark.parametrize("name", sorted(GOOD_ENV))
def test_script_refuses_missing_variable(name):
    result = _run(**{name: None})
    assert result.returncode != 0
    assert name in result.stderr


def test_dockerfile_has_pg18_client_gpg_awscli_and_non_root():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(
        r"^FROM postgres:18", text, re.M
    ), "عميلُ pg_dump يجب أن يطابق خادم الإنتاج (18)"
    assert "gnupg" in text and "awscli" in text
    assert re.search(r"^USER postgres", text, re.M), "لا جذرَ في حاوية النسخ"
    assert "ENTRYPOINT []" in text
    assert "railway-backup.sh" in text


def test_iac_declares_the_cron_backup_service_and_bucket():
    iac = IAC.read_text(encoding="utf-8")
    match = re.search(r'service\("db-backup",\s*\{(.*?)\n  \}\);', iac, re.DOTALL)
    assert match, "خدمةُ db-backup غير معرَّفة — سيحذفها apply"
    block = match.group(1)
    assert 'dockerfilePath: "Dockerfile.backup"' in block
    assert "cronSchedule" in block
    assert 'bucket("db-backups"' in iac
    assert re.search(r"resources:\s*\[[^\]]*\bbackup\b[^\]]*\bbackups\b", iac)


def test_no_secret_values_in_backup_files():
    for path in (SCRIPT, DOCKERFILE):
        text = path.read_text(encoding="utf-8")
        assert not re.search(
            r"postgres(ql)?://[^\s\"$]+:[^\s\"$@]+@", text
        ), f"رابطٌ بكلمة مرور في {path.name}"
