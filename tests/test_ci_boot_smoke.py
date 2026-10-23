"""حارسُ وظيفة فحص الإقلاع — W-20261022-022.

الوظيفةُ تقلع التطبيقَ بإعدادات production على بياناتٍ اصطناعيّة وتفحص /health/؛ يضمن هذا الاختبارُ بنيتَها بلا شبكة:
مستقلّةٌ خارج المسار الحرج، بمهلةٍ صريحة، وبأسرارِ اختبارٍ لا أسرارٍ حقيقيّة.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_FILE = _WORKFLOWS / "boot-smoke.yml"


def _doc() -> dict:
    return yaml.safe_load(_FILE.read_text(encoding="utf-8"))


def test_the_boot_job_runs_on_production_settings_and_has_a_timeout():
    job = _doc()["jobs"]["boot"]
    assert job["env"]["DJANGO_SETTINGS_MODULE"] == "shschool.settings.production"
    assert isinstance(job["timeout-minutes"], int) and 1 <= job["timeout-minutes"] <= 20


def test_the_boot_job_is_off_the_critical_path():
    """لا تدخل needs: في أيّ وظيفةٍ من بوابة الدمج فلا تحجب دمجاً ولا نشراً."""
    for path in _WORKFLOWS.glob("*.yml"):
        if path == _FILE:
            continue
        for name, job in (
            yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}
        ).items():
            needs = job.get("needs") or []
            needs = [needs] if isinstance(needs, str) else needs
            assert "boot" not in needs, f"{path.name}:{name} تعتمد على وظيفة فحص الإقلاع"


def test_the_boot_job_probes_health_and_uses_only_synthetic_secrets():
    text = _FILE.read_text(encoding="utf-8")
    assert "/health/" in text and "daphne" in text
    assert "secrets." not in text, "الوظيفةُ لا تقرأ أسرارَ المستودع"
    env = _doc()["jobs"]["boot"]["env"]
    assert "127.0.0.1" in env["DATABASE_URL"] and "127.0.0.1" in env["REDIS_URL"]
