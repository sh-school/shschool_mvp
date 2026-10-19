"""حارسُ تخفيف طابور الدمج — W-20261019-006.

أرجلُ axe-core الثلاث وPlaywright e2e تُخطّى على merge_group (تُجرى على الطلب نفسِه قبل الدخول) وتبقى على pull_request وpush
(push يُعفى skipped فيه أصلاً). يقرأ YAML والسكربت بلا شبكة؛ ويفشل إن أُسقطت الوظيفتان عن pull_request أو أُعفي زوجُ pull_request.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_needs_gate", ROOT / "scripts" / "ci_needs_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

LIGHTENED = ("axe-a11y", "e2e")


def _jobs() -> dict:
    path = ROOT / ".github" / "workflows" / "quality-gate.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def _runs(condition: str, event: str) -> bool:
    """يقيّم شرطَ `if` المؤلَّفَ من `github.event_name != '<حدث>'` مربوطاً بـ&& على حدثٍ معيّن."""
    for clause in (c.strip() for c in condition.split("&&")):
        left, op, right = clause.partition("!=")
        assert op and left.strip() == "github.event_name", f"شرطٌ غيرُ مدعوم: {clause!r}"
        if event == right.strip().strip("'"):
            return False
    return True


def test_light_jobs_skip_on_merge_group_and_push_but_run_on_pull_request():
    jobs = _jobs()
    for job in LIGHTENED:
        cond = str(jobs[job]["if"])
        assert _runs(cond, "pull_request"), f"{job} أُسقطت عن pull_request"
        assert not _runs(cond, "merge_group"), f"{job} لا تُخطّى على merge_group"
        assert not _runs(cond, "push"), f"{job} لا تُخطّى على push"


def test_merge_group_exemption_is_exactly_the_lightened_pair():
    pairs = {pair for pair in gate.EXEMPT if pair[0] == "merge_group"}
    assert pairs == {("merge_group", job) for job in LIGHTENED}


def test_no_pull_request_pair_is_ever_exempt():
    assert not [pair for pair in gate.EXEMPT if pair[0] == "pull_request"]
    for job in LIGHTENED:
        needs = {"a": {"result": "success"}, job: {"result": "skipped"}}
        assert gate.judge(needs, "pull_request")[1], f"{job} skipped على الطلب فشلٌ"


def test_a_failed_or_cancelled_light_job_still_fails_on_merge_group():
    for job in LIGHTENED:
        for result in ("failure", "cancelled"):
            needs = {"a": {"result": "success"}, job: {"result": result}}
            assert gate.judge(needs, "merge_group")[1], f"{job} {result} يجب أن يفشل"


def test_the_quality_gate_still_listens_to_the_three_events():
    raw = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "quality-gate.yml").read_text(encoding="utf-8")
    )
    triggers = raw.get("on", raw.get(True))
    assert {"push", "pull_request", "merge_group"} <= set(triggers)
