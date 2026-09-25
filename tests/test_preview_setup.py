"""[التشغيل] المعاينةُ المركزيّةُ المحلّيّة: عقدُها لا يُكسَر بصمت.

خادمٌ واحدٌ يعرض `main` بوضع الإنتاج ويتحوّل مؤقّتاً إلى شجرة جلسة (`docker-compose.preview.yml`،
`scripts/preview.sh`، `shschool/settings/preview.py`) — ليحلّ محلّ خادمٍ مقيمٍ لكلّ جلسة على جهازٍ
ذاكرتُه 16 غيغا. ولأنّه يعمل بلا مراقبةٍ ويتشارك القاعدةَ وredis مع خوادمَ أخرى، يُحرس هنا ما لو اختلّ
أصاب غيرَه أو أخرج شيئاً من الجهاز:

  - الحلقةُ المحلّيّة افتراضاً (منافذُ الجلسات كلُّها على 0.0.0.0)؛
  - لا قاعدةَ افتراضيّة: الخادمُ لا يقع على `shschool_db` المشتركة (هجرةُ فرعٍ فيها أسقطت ثماني صفحاتٍ في كلّ
    شجرة — 2026-09-11)؛
  - redis في قاعدةٍ منطقيّةٍ خاصّة فلا يلتقط عاملُ الحزمة الأصليّة (القاعدة 0) مهامَّه؛
  - لا شيءَ يخرج: البريدُ لا يُسلَّم، وSentry مُطفأ، ومفاتيحُ S3 شكليّةٌ لا تصل الإنتاجَ؛
  - ما يبقى من الإنتاج فعلاً: DEBUG مطفأ، وCSP مفروضة، والثابتُ بالبصمة والتصغير، وCelery غيرُ فوريّ؛
  - عقدُ الأمان للسكربت: لا يكتب في شجرةٍ غير `main-preview`، ولا يدفع ولا يبدّل فرعاً ولا يحذف.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.test_production_runtime_settings import _REQUIRED_ENV, _RUNTIME_KEYS

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.preview.yml"
SCRIPT = ROOT / "scripts" / "preview.sh"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


# ── ملفّ الإنشاء ────────────────────────────────────────────────


def test_the_preview_listens_on_loopback_unless_lan_is_asked_for(compose):
    (port,) = compose["services"]["web"]["ports"]

    assert port.startswith("${PREVIEW_BIND:-127.0.0.1}:")
    assert "ports" not in compose["services"]["worker"]  # لا منفذَ للعامل


def test_the_preview_has_no_default_database(compose):
    """بلا `PREVIEW_DB` يفشل الإنشاءُ — لا يعود الخادمُ إلى القاعدة المشتركة بصمت."""
    db_name = compose["x-preview-env"]["DB_NAME"]

    assert db_name.startswith("${PREVIEW_DB:?")
    assert "shschool_db" not in db_name


def test_the_preview_redis_is_a_logical_db_of_its_own(compose):
    url = compose["x-preview-env"]["REDIS_URL"]

    assert url.endswith("/${PREVIEW_REDIS_DB:-9}")  # لا 0: القاعدةُ 0 لعامل الحزمة الأصليّة
    assert compose["x-preview-env"]["SESSION_NAMESPACE"] == "${PREVIEW_DB}"


def test_nothing_leaves_the_machine(compose):
    env = compose["x-preview-env"]

    assert env["EMAIL_BACKEND"] == "core.mail_backends.UndeliveredEmailBackend"
    assert env["SENTRY_DSN"] == ""
    assert env["AWS_S3_ENDPOINT_URL"] == "" and env["AWS_S3_CUSTOM_DOMAIN"] == ""
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_STORAGE_BUCKET_NAME"):
        assert env[key].startswith("preview-not-a-real"), f"{key} يجب أن يبقى شكليّاً"


def test_web_and_worker_share_one_environment_and_are_capped(compose):
    web, worker = compose["services"]["web"], compose["services"]["worker"]

    assert web["environment"] == worker["environment"] == compose["x-preview-env"]
    assert web["mem_limit"] and worker["mem_limit"]  # سقفٌ يحمي الجهازَ من تسرّبٍ أو تقريرٍ جامح
    assert worker["depends_on"]["web"]["condition"] == "service_healthy"  # بعد الهجرة
    assert "--concurrency=1" in "".join(worker["command"])  # عمليّةٌ واحدة: توفيرُ الذاكرة
    assert "profiles" not in web and "profiles" not in worker
    assert web["volumes"][-1] == worker["volumes"][-1] == "preview_static:/app/staticfiles"


def test_the_start_command_migrates_then_collects_static_then_drops_to_the_app_role(compose):
    script = "".join(compose["services"]["web"]["command"])

    assert script.index("set -e") < script.index("migrate --noinput")  # هجرةٌ تسقط توقف الإقلاع
    assert script.index("migrate --noinput") < script.index("collectstatic --noinput --clear")
    assert script.index("collectstatic") < script.index("export DB_USER=shschool_app")
    assert "daphne" in script and "runserver" in script  # prod ثمّ dev


def test_every_preview_variable_is_known_to_the_script(compose):
    """أيُّ متغيّرٍ يقرؤه الإنشاءُ ويجهله السكربتُ (أو العكس) خطأٌ إملائيّ ينتظر يومَ الإقلاع."""
    in_compose = set(re.findall(r"PREVIEW_[A-Z_]+", COMPOSE.read_text(encoding="utf-8")))
    in_script = set(re.findall(r"PREVIEW_[A-Z_]+", SCRIPT.read_text(encoding="utf-8")))
    # الأسماءُ المصدَّرة لا القيمُ: `PREVIEW_ENV_FILE="$PREVIEW_DIR/.env"` يصدّر الأوّلَ وحدَه.
    exported = {
        name
        for line in _code_lines()
        if re.match(r"\s*export\s", line)
        for name in re.findall(r"(?<![$\w{])(PREVIEW_[A-Z_]+)(?==|;|\s|$)", line)
    }
    optional = {"PREVIEW_REDIS_DB"}  # للإنشاء افتراضٌ ولا يضبطه السكربت

    assert in_compose - optional <= in_script, "متغيّرٌ في الإنشاء لا يضبطه السكربت"
    assert exported <= in_compose, "متغيّرٌ يصدّره السكربتُ ولا يقرؤه الإنشاء"


# ── السكربت ────────────────────────────────────────────────────


def _code_lines() -> list[str]:
    return [
        line
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


@pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash في هذه البيئة")
def test_the_script_parses():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_the_script_stops_at_the_first_failure():
    assert "set -euo pipefail" in _code_lines()


FORBIDDEN = [
    r"\bgit\s+(push|checkout|switch|stash|clean|merge|rebase|pull|commit|add|branch\s+-D)\b",
    r"\brm\s+-\w*r",
    r"\bdocker\s+(rm|rmi|stop|kill|system|network|volume|image\s+rm|container\s+prune)\b",
    r"prune",
    r"DROP\s+DATABASE",
]


@pytest.mark.parametrize("pattern", FORBIDDEN)
def test_the_script_never_pushes_switches_or_deletes(pattern):
    """عقدُ الأمان: تكتب المعاينةُ في `main-preview` وقاعدتِها وحدَهما — لا تدفع، ولا تبدّل فرعاً
    (رأسُ المستودع مشتركٌ بين الجلسات)، ولا تحذف قاعدةً أو شجرةً أو حاويةً أو حجماً."""
    offenders = [line for line in _code_lines() if re.search(pattern, line)]

    assert not offenders, offenders


def test_reset_hard_only_targets_the_preview_tree():
    resets = [line for line in _code_lines() if re.search(r"\bgit\b.*reset --hard", line)]

    assert resets and all('"$PREVIEW_DIR"' in line for line in resets), resets


def test_the_script_refuses_reset_in_an_unknown_or_hand_edited_tree():
    text = SCRIPT.read_text(encoding="utf-8")
    guard = text[text.index("guard_tree() {") : text.index("slug_db()")]

    assert '"main-preview"' in guard  # اسمُ الشجرة
    assert "--untracked-files=no" in guard  # لا تعديلَ يدويّاً على ملفٍّ متتبَّع


# ── إعداداتُ وضع المعاينة ──────────────────────────────────────


def _load_preview_settings(**overrides):
    env = os.environ.copy()
    for key in _RUNTIME_KEYS:
        env.pop(key, None)
    env.update(_REQUIRED_ENV)
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "shschool.settings.preview",
            "CELERY_ASYNC_ENABLED": "true",
            "REDIS_URL": "redis://example.invalid:6380/9",
            "DB_NAME": "ss_main_preview",
        }
    )
    env.update({key: str(value) for key, value in overrides.items()})

    code = r"""
