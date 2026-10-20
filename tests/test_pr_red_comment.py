"""تعليقُ الأحمر الحقيقيّ (W-20261003-009): الملغى ليس أحمر، تعليقٌ واحدٌ محدَّث، تنقيةُ سطر الخطأ، وشروطُ الوركفلو."""

import importlib.util
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_pr_red_comment", ROOT / "scripts" / "ci_pr_red_comment.py"
)
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

REPO, SHA = "o/r", "a" * 40
BOT = {"login": "github-actions[bot]"}


def cr(name, conclusion="success", status="completed", at="2026-10-20T10:00:00Z", run=1, job=9):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "completed_at": at,
        "details_url": f"https://github.com/o/r/actions/runs/{run}/job/{job}",
        "app": {"slug": "github-actions"},
    }


class FakeApi:
    def __init__(self, runs, comments=(), state="open", head=SHA, title="W-20261003-009: x"):
        self.runs, self.comments, self.calls = runs, list(comments), []
        self.pr = {
            "state": state,
            "head": {"sha": head, "ref": "claude/x"},
            "title": title,
            "body": "",
        }

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.endswith("/pulls/5"):
            return self.pr
        if "/check-runs" in path:
            return {"check_runs": self.runs}
        if path.endswith("/comments?per_page=100"):
            return self.comments
        return None

    def writes(self):
        return [c for c in self.calls if c[0] in ("POST", "PATCH")]


def logs(text="x\tstep\t2026-10-20T10:00:00Z FAILED tests/test_a.py::t - AssertionError"):
    return lambda run_id: text


def test_cancelled_is_not_red_and_superseded_cancel_is_ignored():
    api = FakeApi(
        [
            cr("lint", "cancelled", at="2026-10-20T09:00:00Z"),
            cr("lint", "success", at="2026-10-20T09:30:00Z"),
            cr("tests", "cancelled"),
        ]
    )
    assert "لا شيء" in pr.run(api, logs(), REPO, 5, SHA)
    assert api.writes() == []


def test_real_red_posts_one_comment_with_check_error_and_card():
    api = FakeApi([cr("tests (shard 2)", "failure"), cr("lint", "success")])
    out = pr.run(api, logs(), REPO, 5, SHA)
    assert "نُشر" in out
    method, path, payload = api.writes()[0]
    assert method == "POST" and path.endswith("/issues/5/comments")
    body = payload["body"]
    assert pr.MARKER in body and "tests (shard 2)" in body and "AssertionError" in body
    assert "W-20261003-009" in body and "lint" not in body


def test_second_run_updates_the_same_comment_and_never_duplicates():
    existing = [{"id": 77, "user": BOT, "body": pr.MARKER + "\nقديم"}]
    api = FakeApi([cr("tests", "failure")], comments=existing)
    assert "حُدِّث" in pr.run(api, logs(), REPO, 5, SHA)
    assert [w[0] for w in api.writes()] == ["PATCH"]
    # تكرارُ التشغيل نفسِه بالنصّ نفسِه لا يكتب
    same = FakeApi(
        [cr("tests", "failure")],
        comments=[{"id": 77, "user": BOT, "body": api.writes()[0][2]["body"]}],
    )
    assert "لا تكرار" in pr.run(same, logs(), REPO, 5, SHA)
    assert same.writes() == []


def test_recovery_updates_existing_comment_but_waits_for_pending():
    existing = [{"id": 77, "user": BOT, "body": pr.MARKER + "\n⛔"}]
    green = FakeApi([cr("tests", "success")], comments=existing)
    assert "حُدِّث" in pr.run(green, logs(), REPO, 5, SHA)
    assert "تعافى" in green.writes()[0][2]["body"]
    pending = FakeApi(
        [cr("tests", "success"), cr("e2e", None, status="in_progress")], comments=existing
    )
    assert "قيدَ التشغيل" in pr.run(pending, logs(), REPO, 5, SHA)
    assert pending.writes() == []


def test_closed_pr_and_advanced_head_are_skipped():
    assert "غيرُ مفتوح" in pr.run(
        FakeApi([cr("t", "failure")], state="closed"), logs(), REPO, 5, SHA
    )
    stale = FakeApi([cr("t", "failure")], head="b" * 40)
    assert "تقدّم" in pr.run(stale, logs(), REPO, 5, SHA) and stale.writes() == []


def test_error_text_is_sanitized_as_untrusted_data():
    evil = "x\ts\t2026 error: `rm` @octocat <img src=x> | pwn\x1b[31m"
    api = FakeApi([cr("tests", "failure")])
    pr.run(api, logs(evil), REPO, 5, SHA)
    body = api.writes()[0][2]["body"]
    assert "`rm`" not in body and "<img" not in body and "\x1b" not in body
    assert "@octocat" not in body  # الإشارةُ بحرفٍ صفريّ العرض لا تُنبّه أحداً


def test_workflow_runs_from_base_with_minimal_permissions_and_no_pr_code():
    wf = yaml.safe_load((ROOT / ".github/workflows/pr-red-comment.yml").read_text(encoding="utf-8"))
    assert set(wf[True]) == {"workflow_run"}
    assert wf["permissions"] == {
        "contents": "read",
        "pull-requests": "write",
        "checks": "read",
        "actions": "read",
    }
    job = wf["jobs"]["comment"]
    assert "pull_request" in job["if"]
    checkout = job["steps"][0]
    assert not {"ref", "repository"} & set(
        checkout.get("with", {})
    ), "لا ref لرأس الطلب: يُفحص فرعُ الأساس وحدَه"
    assert checkout["with"]["persist-credentials"] is False


def test_human_comment_with_marker_is_never_edited():
    human = [{"id": 5, "user": {"login": "attacker"}, "body": pr.MARKER + " x"}]
    api = FakeApi([cr("tests", "failure")], comments=human)
    pr.run(api, logs(), REPO, 5, SHA)
    assert [w[0] for w in api.writes()] == ["POST"]


def test_log_is_read_only_for_own_repo_github_actions_job_and_per_job():
    seen = []

    def reader(job_id):
        seen.append(job_id)
        return f"x	s	2026 error: in job {job_id}"

    foreign = cr("a", "failure")
    foreign["details_url"] = "https://evil.example/o/r/actions/runs/1/job/7"
    other_repo = cr("b", "failure")
    other_repo["details_url"] = "https://github.com/x/y/actions/runs/1/job/8"
    other_app = cr("c", "failure")
    other_app["app"] = {"slug": "evil"}
    api = FakeApi(
        [foreign, other_repo, other_app, cr("d", "failure", job=11), cr("e", "failure", job=12)]
    )
    pr.run(api, reader, REPO, 5, SHA)
    assert seen == ["11", "12"]
    body = api.writes()[0][2]["body"]
    assert "in job 11" in body and "in job 12" in body


def test_check_name_is_inline_code_and_secrets_are_redacted():
    api = FakeApi([cr("[click](https://evil.example)", "failure")])
    url = "postgres://u:S3cr3t@db"  # pragma: allowlist secret
    line = "x	s	2026 error: " + url + " ghp_" + "a" * 24
    pr.run(api, logs(line), REPO, 5, SHA)
    body = api.writes()[0][2]["body"]
    assert "`[click](https://evil.example)`" in body
    assert "S3cr3t" not in body and "ghp_" not in body
