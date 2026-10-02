"""حَكَمُ بوّابتَي الدمج (`scripts/ci_needs_gate.py`) وحارسُ أنّ كلَّ مهمّةٍ تدخل الحكم — W-20261002-031.

بلا قاعدةٍ ولا شبكة: يقرأ الملفّاتِ ويستدعي دوالَّ السكربت.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_needs_gate", ROOT / "scripts" / "ci_needs_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

WORKFLOWS = {
    "quality-gate.yml": "gate-summary",
    "security-scan.yml": "summary",
}
# مهمّةٌ لا تدخل الملخّص عمداً، بسببها. وأيُّ مهمّةٍ جديدةٍ خارجَ needs بلا سطرٍ هنا تُسقط الاختبار.
NOT_IN_NEEDS = {
    (
        "quality-gate.yml",
        "pr-file-collision",
    ): "تحذيرٌ لا حظر (scripts/pr_file_collision.py) — لا يحجب الدمج",
}


def _ok(*jobs: str) -> dict:
    return {j: {"result": "success"} for j in jobs}


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))[
        "jobs"
    ]


def _triggers(name: str) -> dict:
    raw = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    return raw.get("on", raw.get(True))  # يقرأ YAML 1.1 المفتاحَ `on` قيمةً منطقيّة


# ── الحكمُ ────────────────────────────────────────────────────────────────────


def test_all_success_passes():
    _, failures = gate.judge(_ok("a", "b"), "pull_request")
    assert failures == []


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "weird", None])
def test_anything_but_success_fails_on_pull_request(result):
    needs = {**_ok("a"), "b": {"result": result}}
    _, failures = gate.judge(needs, "pull_request")
    assert any(f.startswith("b:") for f in failures)


def test_skipped_is_exempt_only_for_the_listed_event_and_job():
    needs = {**_ok("a"), "e2e": {"result": "skipped"}}
    assert gate.judge(needs, "push")[1] == []
    assert gate.judge(needs, "pull_request")[1], "skipped على الطلب فشلٌ"
    assert gate.judge(needs, "merge_group")[1], "skipped على الطابور فشلٌ"
    other = {**_ok("a"), "ruff": {"result": "skipped"}}
    assert gate.judge(other, "push")[1], "ruff غيرُ معفًى على push"


@pytest.mark.parametrize("result", ["cancelled", "failure"])
def test_exempt_job_still_fails_when_cancelled_or_failed(result):
    needs = {**_ok("a"), "e2e": {"result": result}}
    assert gate.judge(needs, "push")[1]


def test_cheap_security_and_core_jobs_are_never_exempt():
    # مراجعةُ 0105: secrets-scan وmigration-linter رخيصان ويفحصان ما دخل main فعلاً — دفاعُ عمق.
    exempt_jobs = {job for (_, job) in gate.EXEMPT}
    assert not exempt_jobs & {"secrets-scan", "migration-linter", "test-coverage", "fast-guards"}


def test_only_push_is_ever_exempted():
    assert {event for (event, _) in gate.EXEMPT} == {"push"}


# ── الفشلُ المغلق ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("needs_json", "event"),
    [
        (None, "pull_request"),
        ("", "pull_request"),
        ("   ", "pull_request"),
        ("{not json", "pull_request"),
        ("[]", "pull_request"),
        ("{}", "pull_request"),
        (json.dumps(_ok("a")), None),
        (json.dumps(_ok("a")), "workflow_run"),
    ],
)
def test_fails_closed_on_missing_or_malformed_input(needs_json, event):
    assert gate.run(needs_json, event, "t", None) == 1


def test_run_passes_and_writes_summary(tmp_path):
    out = tmp_path / "summary.md"
    assert gate.run(json.dumps(_ok("a", "b")), "pull_request", "عنوان", str(out)) == 0
    assert "PASS" in out.read_text(encoding="utf-8")


def test_run_fails_on_unknown_result_text():
    assert gate.run(json.dumps({"a": {"result": "neutral"}}), "pull_request", "t", None) == 1


# ── كلُّ مهمّةٍ في الملفّ تدخل الحكم ────────────────────────────────────────────


@pytest.mark.parametrize("name", list(WORKFLOWS))
def test_every_job_is_in_summary_needs_or_justified(name):
    jobs = _load(name)
    needs = set(jobs[WORKFLOWS[name]]["needs"])
    missing = [
        j for j in jobs if j != WORKFLOWS[name] and j not in needs and (name, j) not in NOT_IN_NEEDS
    ]
    assert not missing, (
        f"مهمّةٌ خارجَ بوّابة الدمج بصمت: {missing} — أضفْها إلى needs الملخّص، "
        "أو أعلِن إعفاءَها بسببٍ في NOT_IN_NEEDS"
    )
    assert needs <= set(jobs)


@pytest.mark.parametrize("name", list(WORKFLOWS))
def test_summary_uses_the_shared_judge_with_whole_needs(name):
    summary = _load(name)[WORKFLOWS[name]]
    assert str(summary["if"]).strip() == "always()"
    runs = [step for step in summary["steps"] if "ci_needs_gate.py" in step.get("run", "")]
    assert len(runs) == 1
    assert "toJSON(needs)" in runs[0]["env"]["NEEDS_JSON"]
    assert "if" not in runs[0], "خطوةُ الحكم لا تُشرَط — وإلّا تُتخطّى فتمرّ"


def test_exempt_jobs_depend_only_on_non_exempt_jobs_and_are_event_gated():
    jobs = _load("quality-gate.yml")
    exempt_jobs = {job for (_, job) in gate.EXEMPT}
    for job in exempt_jobs:
        assert job in jobs, f"إعفاءٌ لمهمّةٍ غيرِ موجودة: {job}"
        deps = jobs[job].get("needs") or []
        deps = [deps] if isinstance(deps, str) else deps
        assert not set(deps) & exempt_jobs, f"{job} يعتمد على مهمّةٍ معفاة فيُخفي إعفاؤها فشلَها"
        assert "github.event_name" in str(
            jobs[job].get("if", "")
        ), f"{job}: يُعفى skipped بسبب شرط الحدث وحدَه، فلا بدّ أن يُتخطّى بـ`if` على الحدث"


def test_required_status_contexts_keep_their_names():
    # اسمُ المهمّة جزءٌ من قاعدة حماية الفرع؛ تغييرُه يُعلّق كلَّ الطلبات بانتظار سياقٍ لا يصل.
    assert _load("quality-gate.yml")["gate-summary"]["name"] == "ملخص بوابة الجودة"
    assert _load("security-scan.yml")["summary"]["name"] == "Security Summary"


def test_security_scan_keeps_its_triggers():
    assert {"push", "pull_request", "merge_group", "schedule", "workflow_dispatch"} <= set(
        _triggers("security-scan.yml")
    )


def test_quality_gate_keeps_pull_request_and_merge_group_full():
    assert {"push", "pull_request", "merge_group"} <= set(_triggers("quality-gate.yml"))
    jobs = _load("quality-gate.yml")
    for job in ("mypy", "axe-a11y", "e2e"):
        assert (
            str(jobs[job]["if"]).strip() == "github.event_name != 'push'"
        ), f"{job}: لا يُتخطّى إلا على push"
