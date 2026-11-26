"""قائمةُ الخارطة المعلَّقة بعد النشر (W-20261010-021): استخراجُ الرموز، تساوي الأثر، طلبٌ بلا بند، وشروطُ الوركفلو."""

import importlib.util
import pathlib
from urllib.parse import parse_qs, urlsplit

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_roadmap_queue", ROOT / "scripts" / "ci_roadmap_queue.py"
)
rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rq)

REPO = "o/r"
CUR, PREV, MARKED = "c" * 40, "a" * 40, "b" * 40
QUEUE = [{"number": 77, "title": "قائمة الخارطة المعلَّقة (roadmap-pending)"}]


def pr(n, title, body="", labels=(), merged=True):
    return {
        "number": n,
        "title": title,
        "body": body,
        "labels": [{"name": x} for x in labels],
        "merged_at": "2026-10-20T10:00:00Z" if merged else None,
    }


class FakeApi:
    def __init__(self, prs_by_commit, comments=(), issues=(), statuses=("success",)):
        self.prs_by_commit, self.comments, self.issues, self.statuses, self.calls = (
            prs_by_commit,
            list(comments),
            list(issues),
            list(statuses),
            [],
        )

    @staticmethod
    def page(items, path):
        """شريحةُ الصفحة المطلوبة كما يقسّمها GitHub (per_page وpage)."""
        query = parse_qs(urlsplit(path).query)
        size, number = int(query["per_page"][0]), int(query.get("page", ["1"])[0])
        return items[(number - 1) * size : number * size]

    def compared(self):
        return [c[1].split("/compare/")[1] for c in self.calls if "/compare/" in c[1]]

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path.startswith(f"repos/{REPO}/deployments?"):
            return [{"id": 2, "sha": CUR}, {"id": 1, "sha": PREV}]
        if "/statuses?" in path:
            return self.page([{"state": s} for s in self.statuses], path)
        if "/compare/" in path:
            return {"commits": self.page([{"sha": k} for k in self.prs_by_commit], path)}
        if path.endswith("/pulls"):
            return self.prs_by_commit[path.split("/")[-2]]
        if "/issues?state=open" in path:
            return self.issues
        if method == "GET" and "/comments?" in path:
            return self.page(self.comments, path)
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


def test_previous_deploy_now_inactive_still_counts_as_successful():
    api = FakeApi({"k": [pr(10, "أ")]}, statuses=("inactive", "success", "in_progress"))
    assert "وُسم 1" in rq.run(api, REPO, CUR)
    assert api.compared()[0].startswith(f"{PREV}...{CUR}")


def test_earlier_deploys_without_a_base_raise_a_visible_warning():
    api = FakeApi({"k": [pr(10, "أ")]}, statuses=("failure",))
    assert rq.run(api, REPO, CUR).startswith("::warning::")
    assert api.compared() == [] and api.posts("/comments") == []


def test_base_is_the_last_marker_across_all_comment_pages():
    comments = [{"body": rq.marker("d" * 40)}] + [{"body": "نقاش"}] * 100
    comments.append({"body": rq.marker(MARKED) + "\nقائمة"})
    api = FakeApi({"k": [pr(10, "أ")]}, comments=comments, issues=QUEUE, statuses=("failure",))
    assert "وُسم 1" in rq.run(api, REPO, CUR)
    assert api.compared()[0].startswith(f"{MARKED}...{CUR}")
    assert not [c for c in api.calls if "/deployments" in c[1]]
    assert api.posts("/issues") == []


def test_rerun_finds_its_marker_beyond_the_first_comment_page():
    comments = [{"body": "نقاش"}] * 100 + [{"body": rq.marker(CUR)}]
    api = FakeApi({"k": [pr(10, "أ")]}, comments=comments, issues=QUEUE)
    assert "لا تكرار" in rq.run(api, REPO, CUR)
    assert [c for c in api.calls if c[0] == "POST"] == []


def test_second_run_after_posting_repeats_nothing():
    api = FakeApi({"k": [pr(10, "أ")]}, issues=QUEUE)
    rq.run(api, REPO, CUR)
    api.comments.append(api.posts("/comments")[0][2])
    assert "لا تكرار" in rq.run(api, REPO, CUR)
    assert len(api.posts("/comments")) == 1 and len(api.posts("/labels")) == 1


def test_compare_beyond_250_commits_reads_every_page():
    api = FakeApi({f"k{i}": [pr(i, "أ")] for i in range(1, 302)})
    assert "وُسم 301" in rq.run(api, REPO, CUR)
    assert len(api.compared()) == 4


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
