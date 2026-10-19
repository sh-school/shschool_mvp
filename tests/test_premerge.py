"""فحصُ premerge الموحَّد قبل «جاهزٌ للمعاينة» (W-20261016-020).

الخطرُ: أن يسقط في CI بعد الدفع ما كان يُكتشف محلّياً بثوانٍ (#1098: حارسان في test_preview_setup يرفضان `rm -rf`
و`--force-recreate` في scripts/preview.sh، ولا قاعدةَ في affected تربط ذلك السكربتَ بحارسيه)، وأن يُعدّ «نجاحاً» ما لم يُقَس.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("premerge", ROOT / "scripts" / "premerge.py")
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="لا git")

_ID = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.test",
}


def _g(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, **_ID},
        check=True,
    )
    return proc.stdout.strip()


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    _g(repo, "add", *files)
    _g(repo, "commit", "-q", "-m", message)


@pytest.fixture()
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _g(r, "init", "-q", "-b", "main")
    return r


def _proc(code: int, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)


# ── حالةُ #1098 المعاد إنتاجُها ─────────────────────────────────────


GUARD_TEST = '''from pathlib import Path


def test_the_script_never_deletes():
    """الحارس: لا `rm -rf` في scripts/preview.sh (مثل حارس test_preview_setup)."""
    text = Path("scripts/preview.sh").read_text(encoding="utf-8")
    assert "rm -rf" not in text
'''


@needs_git
def test_the_1098_failure_is_caught_before_ready(repo, monkeypatch):
    """سكربتٌ `.sh` يُعدَّل فيسقط حارسٌ يذكر مسارَه: affected لا قاعدةَ له، وcheck_references يكشفه فشلاً."""
    _commit(
        repo, {"scripts/preview.sh": "echo ok\n", "tests/test_preview_setup.py": GUARD_TEST}, "base"
    )
    _g(repo, "switch", "-q", "-c", "work")
    _commit(repo, {"scripts/preview.sh": 'rm -rf "$lock"\n'}, "break the guard")

    def run_pytest_in_repo(tests):
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *tests],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return (pm.OK, "") if proc.returncode == 0 else (pm.FAIL, proc.stdout[-300:])

    monkeypatch.setattr(
        pm, "_load_affected", lambda: SimpleNamespace(run_pytest=run_pytest_in_repo)
    )
    status, detail = pm.check_references("main", repo)
    assert status == pm.FAIL, detail
    assert "tests/test_preview_setup.py" in detail


@needs_git
def test_a_clean_change_to_the_same_script_passes_references(repo, monkeypatch):
    _commit(
        repo, {"scripts/preview.sh": "echo ok\n", "tests/test_preview_setup.py": GUARD_TEST}, "base"
    )
    _g(repo, "switch", "-q", "-c", "work")
    _commit(repo, {"scripts/preview.sh": "echo fine\n"}, "safe change")
    monkeypatch.setattr(
        pm, "_load_affected", lambda: SimpleNamespace(run_pytest=lambda tests: (pm.OK, ""))
    )
    assert pm.check_references("main", repo)[0] == pm.OK


@needs_git
def test_references_picks_only_tests_that_name_a_changed_file(repo):
    _commit(repo, {"scripts/a.sh": "a\n", "scripts/b.sh": "b\n"}, "base")
    _commit(
        repo,
        {"tests/test_a.py": "X = 'scripts/a.sh'\n", "tests/test_b.py": "X = 'scripts/b.sh'\n"},
        "tests",
    )
    assert pm.tests_mentioning(["scripts/a.sh"], repo) == ["tests/test_a.py"]
    assert (
        pm.tests_mentioning(["tests/test_a.py"], repo) == []
    )  # اختبارٌ معدَّلٌ يتولّاه affected لا هذا الفحص
    assert pm.tests_mentioning([], repo) == []


# ── غيرُ المقيس لا يُعدّ نجاحاً ─────────────────────────────────────


@pytest.mark.parametrize("fn", [pm.check_prepush, pm.check_affected])
def test_a_tool_that_cannot_run_is_unmeasured_not_ok(fn, monkeypatch):
    monkeypatch.setattr(pm, "_run", lambda cmd, cwd=None: _proc(3, "غير مقيس"))
    assert fn()[0] == pm.MISSING


@pytest.mark.parametrize("fn", [pm.check_prepush, pm.check_affected])
def test_a_failing_tool_is_a_failure_and_a_passing_one_is_ok(fn, monkeypatch):
    monkeypatch.setattr(pm, "_run", lambda cmd, cwd=None: _proc(1, "x"))
    assert fn()[0] == pm.FAIL
    monkeypatch.setattr(pm, "_run", lambda cmd, cwd=None: _proc(0))
    assert fn()[0] == pm.OK


@needs_git
def test_open_prs_are_unmeasured_without_gh(repo, monkeypatch):
    _commit(repo, {"a.txt": "a\n"}, "base")
    _g(repo, "switch", "-q", "-c", "work")
    _commit(repo, {"b.txt": "b\n"}, "work")
    monkeypatch.setattr(pm, "which", lambda name: None)
    assert pm.check_prs("main", repo)[0] == pm.MISSING


@needs_git
def test_open_prs_are_unmeasured_when_gh_fails(repo, monkeypatch):
    _commit(repo, {"a.txt": "a\n"}, "base")
    _g(repo, "switch", "-q", "-c", "work")
    _commit(repo, {"b.txt": "b\n"}, "work")
    monkeypatch.setattr(pm, "which", lambda name: "/usr/bin/gh")
    real_run = pm._run
    monkeypatch.setattr(
        pm,
        "_run",
        lambda cmd, cwd=None: _proc(1, "", "auth") if cmd[0] == "gh" else real_run(cmd, cwd),
    )
    assert pm.check_prs("main", repo)[0] == pm.MISSING


@needs_git
def test_a_missing_base_is_unmeasured_for_references_and_prs(repo):
    _commit(repo, {"a.txt": "a\n"}, "base")
    assert pm.check_references("origin/none", repo)[0] == pm.MISSING
    assert pm.check_prs("origin/none", repo)[0] == pm.MISSING


@needs_git
def test_a_git_that_cannot_simulate_the_merge_is_unmeasured(repo, monkeypatch):
    _commit(repo, {"a.txt": "a\n"}, "base")
    real_git = pm._git
    monkeypatch.setattr(
        pm,
        "_git",
        lambda *a, cwd=None: (
            _proc(129, "", "usage: git merge-tree")
            if a[0] == "merge-tree"
            else real_git(*a, cwd=cwd)
        ),
    )
    assert pm.check_merge("main", repo)[0] == pm.MISSING


# ── محاكاةُ الدمج ─────────────────────────────────────────────────


@needs_git
def test_a_clean_merge_simulation_is_ok_and_touches_nothing(repo):
    _commit(repo, {"a.txt": "a\n", "b.txt": "b\n"}, "base")
    _g(repo, "switch", "-q", "-c", "work")
    _commit(repo, {"a.txt": "a2\n"}, "work")
    _g(repo, "switch", "-q", "main")
    _commit(repo, {"b.txt": "b2\n"}, "main moves")
    _g(repo, "switch", "-q", "work")
    head, status_before = _g(repo, "rev-parse", "HEAD"), _g(repo, "status", "--porcelain")
    assert pm.check_merge("main", repo)[0] == pm.OK
    assert _g(repo, "rev-parse", "HEAD") == head
    assert _g(repo, "status", "--porcelain") == status_before
    assert _g(repo, "branch", "--show-current") == "work"


@needs_git
def test_a_conflicting_merge_simulation_fails_and_names_the_file(repo):
    _commit(repo, {"notes.txt": "one\ntwo\nthree\n"}, "base")
    _g(repo, "switch", "-q", "-c", "work")
    _commit(repo, {"notes.txt": "one\nWORK\nthree\n"}, "work")
    _g(repo, "switch", "-q", "main")
    _commit(repo, {"notes.txt": "one\nMAIN\nthree\n"}, "main moves")
    _g(repo, "switch", "-q", "work")
    status, detail = pm.check_merge("main", repo)
    assert status == pm.FAIL
    assert "notes.txt" in detail


# ── تداخلُ الطلبات المفتوحة ───────────────────────────────────────


def test_overlap_with_an_open_pr_is_a_warning_not_a_failure():
    prs = [
        {"number": 7, "headRefOid": "other", "files": [{"path": "core/a.py"}, {"path": "z.py"}]},
        {"number": 8, "headRefOid": "other2", "files": [{"path": "unrelated.py"}]},
    ]
    status, detail = pm.overlap_status(["core/a.py", "core/b.py"], prs, "me")
    assert status == pm.WARN
    assert "#7" in detail and "core/a.py" in detail and "#8" not in detail


def test_no_overlap_is_ok_and_the_own_pr_is_ignored():
    prs = [{"number": 7, "headRefOid": "me", "files": [{"path": "core/a.py"}]}]
    assert pm.overlap_status(["core/a.py"], prs, "me")[0] == pm.OK


# ── الحكمُ ووضعُ الظلّ والبصمة ──────────────────────────────────────


def _res(**statuses):
    return {k: {"status": v, "detail": "", "seconds": 0.1} for k, v in statuses.items()}


def test_shadow_mode_never_blocks_whatever_fails():
    assert pm.verdict(_res(a=pm.FAIL, b=pm.MISSING), enforce=False) == 0


def test_enforce_fails_on_failure_then_unmeasured_and_ignores_warnings():
    assert pm.verdict(_res(a=pm.OK, b=pm.FAIL, c=pm.MISSING), enforce=True) == 1
    assert pm.verdict(_res(a=pm.OK, c=pm.MISSING), enforce=True) == 3
    assert pm.verdict(_res(a=pm.OK, c=pm.WARN), enforce=True) == 0


def test_the_fingerprint_is_deterministic_and_tracks_head_and_results():
    a = pm.fingerprint("abc", _res(x=pm.OK, y=pm.FAIL))
    assert a == pm.fingerprint("abc", _res(y=pm.FAIL, x=pm.OK))
    assert a != pm.fingerprint("abd", _res(x=pm.OK, y=pm.FAIL))
    assert a != pm.fingerprint("abc", _res(x=pm.OK, y=pm.OK))


def _stub_all(monkeypatch, **by_name):
    runners = {name: (lambda base, cwd, s=by_name.get(name, pm.OK): (s, "")) for name in pm.CHECKS}
    monkeypatch.setattr(pm, "RUNNERS", runners)
    monkeypatch.setattr(pm, "_log_shadow", lambda *a, **k: None)


def test_main_in_shadow_mode_prints_what_would_block_but_exits_zero(monkeypatch, capsys):
    _stub_all(monkeypatch, affected=pm.FAIL)
    monkeypatch.delenv("PREMERGE_ENFORCE", raising=False)
    assert pm.main([]) == 0
    out = capsys.readouterr().out
    assert "وضعُ الظلّ لم يحجب" in out and "✘" in out


def test_main_enforced_by_flag_or_env_exits_nonzero(monkeypatch):
    _stub_all(monkeypatch, affected=pm.FAIL)
    assert pm.main(["--enforce"]) == 1
    monkeypatch.setenv("PREMERGE_ENFORCE", "1")
    assert pm.main([]) == 1


def test_main_reports_unmeasured_without_calling_it_ok(monkeypatch, capsys):
    _stub_all(monkeypatch, merge=pm.MISSING)
    assert pm.main(["--enforce"]) == 3
    out = capsys.readouterr().out
    assert "غيرُ مقيس" in out and "كلُّ ما قيس نجح" not in out


def test_main_prints_every_check_its_time_and_one_fingerprint_line(monkeypatch, capsys):
    _stub_all(monkeypatch)
    pm.main([])
    out = capsys.readouterr().out
    assert all(pm.TITLES[name] in out for name in pm.CHECKS)
    assert out.count("بصمة premerge:") == 1 and "الزمنُ الكلّيّ" in out


def test_skip_leaves_a_check_out_and_an_unknown_name_is_refused(monkeypatch, capsys):
    _stub_all(monkeypatch)
    pm.main(["--skip", "prs"])
    assert pm.TITLES["prs"] not in capsys.readouterr().out.split("=== النتيجة ===")[1]
    assert pm.main(["--skip", "nope"]) == 2


def test_dry_run_runs_nothing(monkeypatch, capsys):
    monkeypatch.setattr(
        pm, "RUNNERS", {n: (lambda *a: pytest.fail("لا يُشغَّل شيء")) for n in pm.CHECKS}
    )
    assert pm.main(["--dry-run"]) == 0
    assert pm.TITLES["merge"] in capsys.readouterr().out


def test_the_makefile_target_exists_and_runs_the_script_in_shadow_mode():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "premerge:\n\tpython scripts/premerge.py\n" in makefile.replace("\r\n", "\n")
    assert " premerge " in makefile.split(".PHONY:")[1].split("\n\n")[0] + " "
