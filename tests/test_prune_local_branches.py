"""[CI] `scripts/prune_local_branches.py` (REP-10): يحكم على الفرع بمحتواه، ولا يحذف إيداعاً غيرَ مدموجٍ أبداً.

كان الفحصُ القديم يثق باسم الرأس وحدَه («طلبٌ مدموجٌ بهذا الاسم» ← آمن) فيحذف فرعاً أُعيد استعمالُ اسمه وعليه إيداعاتٌ جديدةٌ لم تُدمج، ولا يرى
الدمجَ المسحوقَ في المقابل (فالفرعُ المدموجُ بالسحق ليس سلفاً لـmain) فيُبقي مئاتِ الفروع. فالاختباراتُ هنا تبني مستودعاً حقيقيّاً صغيراً
فيه كلُّ صنفٍ من الفروع، وتُثبت: (1) ما فيه إيداعٌ غيرُ مدموجٍ لا يُعدّ آمناً ولا يُحذف بـ--apply مهما كان اسمُه، (2) ما محتواه في main فعلاً
(دمجٌ مسحوقٌ، ولو تغيّر الملفُّ بعده) آمنٌ، (3) الوسمُ يسبق حذفَ ما لم يُدمج فيُسترجع بلا فقدان، (4) الحذفُ لا يتجاوز الطرفَ الذي حُكم عليه.
تُتخطّى حيث لا `git`. وهي في بوّابة الدمج (`pytest — تغطية`) لا في فحصٍ ليليٍّ وحدَه.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prune_local_branches.py"
WRAPPER = ROOT / "scripts" / "prune_local_branches.sh"

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="يحتاج git")

FLAGS = ["--no-fetch", "--no-gh"]
SAFE = {"SAFE_ANCESTOR", "SAFE_TAGGED", "SAFE_PR_MERGED", "SAFE_CONTENT_IN_MAIN"}


class World:
    """مستودعٌ عابرٌ فيه main وفروعٌ من كلّ صنف. التواريخُ قديمةٌ (10 أيّام) إلّا ما يُراد حديثاً."""

    def __init__(self, root: pathlib.Path, copy_of: pathlib.Path | None = None) -> None:
        self.root = root
        self.repo = root / "repo"
        if copy_of is not None:
            shutil.copytree(copy_of, self.repo)
        else:
            self.repo.mkdir()
        empty_config = root / "gitconfig"
        empty_config.write_text("", encoding="utf-8")
        self.env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
        }
        self.env.update(
            GIT_CONFIG_GLOBAL=str(empty_config),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@example.invalid",
        )
        if copy_of is None:
            self.git("init", "-q", "-b", "main")

    def git(self, *args: str, days_ago: float | None = None) -> str:
        env = dict(self.env)
        if days_ago is not None:
            when = dt.datetime.now(dt.UTC) - dt.timedelta(days=days_ago)
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.strftime(
                "%Y-%m-%dT%H:%M:%S+0000"
            )
        proc = subprocess.run(
            ["git", *args], cwd=self.repo, env=env, capture_output=True, text=True, encoding="utf-8"
        )
        assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
        return proc.stdout.strip()

    def commit(self, files: dict[str, str | None], message: str, days_ago: float = 10) -> str:
        """يكتب الملفّاتِ (وNone = حذف) ويودعها ويردّ رمزَ الإيداع."""
        for name, content in files.items():
            path = self.repo / name
            if content is None:
                self.git("rm", "-q", "--", name)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self.git("add", "--", name)
        self.git("commit", "-q", "-m", message, days_ago=days_ago)
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str, start: str = "main") -> None:
        self.git("checkout", "-q", "-b", name, start)

    def tip(self, name: str) -> str:
        return self.git("rev-parse", f"refs/heads/{name}")

    def exists(self, name: str) -> bool:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
        )
        return proc.returncode == 0

    def run(self, *args: str, prs: list[dict] | None = None) -> subprocess.CompletedProcess[str]:
        extra = list(FLAGS)
        if prs is not None:
            prs_file = self.root / "prs.json"
            prs_file.write_text(json.dumps(prs), encoding="utf-8")
            extra = ["--no-fetch", "--prs-json", str(prs_file)]
        return subprocess.run(
            [sys.executable, str(SCRIPT), *extra, *args],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )

    def report(self, *args: str, prs: list[dict] | None = None) -> dict:
        proc = self.run("--json", *args, prs=prs)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return json.loads(proc.stdout)


def build_template(root: pathlib.Path) -> tuple[World, list[dict]]:
    """يبني كلَّ صنفٍ من الفروع (بلا شجرة عمل) ويردّ (العالم، طلباتِ GitHub المفترضة). يُبنى مرّةً وتُنسخ منه العوالم."""
    w = World(root)
    w.commit(
        {"README.md": "r0", "a.txt": "a0", "keep.txt": "k0", "gone.txt": "g0"}, "c0", days_ago=20
    )

    # 1) إيداعٌ غيرُ مدموج — الصنفُ الذي لا يجوز حذفُه أبداً
    w.branch("feat/unmerged")
    w.commit({"u.txt": "عملٌ فريد"}, "unique work")

    # 2) دمجٌ عاديّ بتقدّم سريع ← سلفٌ لـmain
    w.branch("feat/ff-merged", "main")
    w.commit({"f.txt": "f"}, "ff work")

    # 3) دمجٌ مسحوق: إيداعان في الفرع يصيران إيداعاً واحداً في main، ثمّ يتغيّر الملفُّ بعده
    w.branch("feat/squashed", "main")
    w.commit({"s1.txt": "s1"}, "squash part 1")
    w.commit({"a.txt": "a-squashed"}, "squash part 2")

    # 4) دمجٌ جزئيّ: ملفٌّ واحدٌ فقط بلغ main
    w.branch("feat/partial", "main")
    w.commit({"p1.txt": "p1", "p2.txt": "p2"}, "two files")

    # 5) حذفُ ملفٍّ لم يبلغ main (main ما زال يحويه)
    w.branch("feat/deletes-kept-file", "main")
    w.commit({"keep.txt": None}, "delete keep")

    # 6) حذفُ ملفٍّ حذفه main فعلاً ← لا شيءَ يُفقد
    w.branch("feat/deletes-gone-file", "main")
    w.commit({"gone.txt": None}, "delete gone")

    # 7) مدموجٌ لكنّ طرفَه حديثٌ (خلال المهلة)
    w.branch("feat/recent-merged", "main")
    w.commit({"r.txt": "r"}, "recent work", days_ago=0.1)

    # 8) مدموجٌ ومفتوحٌ في شجرة عمل
    w.branch("feat/live", "main")
    w.commit({"l.txt": "l"}, "live work")

    # 9) غيرُ مدموجٌ وله طلبٌ مفتوح
    w.branch("feat/open-pr", "main")
    w.commit({"o.txt": "o"}, "open pr work")

    # 10) اسمٌ أُعيد استعمالُه: طلبٌ مدموجٌ برأسٍ قديم ثمّ إيداعٌ محلّيٌّ جديدٌ فوقه
    w.branch("feat/reused-name", "main")
    reused_head = w.commit({"first.txt": "first"}, "first pr work")
    w.commit({"second.txt": "لم يُدمج"}, "new local work after the merge")

    # 11) طلبٌ مدموجٌ برأسه (محتواه لا يطابق main حرفيّاً — دمجٌ بحلّ تعارض)
    w.branch("feat/pr-merged", "main")
    pr_merged_head = w.commit({"pm.txt": "pm"}, "pr merged work")

    # 12) طرفُه سلفٌ لرأس طلبٍ مدموج (الفرعُ المحلّيُّ متأخّرٌ عن رأس الطلب)
    w.branch("feat/pr-behind", "main")
    behind_tip = w.commit({"pb.txt": "pb"}, "behind tip")
    w.branch("feat/pr-behind-head", "feat/pr-behind")
    behind_head = w.commit({"pb2.txt": "pb2"}, "pr head")

    # 13) غيرُ مدموجٌ لكنّ عليه وسماً (أرشيفٌ سابق)
    w.branch("feat/tagged", "main")
    w.commit({"t.txt": "t"}, "tagged work")
    w.git("tag", "-a", "archive/feat-tagged-2026-01-01", "-m", "archive")

    # 14) غيرُ مدموجٌ وله نسخةٌ بعيدة، و15) لقطةُ نسخٍ احتياطيٍّ قبل إصلاح
    w.branch("feat/remote-copy", "main")
    remote_tip = w.commit({"rc.txt": "rc"}, "remote copy work")
    w.git("update-ref", "refs/remotes/origin/feat/remote-copy", remote_tip)
    w.branch("backup-2026-01-01-before-a-fix", "main")
    w.commit({"snapshot.txt": "x"}, "before fix")

    # ── main: يدمج ما دُمج، ثمّ يتغيّر ──
    w.git("checkout", "-q", "main")
    w.git("merge", "-q", "--ff-only", "feat/ff-merged")
    w.git("merge", "-q", "--squash", "feat/squashed")
    w.git("commit", "-q", "-m", "squash feat/squashed", days_ago=10)
    w.commit({"a.txt": "a-later"}, "main edits the squashed file later")  # الملفُّ لم يعد كما دُمج
    w.commit({"p1.txt": "p1"}, "only p1 of the partial branch reached main")
    w.commit({"gone.txt": None}, "main deletes gone.txt itself")
    w.git("merge", "-q", "--no-ff", "-m", "merge recent", "feat/recent-merged", days_ago=0.1)
    w.git("merge", "-q", "--no-ff", "-m", "merge live", "feat/live", days_ago=10)

    prs = [
        {
            "number": 1,
            "state": "OPEN",
            "headRefName": "feat/open-pr",
            "headRefOid": w.tip("feat/open-pr"),
        },
        {
            "number": 2,
            "state": "MERGED",
            "headRefName": "feat/reused-name",
            "headRefOid": reused_head,
        },
        {
            "number": 3,
            "state": "MERGED",
            "headRefName": "feat/pr-merged",
            "headRefOid": pr_merged_head,
        },
        {
            "number": 4,
            "state": "MERGED",
            "headRefName": "feat/pr-behind",
            "headRefOid": behind_head,
        },
        {
            "number": 5,
            "state": "MERGED",
            "headRefName": "feat/pr-behind-head",
            "headRefOid": behind_head,
        },
    ]
    assert behind_tip != behind_head
    return w, prs


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> tuple[World, list[dict]]:
    return build_template(tmp_path_factory.mktemp("prune-template"))


def fresh_world(template: tuple[World, list[dict]], root: pathlib.Path) -> tuple[World, list[dict]]:
    """نسخةٌ من القالب بشجرة عملٍ حيّةٍ على feat/live (تسجيلُ الشجرة يحمل مساراً مطلقاً فلا يُنسخ)."""
    source, prs = template
    w = World(root, copy_of=source.repo)
    w.git("worktree", "add", "-q", str(root / "live-tree"), "feat/live")
    return w, prs


@pytest.fixture(scope="module")
def world(template, tmp_path_factory: pytest.TempPathFactory) -> tuple[World, list[dict]]:
    return fresh_world(template, tmp_path_factory.mktemp("prune-world"))


@pytest.fixture(scope="module")
def verdicts(world: tuple[World, list[dict]]) -> dict[str, str]:
    w, prs = world
    return {r["branch"]: r["verdict"] for r in w.report(prs=prs)["records"]}


# ── 1) ما فيه إيداعٌ غيرُ مدموجٍ لا يُعدّ آمناً ──


@pytest.mark.parametrize(
    "branch",
    [
        "feat/unmerged",
        "feat/partial",
        "feat/deletes-kept-file",
        "feat/reused-name",
        "feat/remote-copy",
        "backup-2026-01-01-before-a-fix",
    ],
)
def test_a_branch_with_unmerged_work_is_never_safe(verdicts, branch):
    assert verdicts[branch] == "REVIEW", verdicts[branch]


def test_a_reused_branch_name_is_not_trusted_just_because_a_pr_with_that_name_merged(verdicts):
    """الحالةُ التي كان الفحصُ القديم يحذف فيها إيداعاً لم يُدمج: الاسمُ مدموجٌ والطرفُ لا."""
    assert verdicts["feat/reused-name"] == "REVIEW"


# ── 2) ما محتواه في main فعلاً آمنٌ — بأيّ طريقٍ دُمج ──


def test_a_fast_forward_merge_is_safe_as_an_ancestor(verdicts):
    assert verdicts["feat/ff-merged"] == "SAFE_ANCESTOR"


def test_a_squash_merged_branch_is_safe_by_content_even_after_main_edited_the_file(verdicts):
    """الدمجُ المسحوقُ لا يجعل الفرعَ سلفاً لـmain؛ وكلُّ نسخةٍ أنتجها الفرعُ مرّت في تاريخ main."""
    assert verdicts["feat/squashed"] == "SAFE_CONTENT_IN_MAIN"


def test_a_deletion_main_already_made_is_not_unmerged_work(verdicts):
    assert verdicts["feat/deletes-gone-file"] == "SAFE_CONTENT_IN_MAIN"


def test_a_merged_pr_whose_head_is_the_tip_or_contains_it_is_safe(verdicts):
    assert verdicts["feat/pr-merged"] == "SAFE_PR_MERGED"
    assert verdicts["feat/pr-behind"] == "SAFE_PR_MERGED"


def test_a_branch_carrying_an_archive_tag_is_safe(verdicts):
    assert verdicts["feat/tagged"] == "SAFE_TAGGED"


# ── 3) مَن لا يُمسّ ──


def test_a_branch_open_in_a_worktree_or_with_an_open_pr_is_kept(verdicts):
    assert verdicts["feat/live"] == "KEEP_LIVE"
    assert verdicts["feat/open-pr"] == "KEEP_OPEN_PR"


def test_a_merged_branch_whose_tip_is_within_the_grace_window_waits(world, verdicts):
    w, prs = world
    assert verdicts["feat/recent-merged"] == "GRACE"
    now_safe = {
        r["branch"]: r["verdict"] for r in w.report("--grace-hours", "0", prs=prs)["records"]
    }
    assert now_safe["feat/recent-merged"] == "SAFE_ANCESTOR"


def test_main_itself_is_never_a_candidate(verdicts):
    assert "main" not in verdicts


# ── 4) العرضُ لا يحذف، والحذفُ لا يتجاوز الآمن ──


def test_the_default_run_deletes_nothing(template, tmp_path):
    w, prs = fresh_world(template, tmp_path)
    before = w.git("for-each-ref", "refs/heads")

    proc = w.run(prs=prs)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert w.git("for-each-ref", "refs/heads") == before
    assert "تحتاج مراجعةً" in proc.stdout


def test_apply_deletes_only_what_is_safe_and_never_unmerged_grace_live_or_open_work(
    template, tmp_path
):
    w, prs = fresh_world(template, tmp_path)
    main_before = w.tip("main")
    report = w.report(prs=prs)
    safe = {r["branch"] for r in report["records"] if r["verdict"] in SAFE}
    kept = {r["branch"] for r in report["records"]} - safe
    assert safe and kept

    proc = w.run("--apply", prs=prs)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not any(w.exists(name) for name in safe), "بقي فرعٌ آمنٌ لم يُحذف"
    assert all(w.exists(name) for name in kept), "حُذف فرعٌ ليس آمناً"
    assert w.tip("main") == main_before
    for name in (
        "feat/unmerged",
        "feat/reused-name",
        "feat/recent-merged",
        "feat/live",
        "feat/open-pr",
    ):
        assert w.exists(name), name


def test_a_deleted_branch_can_be_restored_from_the_printed_hint(template, tmp_path):
    w, prs = fresh_world(template, tmp_path)
    squashed_tip = w.tip("feat/squashed")

    proc = w.run("--apply", prs=prs)

    assert f"git branch feat/squashed {squashed_tip}" in proc.stdout
    w.git("branch", "feat/squashed", squashed_tip)
    assert w.tip("feat/squashed") == squashed_tip


def test_apply_stops_at_the_batch_limit(template, tmp_path):
    w, prs = fresh_world(template, tmp_path)
    safe_count = sum(1 for r in w.report(prs=prs)["records"] if r["verdict"] in SAFE)
    assert safe_count > 2

    result = json.loads(w.run("--apply", "--json", "--max", "2", prs=prs).stdout)

    assert len(result["deleted"]) == 2
    assert len(result["refused"]) == safe_count - 2


# ── 5) الوسمُ يسبق حذفَ ما لم يُدمج ──


def test_archive_tags_unmerged_branches_then_apply_deletes_them_without_losing_the_work(
    template, tmp_path
):
    w, prs = fresh_world(template, tmp_path)
    unmerged_tip = w.tip("feat/unmerged")

    archived = json.loads(w.run("--archive", "--json", prs=prs).stdout)["archived"]

    tag = next(a["tag"] for a in archived if a["branch"] == "feat/unmerged")
    assert w.git("rev-parse", f"refs/tags/{tag}^{{commit}}") == unmerged_tip
    assert w.exists("feat/unmerged"), "--archive يَسِم ولا يحذف"
    after = {r["branch"]: r["verdict"] for r in w.report(prs=prs)["records"]}
    assert after["feat/unmerged"] == "SAFE_TAGGED"

    w.run("--apply", prs=prs)

    assert not w.exists("feat/unmerged")
    w.git("branch", "feat/unmerged", tag)
    assert w.tip("feat/unmerged") == unmerged_tip


def test_a_backup_snapshot_branch_is_not_tagged_automatically(template, tmp_path):
    """وسمٌ يُدفع (`git push --tags`) يُنشر في مستودعٍ عامّ؛ فلقطاتُ النسخ وما قبل الإصلاح تبقى قرارَ المالك."""
    w, prs = fresh_world(template, tmp_path)

    result = json.loads(w.run("--archive", "--json", prs=prs).stdout)

    assert "backup-2026-01-01-before-a-fix" in result["archive_skipped"]
    assert all(a["branch"] != "backup-2026-01-01-before-a-fix" for a in result["archived"])


# ── 6) الحذفُ لا يتجاوز الطرفَ الذي حُكم عليه ──


def _load_module():
    spec = importlib.util.spec_from_file_location("prune_local_branches", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_delete_refuses_when_the_tip_moved_after_the_verdict(tmp_path, monkeypatch):
    w = World(tmp_path)
    w.commit({"a.txt": "a"}, "c0", days_ago=20)
    w.branch("feat/moving")
    judged_tip = w.commit({"m.txt": "m"}, "judged", days_ago=10)
    w.commit({"m2.txt": "عملٌ أُضيف بعد الحكم"}, "added after the verdict", days_ago=9)
    w.git("checkout", "-q", "main")
    monkeypatch.chdir(w.repo)
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"):
        monkeypatch.setenv(key, w.env[key])

    module = _load_module()

    assert module.delete_branch("feat/moving", judged_tip) is False
    assert w.exists("feat/moving")
    assert module.delete_branch("feat/moving", w.tip("feat/moving")) is True
    assert not w.exists("feat/moving")


# ── 7) المقاييسُ (RK1..RK3) وسقفُ RD5 ──


def test_metrics_follow_the_roadmap_definitions(world):
    w, prs = world
    report = w.report(prs=prs)
    records = report["records"]
    metrics = report["metrics"]

    not_kept = [r for r in records if r["verdict"] not in ("KEEP_LIVE", "KEEP_OPEN_PR")]
    assert metrics["RK1"] == len(not_kept)
    single_copy = [r for r in records if r["verdict"] == "REVIEW" and not r["remote_copy"]]
    assert metrics["RK2_candidates"] == len(single_copy)
    assert any(r["branch"] == "feat/remote-copy" and r["remote_copy"] for r in records)
    assert metrics["RK3_candidates"] == 1, "شجرةُ feat/live الحيّةُ فرعُها مدموجٌ"
    assert metrics["review_ceiling"] == {
        "count": sum(1 for r in records if r["verdict"] == "REVIEW"),
        "max": 40,
        "exceeded": False,
    }


def test_the_review_ceiling_is_flagged_when_exceeded():
    module = _load_module()
    review = [module.Branch(f"b{i}", "0" * 40, 0, verdict=module.REVIEW) for i in range(41)]

    metrics = module.metrics(review, [], prs_known=True)

    assert metrics["review_ceiling"]["exceeded"] is True


# ── 8) المُشغِّلُ الذي يعرفه الجميع ──


@pytest.mark.skipif(
    not shutil.which("bash") or os.name == "nt",
    reason="المُشغِّلُ bash؛ على ويندوز يُجرَّب يدويّاً في Git Bash",
)
def test_the_shell_wrapper_runs_the_python_tool(template, tmp_path):
    w, _ = fresh_world(template, tmp_path)

    proc = subprocess.run(
        ["bash", str(WRAPPER), *FLAGS, "--json"],
        cwd=w.repo,
        env=w.env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["main_ref"] == "main"
