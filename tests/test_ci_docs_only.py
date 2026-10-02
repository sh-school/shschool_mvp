"""تصنيفُ الطلب الوثائقيّ و«قرّاءُ الوثائق» — W-20261002-031."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ci_docs_only", ROOT / "scripts" / "ci_docs_only.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


@pytest.mark.parametrize(
    "paths",
    [
        ["docs/adr/0002-x.md"],
        ["AAdocs/ministry_data/2026_2027/remediation_plan.md", "docs/a/b.md"],
    ],
)
def test_md_under_docs_and_aadocs_only_is_docs_only(paths):
    assert mod.is_docs_only(paths)


@pytest.mark.parametrize(
    "paths",
    [
        [],  # خروجٌ فارغٌ ⇒ كامل
        ["README.md"],  # md خارجَ المجلّدَين
        ["CLAUDE.md"],
        ["handover_notes/x.md"],
        ["docs/config.yml"],  # غيرُ md تحت docs/
        ["docs/data.json"],
        ["docs/notes.txt"],
        ["docs/a.md", "quality/models/appraisal.py"],  # خليطٌ
        [".github/workflows/quality-gate.yml"],
        [".github/README.md"],
        ["scripts/ci_needs_gate.py"],
        [".claude/hooks/x.md"],
        ["docsx/a.md"],
    ],
)
def test_anything_else_runs_the_full_suite(paths):
    assert not mod.is_docs_only(paths)


def test_classify_fails_safe_on_git_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # لا مستودعَ هنا ⇒ git يفشل
    assert mod.main(["classify", "deadbeef"]) == 0
    assert capsys.readouterr().out.strip() == "docs_only=false"


def test_docs_readers_cover_the_known_document_tests():
    readers = set(mod.docs_readers(ROOT))
    for name in ("test_data_retention.py", "test_regression_guards_doc.py", "test_docs_viewer.py"):
        assert f"tests/{name}" in readers


def test_docs_readers_pattern_catches_dynamic_reads(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        'p = ROOT / "docs" / "x"\nlist(p.iterdir())\n', encoding="utf-8"
    )
    (tmp_path / "tests" / "test_b.py").write_text('open("AAdocs/x")\n', encoding="utf-8")
    (tmp_path / "tests" / "test_c.py").write_text("assert 1 == 1\n", encoding="utf-8")
    assert mod.docs_readers(tmp_path) == ["tests/test_a.py", "tests/test_b.py"]


def test_workflow_filters_by_event_inside_the_job_not_paths_ignore():
    raw = yaml.safe_load((ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8"))
    triggers = raw.get("on", raw.get(True))
    for event in ("push", "pull_request", "merge_group"):
        assert "paths-ignore" not in (
            triggers.get(event) or {}
        ), "paths-ignore يحجب السياق فيتعلّق الطلب"
        assert "paths" not in (triggers.get(event) or {})
    steps = raw["jobs"]["test-coverage"]["steps"]
    diff = next(step for step in steps if step.get("id") == "diff")
    assert (
        diff["if"] == "github.event_name == 'pull_request'"
    ), "الحسابُ على الطلب وحدَه؛ push والطابور كاملان"
