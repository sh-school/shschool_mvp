"""حارسُ مهلةِ وظائف CI — W-20261019-022 (المرحلة أ).

كلُّ وظيفةٍ من الثماني (أربعٌ في بوابة الدمج وأربعٌ في الفحص الأسبوعيّ) لها `timeout-minutes` صريحٌ بقيمةٍ من أزمنة تشغيلٍ مقيسة،
فلا تعلّق وظيفةٌ ست ساعاتٍ (المهلةُ الافتراضيّة) وتحجز طابورَ الدمج. يقرأ YAML بلا شبكة.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# (الملف، الوظيفة) ← أقصى مهلةٍ مقبولة بالدقائق (سقفٌ يمنع رفعَها بلا قياس)
LIMITS = {
    ("quality-gate.yml", "test-coverage"): 10,
    ("quality-gate.yml", "migration-linter"): 10,
    ("quality-gate.yml", "axe-a11y"): 20,
    ("quality-gate.yml", "e2e"): 20,
    ("quality.yml", "pip-audit"): 10,
    ("quality.yml", "radon"): 10,
    ("quality.yml", "coverage-report"): 60,
    ("quality.yml", "api-contracts"): 15,
}


def _jobs(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"]


@pytest.mark.parametrize(("workflow", "job"), sorted(LIMITS))
def test_job_has_a_measured_timeout(workflow, job):
    minutes = _jobs(workflow)[job].get("timeout-minutes")
    assert isinstance(
        minutes, int
    ), f"{workflow}:{job} بلا timeout-minutes صريح (الافتراضيّ 360 دقيقة)"
    assert (
        1 <= minutes <= LIMITS[(workflow, job)]
    ), f"{workflow}:{job} مهلةٌ {minutes} خارج السقف المقيس {LIMITS[(workflow, job)]}"


def test_every_merge_gate_job_has_a_timeout():
    missing = [
        name for name, job in _jobs("quality-gate.yml").items() if "timeout-minutes" not in job
    ]
    assert not missing, f"وظائفُ بوابة الدمج بلا مهلة: {missing}"
