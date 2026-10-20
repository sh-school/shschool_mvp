"""حارسُ تصادم أرقام الهجرات (W-20261019-002): تصادم، لا تصادم، تصادم مع main بعد الأساس، غياب gh."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_migration_collisions", Path("scripts/check_migration_collisions.py")
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

MINE = ["operations/migrations/0007_exit_permit.py", "docs/x.md"]


def _patch(monkeypatch, mine, prs, main_added=(), branch="w-mine", head="aaa"):
    monkeypatch.setattr(guard, "branch_added_paths", lambda base: (list(mine), "base"))
    monkeypatch.setattr(guard, "main_added_since", lambda base, mb: list(main_added))
    monkeypatch.setattr(guard, "open_pull_requests", lambda: prs)
    monkeypatch.setattr(guard, "current_branch_and_head", lambda: (branch, head))


def _pr(number, branch, files, head="zzz"):
    return f"#{number} ({branch})", {"head": head, "branch": branch, "files": files}


def test_same_number_in_same_app_as_an_open_pr_fails_and_names_it(monkeypatch):
    label, info = _pr(1124, "claude/other", ["operations/migrations/0007_other.py"])
    _patch(monkeypatch, MINE, {label: info})
    code, message = guard.run()
    assert code == guard.COLLISION
    assert "#1124" in message and "0007_exit_permit.py" in message and "0007_other.py" in message


def test_a_different_number_or_app_passes(monkeypatch):
    prs = dict(
        [
            _pr(1, "a", ["operations/migrations/0008_x.py"]),
            _pr(2, "b", ["core/migrations/0007_y.py"]),
        ]
    )
    _patch(monkeypatch, MINE, prs)
    assert guard.run()[0] == guard.OK


def test_a_collision_with_main_after_the_base_fails(monkeypatch):
    _patch(monkeypatch, MINE, {}, main_added=["operations/migrations/0007_landed.py"])
    code, message = guard.run()
    assert code == guard.COLLISION and "origin/main" in message


def test_my_own_pr_is_excluded_by_branch_or_head(monkeypatch):
    by_branch = dict([_pr(5, "claude/w-mine", ["operations/migrations/0007_exit_permit_v2.py"])])
    by_head = dict([_pr(6, "x", ["operations/migrations/0007_z.py"], head="aaa")])
    for prs in (by_branch, by_head):
        _patch(monkeypatch, MINE, prs)
        assert guard.run()[0] == guard.OK


def test_the_same_file_is_not_a_collision(monkeypatch):
    prs = dict([_pr(7, "stacked", ["operations/migrations/0007_exit_permit.py"])])
    _patch(monkeypatch, MINE, prs)
    assert guard.run()[0] == guard.OK


def test_no_migration_in_the_branch_needs_no_network(monkeypatch):
    _patch(monkeypatch, ["docs/x.md"], {})
    monkeypatch.setattr(guard, "open_pull_requests", lambda: 1 / 0)
    assert guard.run()[0] == guard.OK


def test_missing_gh_is_not_measured_and_never_a_silent_pass(monkeypatch):
    _patch(monkeypatch, MINE, {})

    def no_gh():
        raise guard.NotMeasuredError("gh غير مثبَّت")

    monkeypatch.setattr(guard, "open_pull_requests", no_gh)
    code, message = guard.run()
    assert code == guard.MISSING and "غير مقيس" in message


def test_run_helper_reports_missing_binary(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(guard.subprocess, "run", boom)
    try:
        guard._run(["gh", "x"])
    except guard.NotMeasuredError:
        return
    raise AssertionError("كان يجب أن يُرفع NotMeasuredError")
