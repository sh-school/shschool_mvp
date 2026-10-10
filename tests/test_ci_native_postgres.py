"""[CI] لا وظيفةَ تعتمد على حاويةِ خدمةٍ تُسحب من Docker Hub (W-20261010-016، امتدادٌ لـ#927).

سقفُ السحب غيرُ الموثَّق في Docker Hub (toomanyrequests) أسقط الفحوصَ 2026-10-09 وكلُّ وظيفةٍ باقيةٌ على حاوية
postgres/redis معرَّضةٌ له. فكلُّ وظيفةٍ تحتاج قاعدةً تأخذها من الإجراء المحلّيّ `native-postgres` على الـrunner، والاستعادةُ
على PostgreSQL 18 (نسخةُ الإنتاج) لا 16.
"""

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = sorted((_ROOT / ".github/workflows").glob("*.yml"))
_ACTION = "./.github/actions/native-postgres"


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _jobs():
    for path in _WORKFLOWS:
        for name, job in (_load(path).get("jobs") or {}).items():
            yield path.name, name, job


def test_no_job_pulls_a_postgres_or_redis_service_container():
    """لا `services:` بصورة postgres أو redis في أيّ workflow — فسحبُها من Docker Hub هو سببُ السقوط."""
    offenders = []
    for wf, name, job in _jobs():
        for svc, spec in (job.get("services") or {}).items():
            image = str((spec or {}).get("image", ""))
            if image.startswith(("postgres", "redis")) or svc in ("postgres", "redis"):
                offenders.append(f"{wf}::{name}::{svc}={image}")
    assert not offenders, offenders


def test_the_jobs_converted_by_this_card_use_the_native_action():
    """الوظائفُ الستُّ التي حُوِّلت (axe وe2e وnightly واللقطات وثلاثُ وظائف الأسبوعيّ والاستعادة) تستعمل الإجراءَ الأصليّ."""
    expected = {
        ("quality-gate.yml", "axe-a11y"),
        ("quality-gate.yml", "e2e"),
        ("nightly.yml", "full-pytest"),
        ("visual-snapshots.yml", "snapshots"),
        ("quality.yml", "coverage-report"),
        ("quality.yml", "mutation-testing"),
        ("quality.yml", "api-contracts"),
        ("backup-restore-test.yml", "restore-drill"),
    }
    using = {
        (wf, name)
        for wf, name, job in _jobs()
        if any(step.get("uses") == _ACTION for step in job.get("steps", []))
    }
    assert expected <= using, expected - using


def test_the_native_step_comes_after_checkout_because_the_action_is_local():
    """إجراءٌ محلّيٌّ يُقرأ من المستودع: لا يُستدعى قبل `actions/checkout` في وظيفته."""
    for wf, name, job in _jobs():
        uses = [step.get("uses", "") for step in job.get("steps", [])]
        if _ACTION in uses:
            first_checkout = next(
                (i for i, u in enumerate(uses) if u.startswith("actions/checkout@")), None
            )
            assert first_checkout is not None, f"{wf}::{name} بلا checkout"
            assert uses.index(_ACTION) > first_checkout, f"{wf}::{name}: الإجراءُ قبل checkout"


def test_the_restore_drill_runs_on_postgres_18_like_production():
    """الاستعادةُ على 18 لا 16 (الإنتاجُ على 18)، بالمستخدم وكلمة المرور والقاعدة التي تقرؤها خطواتُها اللاحقة."""
    job = _load(_ROOT / ".github/workflows/backup-restore-test.yml")["jobs"]["restore-drill"]
    native = [s for s in job["steps"] if s.get("uses") == _ACTION]
    assert len(native) == 1
    with_ = native[0]["with"]
    assert str(with_["version"]) == "18"
    assert (with_["db_user"], with_["db_name"]) == ("restore_user", "restore_test")
    assert "restore_test" in (_ROOT / ".github/workflows/backup-restore-test.yml").read_text(
        encoding="utf-8"
    )


def test_the_action_supports_a_version_input_and_defaults_stay_unchanged():
    """الافتراضيُّ 16 وtest_user/test_db — فلا يتغيّر إعدادُ أيّ وظيفةٍ قائمةٍ تستعمله دون مدخلات."""
    inputs = _load(_ROOT / ".github/actions/native-postgres/action.yml")["inputs"]
    assert str(inputs["version"]["default"]) == "16"
    assert inputs["db_user"]["default"] == "test_user"
    assert inputs["db_name"]["default"] == "test_db"
    assert inputs["redis"]["default"] == "false"