import shschool.settings.preview as s

print("STORAGE_BACKEND=" + s.STORAGES["default"]["BACKEND"])
print("STATIC_BACKEND=" + s.STORAGES["staticfiles"]["BACKEND"])
print("MEDIA_URL=" + s.MEDIA_URL)
print("DEBUG=" + str(s.DEBUG))
print("SSL_REDIRECT=" + str(s.SECURE_SSL_REDIRECT))
print("HSTS=" + str(s.SECURE_HSTS_SECONDS))
print("SESSION_SECURE=" + str(s.SESSION_COOKIE_SECURE))
print("CSRF_SECURE=" + str(s.CSRF_COOKIE_SECURE))
print("SESSION_NAME=" + s.SESSION_COOKIE_NAME)
print("CSRF_NAME=" + s.CSRF_COOKIE_NAME)
print("CSP=" + str(s.CONTENT_SECURITY_POLICY is not None))
print("XFRAME=" + s.X_FRAME_OPTIONS)
print("CELERY_EAGER=" + str(s.CELERY_TASK_ALWAYS_EAGER))
print("CONN_MAX_AGE=" + str(s.DATABASES["default"]["CONN_MAX_AGE"]))
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
    )


def _values(result):
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def test_the_preview_settings_keep_production_and_drop_only_what_the_machine_lacks():
    result = _load_preview_settings()
    assert result.returncode == 0, result.stderr
    v = _values(result)

    # ما يُغيَّر (ثلاثةُ أشياء): التخزين، وhttp، واسمُ الكوكي.
    assert v["STORAGE_BACKEND"] == "core.db_storage.DatabaseStorage"  # لا S3
    assert v["MEDIA_URL"] == "/media/"
    assert (v["SSL_REDIRECT"], v["HSTS"]) == ("False", "0")
    assert (v["SESSION_SECURE"], v["CSRF_SECURE"]) == ("False", "False")
    assert (v["SESSION_NAME"], v["CSRF_NAME"]) == ("sessionid_preview", "csrftoken_preview")

    # ما يبقى كالإنتاج — هو غرضُ المعاينة أصلاً.
    assert v["DEBUG"] == "False"
    assert v["STATIC_BACKEND"] == "core.static_storage.MinifiedManifestStaticFilesStorage"
    assert v["CSP"] == "True"  # مفروضةٌ لا report-only
    assert v["XFRAME"] == "DENY"
    assert v["CELERY_EAGER"] == "False"  # عاملٌ حقيقيّ لا تنفيذٌ فوريّ
    assert v["CONN_MAX_AGE"] == "0"


def test_production_itself_is_untouched_by_the_preview_module():
    """استيرادُ preview لا يُبقي أثراً في production: النسخةُ في الإنتاج تبقى S3 وsecure."""
    env = os.environ.copy()
    for key in _RUNTIME_KEYS:
        env.pop(key, None)
    env.update(_REQUIRED_ENV)
    code = (
        "import shschool.settings.preview\n"
        "import shschool.settings.production as p\n"
        "print(p.STORAGES['default']['BACKEND'])\n"
        "print(p.SECURE_SSL_REDIRECT, p.SESSION_COOKIE_SECURE,"
        " getattr(p, 'SESSION_COOKIE_NAME', 'sessionid'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    backend, flags = result.stdout.strip().splitlines()
    assert backend == "storages.backends.s3boto3.S3Boto3Storage"
    assert flags == "True True sessionid"
