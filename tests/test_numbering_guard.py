"""حارسُ تصادم الترقيم (W-20261003-005): ADR ورموزُ القيود عبر الشجرة وmain والطلبات المفتوحة.

وقع التصادمُ مرّتين رصدهما إنسانٌ بعد الدمج (ADR-0008/0009 وHC21/HC22، 2026-10-01/02).
"""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _guard():
    spec = importlib.util.spec_from_file_location(
        "check_numbering", ROOT / "scripts" / "check_numbering.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _guard()

A = "docs/adr/0010-a.md"
B = "docs/adr/0010-b.md"
C = "docs/adr/0011-c.md"


def test_two_files_with_one_prefix_in_the_tree_fail():
    problems = guard.adr_collisions([A, B], main=[], prs=[])

    assert len(problems) == 1 and "ADR-0010" in problems[0]


def test_two_distinct_prefixes_pass():
    assert guard.adr_collisions([A, C], main=[], prs=[]) == []


def test_the_same_file_in_main_is_not_a_collision():
    assert guard.adr_collisions([A], main=[A], prs=[]) == []


def test_a_different_file_with_the_same_prefix_in_main_fails():
    problems = guard.adr_collisions([A], main=[B], prs=[])

    assert len(problems) == 1 and "main" in problems[0] and B in problems[0]


def test_an_open_pull_request_with_the_same_prefix_fails_and_names_its_number():
    prs = guard.open_pr_adrs([{"number": 812, "files": [{"path": B}, {"path": "core/x.py"}]}])

    problems = guard.adr_collisions([A], main=[], prs=prs)

    assert len(problems) == 1 and "#812" in problems[0]


def test_the_own_pull_request_is_not_a_collision_with_itself():
    prs = guard.open_pr_adrs([{"number": 812, "files": [{"path": A}]}])

    assert guard.adr_collisions([A], main=[], prs=prs, own_pr=812) == []
    assert guard.adr_collisions([A], main=[], prs=prs) == [], "الملفُّ نفسُه ليس تصادماً"


def test_only_adr_markdown_files_have_a_prefix():
    assert guard.adr_prefix("docs/adr/0010-x.md") == "0010"
    assert guard.adr_prefix("docs/adr/README.md") is None
    assert guard.adr_prefix("docs/other/0010-x.md") is None


def test_a_duplicated_constraint_code_fails():
    text = '_hard("HC21", "a")\n_hard("HC22", "b")\n_hard("HC21", "c")\n_soft("SC1", "d", 1.0)\n'

    problems = guard.code_duplicates(text)

    assert len(problems) == 1 and "HC21" in problems[0]


def test_unique_constraint_codes_pass():
    assert guard.code_duplicates('_hard("HC1", "a")\n_hard("HC2", "b")\n') == []


def test_the_current_registry_has_unique_codes():
    text = (ROOT / "operations" / "constraint_registry.py").read_text(encoding="utf-8")

    assert guard.code_duplicates(text) == []


@pytest.mark.skipif(shutil.which("git") is None, reason="يحتاج git")
def test_the_script_runs_end_to_end_with_a_simulated_open_pull_request(tmp_path, capsys):
    prs = tmp_path / "prs.json"
    existing = sorted(p.name for p in (ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    prefix = existing[0][:4]
    prs.write_text(
        json.dumps([{"number": 999, "files": [{"path": f"docs/adr/{prefix}-other.md"}]}]),
        encoding="utf-8",
    )

    assert guard.main(["--root", str(ROOT), "--prs-json", str(prs)]) == 1
    assert "#999" in capsys.readouterr().out
    assert guard.main(["--root", str(ROOT), "--skip-prs"]) == 0
