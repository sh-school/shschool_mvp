"""مطابقةُ الشجرة في طابور الدمج (`scripts/ci_tree_reuse.py`) — W-20261106-009.

بلا شبكة: تُستبدل دوالُّ git وgh بمزيّفات. القاعدة: الإعفاءُ مغلقٌ عند الشك.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_tree_reuse", ROOT / "scripts" / "ci_tree_reuse.py"
)
reuse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reuse)

TREE_A = "a" * 40
TREE_B = "b" * 40
REF = "refs/heads/gh-readonly-queue/main/pr-123-" + "c" * 40


def _patch(monkeypatch, local, reviewed):
    monkeypatch.setattr(reuse, "local_tree", lambda: local)
    monkeypatch.setattr(reuse, "reviewed_tree", lambda repo, number: reviewed)


def test_matching_tree_skips(monkeypatch):
    _patch(monkeypatch, TREE_A, TREE_A)
    assert reuse.decide("o/r", REF) is True


def test_different_tree_runs_everything(monkeypatch):
    _patch(monkeypatch, TREE_A, TREE_B)
    assert reuse.decide("o/r", REF) is False


def test_missing_artifact_runs_everything(monkeypatch):
    _patch(monkeypatch, TREE_A, None)
    assert reuse.decide("o/r", REF) is False


def test_local_git_failure_runs_everything(monkeypatch):
    def boom():
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(reuse, "local_tree", boom)
    monkeypatch.setattr(reuse, "reviewed_tree", lambda repo, number: TREE_A)
    assert reuse.decide("o/r", REF) is False


@pytest.mark.parametrize(
    "ref", [None, "", "refs/heads/main", "gh-readonly-queue/main/pr-x-abc1234"]
)
def test_unparsable_queue_ref_runs_everything(monkeypatch, ref):
    _patch(monkeypatch, TREE_A, TREE_A)
    assert reuse.decide("o/r", ref) is False


def test_missing_repo_runs_everything(monkeypatch):
    _patch(monkeypatch, TREE_A, TREE_A)
    assert reuse.decide(None, REF) is False


def test_pr_number_is_read_from_the_queue_ref():
    assert reuse.pr_number(REF) == 123
    assert reuse.pr_number("refs/heads/gh-readonly-queue/release/x/pr-7-" + "d" * 40) == 7


@pytest.mark.parametrize("bad", [None, "", "abc", "g" * 40, "a" * 39, "a" * 41])
def test_corrupt_fingerprint_never_matches(bad):
    assert reuse.trees_match(bad, bad) is False
    assert reuse.trees_match(TREE_A, bad) is False


def test_reviewed_tree_is_none_when_gh_fails(monkeypatch):
    def boom(*cmd):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(reuse, "_run", boom)
    assert reuse.reviewed_tree("o/r", 1) is None


def test_reviewed_tree_is_none_without_a_successful_run(monkeypatch):
    answers = iter(["f" * 40 + "\n", "\n"])
    monkeypatch.setattr(reuse, "_run", lambda *cmd: next(answers))
    assert reuse.reviewed_tree("o/r", 1) is None


def test_check_writes_match_false_on_unexpected_error(monkeypatch, tmp_path, capsys):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(reuse, "decide", lambda repo, ref: 1 / 0)
    assert reuse.main(["check"]) == 0
    assert out.read_text(encoding="utf-8") == "match=false\n"


def test_check_writes_match_true_only_on_match(monkeypatch, tmp_path):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(reuse, "decide", lambda repo, ref: True)
    assert reuse.main(["check"]) == 0
    assert out.read_text(encoding="utf-8") == "match=true\n"
