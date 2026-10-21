"""قائمةُ الخارطة المعلَّقة بعد النشر (W-20261010-021): استخراجُ الرموز، تساوي الأثر، طلبٌ بلا بند، وشروطُ الوركفلو."""

import importlib.util
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_roadmap_queue", ROOT / "scripts" / "ci_roadmap_queue.py"
)
rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rq)

REPO = "o/r"
CUR, PREV = "c" * 40, "a" * 40


def pr(n, title, body="", labels=(), merged=True):
    return {
        "number": n,
        "title": title,
        "body": body,
        "labels": [{"name": x} for x in labels],
        "merged_at": "2026-10-20T10:00:00Z" if merged else None,
    }


class FakeApi:
    def __init__(self, prs_by_commit, comments=(), issues=()):
        self.prs_by_commit, self.comments, self.issues, self.calls = (
            prs_by_commit,
            list(comments),
            list(issues),
            [],
        )

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path.startswith(f"repos/{REPO}/deployments?"):
            return [{"id": 2, "sha": CUR}, {"id": 1, "sha": PREV}]
        if path.endswith("/statuses?per_page=1"):
            return [{"state": "success"}]
        if "/compare/" in path:
            return {"commits": [{"sha": k} for k in self.prs_by_commit]}
        if path.endswith("/pulls"):
            return self.prs_by_commit[path.split("/")[-2]]
        if "/issues?state=open" in path:
            return self.issues
        if path.endswith("/comments?per_page=100"):
            return self.comments
        if method == "POST" and path.endswith("/issues"):
            return {"number": 77}
        return None

    def posts(self, suffix):
        return [c for c in self.calls if c[0] == "POST" and c[1].endswith(suffix)]


def test_extract_cards_from_realistic_body():
    body = "W-20261010-021: وصف\n\nاعتُمد من المالك على 8500 — الرأس abcd1234\nيشمل N-20261001-004 وW-20261010-021"
    assert rq.extract_cards(body) == ["W-20261010-021", "N-20261001-004"]
    assert rq.extract_cards("") == [] and rq.extract_cards(None) == []


def test_labels_every_merged_pr_and_posts_one_grouped_comment():
    api = FakeApi(
        {
            "k1": [pr(10, "W-20261010-021: أ")],
            "k2": [
                pr(11, "بلا رمز"),
                pr(12, "ج", labels=[rq.SYNCED]),
                pr(13, "غير مدموج", merged=False),
            ],
        }
    )
    out = rq.run(api, REPO, CUR)
    assert "وُسم 2" in out
    assert [c[1] for c in api.posts("/labels")] == [
        f"repos/{REPO}/issues/10/labels",
        f"repos/{REPO}/issues/11/labels",
    ]
    body = api.posts("/comments")[0][2]["body"]
    assert len(api.posts("/comments")) == 1 and rq.marker(CUR) in body
    assert (
        "W-20261010-021" in body and "بلا بند" in body and "#12" not in body and "#13" not in body
    )


def test_rerun_on_same_deploy_repeats_nothing():
    api = FakeApi(
        {"k": [pr(10, "W-20261010-021: أ", labels=[rq.PENDING])]},
        comments=[{"body": rq.marker(CUR)}],
        issues=[{"number": 77, "title": rq.ISSUE_TITLE}],
    )
    assert "لا تكرار" in rq.run(api, REPO, CUR)
    assert (
        api.posts("/labels") == [] and api.posts("/comments") == [] and api.posts("/issues") == []
    )


def test_no_new_prs_does_nothing_and_no_prior_deploy_is_reported():
    api = FakeApi({"k": [pr(5, "x", labels=[rq.SYNCED])]})
    assert "لا طلباتٍ" in rq.run(api, REPO, CUR) and api.posts("/comments") == []
    assert "لا نشرَ ناجحاً سابقاً" in rq.run(lambda *a, **k: [], REPO, CUR)


def test_workflow_gates_environment_creator_and_minimal_permissions():
    wf = yaml.safe_load((ROOT / ".github/workflows/roadmap-queue.yml").read_text(encoding="utf-8"))
    cond = wf["jobs"]["queue"]["if"]
    assert (
        "state == 'success'" in cond
        and "shschool_mvp / production" in cond
        and "railway-app[bot]" in cond
    )
    assert wf["permissions"] == {"pull-requests": "write", "issues": "write"}
    assert set(wf[True]) == {"deployment_status"}  # YAML يقرأ `on` منطقياً
