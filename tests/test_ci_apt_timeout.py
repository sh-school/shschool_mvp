"""حارسُ مهلةِ خطوات apt-get install — W-20261106-008.

في الطلب #1353 علقت خطوةُ «Install system dependencies for native packages» في pip-audit نحو ست ساعات
(المهلةُ الافتراضيّة للخطوة) حتى أُلغيت، فتعطّل المشغّل طوال الليل. يمرّ هذا الحارسُ على كلّ workflow ويفشل
إن وُجدت خطوةٌ تشغّل `apt-get install` بلا `timeout-minutes` صريح. الخطوةُ التي عندها مهلةٌ أصلاً لا تُخفَّض،
فالحارسُ يقبل أيَّ قيمةٍ صحيحةٍ موجبة. يقرأ YAML بلا شبكة.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS.glob("*.yml"))


def _install_steps(path: Path) -> list[tuple[str, dict]]:
    """كلُّ خطوةٍ في كلّ وظيفةٍ من الملفّ تحوي `apt-get install` في سكربتها."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate((job or {}).get("steps") or []):
            if "apt-get install" in (step.get("run") or ""):
                found.append((f"{job_name}:step[{i}] {step.get('name', '')}", step))
    return found


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_every_apt_install_step_has_a_timeout(path):
    offenders = [
        label
        for label, step in _install_steps(path)
        if not isinstance(step.get("timeout-minutes"), int) or step["timeout-minutes"] < 1
    ]
    assert not offenders, f"{path.name}: خطوات apt-get install بلا timeout-minutes: {offenders}"


def test_the_guard_sees_apt_install_steps():
    """حارسٌ ضدّ التفريغ: لو لم يجد الاختبارُ أيَّ خطوة تثبيت لفحص كلَّ شيءٍ بصمت."""
    total = sum(len(_install_steps(path)) for path in WORKFLOW_FILES)
    assert total >= 20, total
