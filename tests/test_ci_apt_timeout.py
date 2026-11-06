"""حارسُ مهلة خطوات apt-get install في كلّ workflow — W-20261106-004.

في الطلب #1353 علقت خطوةُ تثبيت مكتبات النظام في pip-audit نحو 6 ساعات (المهلةُ الافتراضيّة) حتى أُلغيت،
فبقيت الفحوصُ معلّقةً وتعطّل المشغّل طوال الليل. كلُّ خطوةٍ تشغّل `apt-get install` لها `timeout-minutes` صريح.
يقرأ YAML بلا شبكة، ويفحص كلَّ ملفٍّ في `.github/workflows` بدل قائمةٍ ثابتة فلا تفلت خطوةٌ جديدة.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _unbounded_apt_steps(doc: dict, workflow: str) -> list[str]:
    """خطواتُ `apt-get install` التي لا `timeout-minutes` لها، بصيغة `ملف:وظيفة:خطوة`."""
    offenders = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate(job.get("steps") or []):
            if "apt-get install" in str(step.get("run", "")) and "timeout-minutes" not in step:
                offenders.append(f"{workflow}:{job_name}:step[{i}] {step.get('name')}")
    return offenders


def test_every_apt_get_install_step_in_every_workflow_has_a_timeout():
    offenders = []
    apt_steps = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        apt_steps += sum(
            "apt-get install" in str(step.get("run", ""))
            for job in (doc.get("jobs") or {}).values()
            for step in job.get("steps") or []
        )
        offenders += _unbounded_apt_steps(doc, path.name)
    # حارسٌ من النجاح الفارغ: لو لم تُقرأ أيُّ خطوةِ تثبيتٍ أصلاً فالفحصُ لم يفحص شيئاً
    assert apt_steps > 0, "لم يُعثر على أيّ خطوة apt-get install — المسارُ أو الفحصُ معطوب"
    assert not offenders, f"خطواتُ apt-get install بلا timeout-minutes: {offenders}"


def test_the_guard_flags_an_apt_step_without_a_timeout():
    doc = {
        "jobs": {
            "audit": {
                "steps": [
                    {"name": "بلا مهلة", "run": "sudo apt-get install -y libcairo2-dev"},
                ]
            }
        }
    }
    assert _unbounded_apt_steps(doc, "fake.yml") == ["fake.yml:audit:step[0] بلا مهلة"]


def test_the_guard_accepts_an_apt_step_with_a_timeout_and_ignores_other_steps():
    doc = {
        "jobs": {
            "audit": {
                "steps": [
                    {
                        "name": "مع مهلة",
                        "timeout-minutes": 10,
                        "run": "sudo apt-get install -y libcairo2-dev",
                    },
                    {"name": "بلا apt", "run": "pip install -r requirements.txt"},
                    {"name": "uses فقط", "uses": "actions/checkout@v4"},
                ]
            }
        }
    }
    assert _unbounded_apt_steps(doc, "fake.yml") == []
