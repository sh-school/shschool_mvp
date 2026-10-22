"""حارسُ مرونة apt في وظائف المتصفّح — W-20261022-024.

مرآةُ apt تبطؤ على بعض الـrunners (35 كيلوبايت/ث مقابل 4600)، فكانت خطواتُ التثبيت تأكل مهلةَ الوظيفة (20 دقيقة)
قبل بدء الاختبارات. يضمن هذا الحارسُ بلا شبكةٍ أنّ خطوات التثبيت الثقيلة في وظيفتَي المتصفّح لها مهلةُ خطوةٍ صريحة
وإعادةُ محاولة، وأنّ إعدادَ apt يُكتب قبلها.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_APT_ACTION = "./.github/actions/apt-resilient"
_JOBS = ("axe-a11y", "e2e")


def _steps(job: str) -> list[dict]:
    doc = yaml.safe_load((_ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def test_the_apt_config_sets_retries_and_a_connection_timeout():
    doc = yaml.safe_load(
        (_ROOT / ".github/actions/apt-resilient/action.yml").read_text(encoding="utf-8")
    )
    run = doc["runs"]["steps"][0]["run"]
    assert "Acquire::Retries" in run and "Acquire::http::Timeout" in run
    assert "DPkg::Lock::Timeout" in run, "انتظارُ قفل dpkg بدل الاصطدام به"


def test_browser_jobs_write_the_apt_config_before_any_install():
    for job in _JOBS:
        uses = [s.get("uses", "") for s in _steps(job)]
        assert _APT_ACTION in uses, job
        first_install = next(
            i for i, s in enumerate(_steps(job)) if "apt-get install" in s.get("run", "")
        )
        assert uses.index(_APT_ACTION) < first_install, job


def test_heavy_install_steps_have_a_step_timeout_and_a_retry():
    for job in _JOBS:
        heavy = [
            s
            for s in _steps(job)
            if "apt-get install" in s.get("run", "") or "playwright install" in s.get("run", "")
        ]
        assert heavy, job
        for step in heavy:
            assert isinstance(step.get("timeout-minutes"), int), f"{job}: {step.get('name')}"
            assert "for attempt in 1 2" in step["run"], f"{job}: {step.get('name')}"
            assert (
                "pkill -x apt-get" in step["run"]
            ), f"{job}: {step.get('name')} بلا إنهاء apt اليتيم قبل الإعادة"


def test_the_redis_step_of_native_postgres_cannot_hang_forever():
    doc = yaml.safe_load(
        (_ROOT / ".github/actions/native-postgres/action.yml").read_text(encoding="utf-8")
    )
    step = next(s for s in doc["runs"]["steps"] if "redis-server" in s.get("run", ""))
    assert "timeout 240" in step["run"]
    assert "for attempt in 1 2" in step["run"]
    assert "pkill -x apt-get" in step["run"]


def test_composite_action_steps_never_declare_timeout_minutes():
    """`timeout-minutes` يجوز في خطوات الوظيفة لا داخل إجراءٍ مركّب: يُسقط تحميلَ الملفّ كلَّه (#1239: Unexpected value)."""
    offenders = []
    for path in sorted((_ROOT / ".github/actions").glob("*/action.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for i, step in enumerate((doc.get("runs") or {}).get("steps") or []):
            if "timeout-minutes" in step:
                offenders.append(f"{path.parent.name}:step[{i}]")
    assert not offenders, offenders
