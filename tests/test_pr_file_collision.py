"""سواط 2026-09-17: ثلاثةُ طلباتٍ مفتوحةٍ عدّلت `templates/base/base.html` في
آنٍ واحد بلا علم أصحابها، وطلبان (#299 و#303) نفّذا البندَ نفسَه خلال 28 دقيقة.
`scripts/pr_file_collision.py` يحذّر من هذا قبل الدمج، لا يمنعه — تقاطعُ
ملفّين قد يكون تعديلين متكاملين، ليس خطأً بذاته.
"""

from __future__ import annotations

import importlib.util
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "pr_file_collision", ROOT / "scripts" / "pr_file_collision.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pr(number, ref, *paths):
    return {"number": number, "headRefName": ref, "files": [{"path": p} for p in paths]}


def test_no_collision_when_files_dont_overlap():
    module = _load()
    prs = [
        _pr(300, "claude/a", "behavior/views.py"),
        _pr(306, "claude/b", "parents/views.py"),
    ]
    assert module.collisions(300, prs) == []


def test_collision_reports_the_other_pr_and_shared_files():
    module = _load()
    prs = [
        _pr(300, "claude/a", "templates/base/base.html", "behavior/views.py"),
        _pr(306, "claude/b", "templates/base/base.html", "parents/views.py"),
        _pr(315, "claude/c", "templates/base/base.html", "static/css/custom/32-modules-3.css"),
    ]
    hits = module.collisions(300, prs)
    numbers = {number for number, _ref, _files in hits}
    assert numbers == {306, 315}
    for _number, _ref, files in hits:
        assert files == ["templates/base/base.html"]


def test_a_pr_never_collides_with_itself():
    module = _load()
    prs = [_pr(300, "claude/a", "core/permissions.py")]
    assert module.collisions(300, prs) == []


def test_an_unknown_pr_number_reports_nothing():
    """يقع حين لا يزال الحدث يُهيّئ نفسَه — لا يُسقط الوظيفة."""
    module = _load()
    prs = [_pr(300, "claude/a", "core/permissions.py")]
    assert module.collisions(999, prs) == []


def test_a_pr_with_no_files_never_collides():
    module = _load()
    prs = [_pr(300, "claude/a"), _pr(306, "claude/b", "core/permissions.py")]
    assert module.collisions(300, prs) == []


def test_the_job_is_advisory_not_a_required_gate():
    """يحذّر ولا يحظر: لا يدخل قائمة «ملخّص بوابة الجودة» الإلزاميّة."""
    doc = yaml.safe_load((ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8"))
    summary = doc["jobs"]["gate-summary"]
    assert "pr-file-collision" not in summary["needs"]


def test_the_job_only_runs_on_pull_request_events():
    doc = yaml.safe_load((ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["pr-file-collision"]
    assert job["if"] == "github.event_name == 'pull_request'"
