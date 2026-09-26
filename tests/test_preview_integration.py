"""[التشغيل] التكاملُ في المعاينة المركزيّة: main + ما أودعته الجلساتُ ولم يُدمج (قرارُ المالك 2026-09-26).

المعاينةُ تعرض الآن `main` مضموماً إليه رأسُ كلّ شجرةِ جلسةٍ (ما أُودع في فرعها) ليرى المالكُ عملَ الجلسات
مجتمعاً قبل دمجه — `scripts/preview.sh` بـ`git merge-tree` و`git commit-tree` وحدَهما: لا تُفتح شجرةٌ ولا يُبدَّل فرعٌ.
ولأنّها تعمل بلا مراقبةٍ كلَّ دقيقة، يُحرس هنا ما لو اختلّ أسقط المعاينةَ أو أصاب جلسةً:

  - فرعٌ يتعارض، أو تصادم ترقيمُ هجرته هجرةً سابقة (فيسقط migrate)، أو يعدّل آلةَ المعاينة نفسَها،
    أو خمل أياماً: يُتخطّى ويُذكر — ولا يُسقط غيرَه؛
  - المدخلاتُ نفسُها تُنتج الإيداعَ نفسَه (وإلّا أُعيد إنشاءُ الخادم كلَّ دقيقة بلا تغيّر)؛
  - لا يتغيّر رأسٌ ولا فرعٌ ولا ملفٌّ في أيّ شجرةٍ (تُقارَن قبلُ وبعدُ)؛
  - قاعدةُ المعاينة لا تحمل هجرةً ليست في الشجرة المعروضة (حادثةُ 2026-09-11): تُنشأ قاعدةٌ بجيلٍ أعلى.

تُبنى هنا مستودعاتٌ صغيرةٌ في مجلّدٍ مؤقّتٍ وتُستدعى دوالُّ السكربت بـ`source` — بلا docker ولا شبكة.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preview.sh"
# المسارُ المحلولُ لا الاسمُ: على ويندوز يجد `bash` الاسمُ المجرّدُ أوّلاً في System32 (WSL) لا Git Bash.
BASH = shutil.which("bash") or "bash"


def _git_version() -> tuple[int, int]:
    if shutil.which("git") is None:
        return (0, 0)
    out = subprocess.run(
        ["git", "--version"], capture_output=True, encoding="utf-8", check=False
    ).stdout
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


pytestmark = [
    pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash في هذه البيئة"),
    pytest.mark.skipif(_git_version() < (2, 38), reason="merge-tree --write-tree يلزمه git 2.38"),
]

_ID = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(cwd: Path, *args: str, when: int | None = None) -> str:
    env = {**os.environ, **_ID}
    if when is not None:
        stamp = f"{when} +0000"
        env.update({"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Sandbox:
    """مستودعٌ فيه main ومعاينةٌ (`main-preview`) وشجراتُ جلساتٍ متنوّعةٌ الأحوال."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.repo = base / "repo"
        self.wt = base / "wt"
        self.preview = self.wt / "main-preview"
        self.repo.mkdir()
        self.wt.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _write(self.repo / "notes.txt", "one\ntwo\nthree\n")
        _write(self.repo / "app" / "migrations" / "0001_initial.py", "# 1\n")
        _write(self.repo / "app" / "migrations" / "0002_base.py", "# 2\n")
        _write(self.repo / "scripts" / "preview.sh", "# machinery\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD")

        now = int(time.time())
        self._branch("a", {"a.txt": "a\n"})
        self._branch("b", {"b.txt": "b\n"})
        self._branch("conflict", {"notes.txt": "one\nCONFLICT\nthree\n"})
        self._branch("migclash", {"app/migrations/0003_clash.py": "# clash\n"})
        self._branch("machinery", {"scripts/preview.sh": "# changed machinery\n"})
        self._branch("stale", {"stale.txt": "s\n"}, when=now - 10 * 86400)
        self._branch("squashed", {"s.txt": "same\n"})
        # اثنان يضيفان الملفَّ نفسَه بمحتوىً مختلف: لا يتعارضان مع main بل معاً (الأقدمُ يدخل).
        self._branch("c1", {"shared.txt": "from c1\n"}, when=now - 2 * 3600)
        self._branch("c2", {"shared.txt": "from c2\n"})
        # فرعٌ بلا شيءٍ جديد: رأسُه سلفُ main بعد تقدّمه.
        _git(
            self.repo,
            "worktree",
            "add",
            "-q",
            "-b",
            "merged",
            str(self.wt / "merged"),
            self.base_sha,
        )

        # main يتقدّم: يعدّل السطرَ نفسَه الذي عدّله conflict، ويأخذ رقمَ الهجرة 0003، ويضيف s.txt كما في squashed.
        _write(self.repo / "notes.txt", "one\nTWO-main\nthree\n")
        _write(self.repo / "app" / "migrations" / "0003_main.py", "# 3 main\n")
        _write(self.repo / "s.txt", "same\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "main advances")
        self.main = _git(self.repo, "rev-parse", "main")

        _git(self.repo, "worktree", "add", "-q", "--detach", str(self.preview), "main")
        self.state = Path(_git(self.preview, "rev-parse", "--absolute-git-dir")) / "preview-state"

    def _branch(self, name: str, files: dict[str, str], when: int | None = None) -> None:
        tree = self.wt / name
        _git(self.repo, "worktree", "add", "-q", "-b", name, str(tree), self.base_sha)
        for rel, text in files.items():
            _write(tree / rel, text)
        _git(tree, "add", "-A")
        _git(tree, "commit", "-q", "-m", name, when=when)

    # ── ما يجري في bash ──────────────────────────────────────────
    def bash(self, body: str, **env: str) -> subprocess.CompletedProcess[str]:
        program = f'set -eu\nsource "{SCRIPT.as_posix()}"\nset +e\n{body}\n'
        full_env = {
            **os.environ,
            **_ID,
            "PREVIEW_DIR": str(self.preview),
            "PREVIEW_DRY_RUN": "1",
            "SCHOOLOS_ROOT": str(self.base),
            **env,
        }
        return subprocess.run(
            [BASH, "-c", program], env=full_env, capture_output=True, encoding="utf-8", check=False
        )

    def plan(self, **env: str) -> tuple[str, str, str]:
        """(TARGET، INTEG_KIND، INTEG_REPORT) لتخطيطٍ جديدٍ على main الحاليّ."""
        result = self.bash(
            'plan_integration "$(git -C "$PREVIEW_DIR" rev-parse main)"\n'
            'printf "%s\\n%s\\n---\\n%s" "$TARGET" "$INTEG_KIND" "$INTEG_REPORT"',
            **env,
        )
        assert result.returncode == 0, result.stderr
        head, _, report = result.stdout.partition("---\n")
        target, kind = head.strip().splitlines()
        return target, kind, report

    def tree_files(self, commit: str) -> set[str]:
        return set(_git(self.repo, "ls-tree", "-r", "--name-only", commit).splitlines())

    def snapshot(self) -> dict[str, str]:
        """كلُّ ما يمكن أن يتغيّر في أشجار الجلسات: رؤوسُها وفروعُها وحالةُ ملفّاتها."""
        snap = {"refs": _git(self.repo, "for-each-ref", "--format=%(refname) %(objectname)")}
        for tree in sorted(self.wt.iterdir()):
            if tree.name == "main-preview":
                continue
            snap[tree.name] = (
                _git(tree, "rev-parse", "HEAD")
                + "|"
                + _git(tree, "status", "--porcelain", "--ignored")
            )
        return snap


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory) -> Sandbox:
    return Sandbox(tmp_path_factory.mktemp("integ"))


# ── ما يدخل وما يُتخطّى ─────────────────────────────────────────


def test_clean_branches_are_merged_on_top_of_main(sandbox):
    target, kind, report = sandbox.plan()
    files = sandbox.tree_files(target)

    assert kind == "integrated" and target != sandbox.main
    assert {"a.txt", "b.txt", "shared.txt"} <= files  # a وb وc1 (الأقدمُ من المتعارضَين)
    assert {"s.txt", "app/migrations/0003_main.py"} <= files  # وما في main باقٍ
    assert "+ a — " in report and "+ b — " in report and "+ c1 — " in report


def test_skipped_branches_are_named_with_their_reason(sandbox):
    """السببُ يفرّق ما يُصلحه صاحبُ الفرع (إعادةُ أساس) عمّا يحسمه ترتيبُ الدمج (تعارضٌ مع فرعٍ آخر)."""
    _, _, report = sandbox.plan()

    assert re.search(r"^✗ conflict — يتعارض مع main .*notes\.txt", report, re.M)
    assert re.search(r"^✗ c2 — يتعارض مع فرع.*shared\.txt", report, re.M)
    assert re.search(r"^✗ migclash — .*0003_clash\.py", report, re.M)
    assert re.search(r"^✗ machinery — .*scripts/preview\.sh", report, re.M)
    assert re.search(r"^✗ stale — .* 10 ", report, re.M)


def test_skipped_content_never_reaches_the_target(sandbox):
    target, _, _ = sandbox.plan()
    files = sandbox.tree_files(target)

    assert "app/migrations/0003_clash.py" not in files  # كان سيسقط migrate
    assert "stale.txt" not in files
    assert _git(sandbox.repo, "show", f"{target}:scripts/preview.sh") == "# machinery"  # آلةُ main
    assert (
        _git(sandbox.repo, "show", f"{target}:notes.txt") == "one\nTWO-main\nthree"
    )  # لا نصفُ conflict
    assert _git(sandbox.repo, "show", f"{target}:shared.txt") == "from c1"


def test_branches_already_in_main_are_not_mentioned(sandbox):
    """`merged` سلفُ main، و`squashed` محتواه في main بإيداعٍ آخر — لا جديدَ فيهما فلا يُذكران."""
    _, _, report = sandbox.plan()

    assert "merged" not in report
    assert "squashed" not in report


def test_the_same_inputs_give_the_same_commit(sandbox):
    """إيداعٌ حتميٌّ (هويّةٌ وتاريخٌ ثابتان): وإلّا أُعيد إنشاءُ الخادم كلَّ دقيقةٍ بلا تغيّر."""
    first = sandbox.plan()[0]
    second = sandbox.plan()[0]

    assert first == second


def test_excluding_a_tree_removes_it_and_changes_the_target(sandbox):
    before, _, _ = sandbox.plan()
    sandbox.state.mkdir(parents=True, exist_ok=True)
    exclude = sandbox.state / "integ_exclude"
    exclude.write_text("b", encoding="utf-8")
    try:
        target, _, report = sandbox.plan()
    finally:
        exclude.unlink()

    assert target != before
    assert "b.txt" not in sandbox.tree_files(target)
    assert "+ b — " not in report


def test_a_stale_tree_can_be_brought_back_by_lifting_the_age_cap(sandbox):
    target, _, report = sandbox.plan(PREVIEW_INTEGRATE_MAX_AGE_HOURS="0")

    assert "stale.txt" in sandbox.tree_files(target)
    assert "+ stale — " in report


def test_with_nothing_to_add_the_target_is_main_itself(sandbox):
    everything = "a b conflict migclash machinery stale squashed c1 c2 merged"
    sandbox.state.mkdir(parents=True, exist_ok=True)
    exclude = sandbox.state / "integ_exclude"
    exclude.write_text(everything, encoding="utf-8")
    try:
        target, kind, report = sandbox.plan()
    finally:
        exclude.unlink()

    assert (target, kind, report) == (sandbox.main, "main", "")


def test_integration_touches_no_tree_no_head_and_no_branch(sandbox):
    before = sandbox.snapshot()
    sandbox.plan()
    sandbox.plan(PREVIEW_INTEGRATE_MAX_AGE_HOURS="0")

    assert sandbox.snapshot() == before


def test_the_preview_tree_itself_and_the_main_branch_are_never_candidates(sandbox):
    result = sandbox.bash("integ_candidates | cut -d'|' -f1 | sort")
    names = set(result.stdout.split())

    assert "main-preview" not in names
    assert "repo" not in names  # الشجرةُ الأصلُ على فرع main
    assert {"a", "b", "conflict", "c1", "c2"} <= names


# ── التشغيلُ والإطفاء ───────────────────────────────────────────


def test_integration_is_on_by_default_and_the_env_and_state_can_turn_it_off(sandbox):
    on = sandbox.bash("integrate_flag").stdout
    off_by_env = sandbox.bash("integrate_flag", PREVIEW_INTEGRATE="0").stdout
    # الحالةُ المحفوظةُ تغلب الافتراضَ (`integrate off` يكتبها).
    sandbox.state.mkdir(parents=True, exist_ok=True)
    flag = sandbox.state / "integrate"
    flag.write_text("0", encoding="utf-8")
    try:
        off_by_state = sandbox.bash("integrate_flag").stdout
        on_over_env = sandbox.bash("integrate_flag", PREVIEW_INTEGRATE="1").stdout
    finally:
        flag.unlink()

    assert (on, off_by_env, off_by_state, on_over_env) == ("1", "0", "0", "0")


def test_an_explicit_ref_disables_integration(sandbox):
    """PREVIEW_REF تجربةُ شيفرةٍ بعينها — لا يُضَمّ إليها شيء."""
    result = sandbox.bash(
        "integrate_active && echo active || echo inactive", PREVIEW_REF="deadbeef"
    )

    assert result.stdout.strip() == "inactive"


def test_the_cli_can_exclude_and_include_a_tree(sandbox):
    env = {
        **os.environ,
        **_ID,
        "PREVIEW_DIR": str(sandbox.preview),
        "SCHOOLOS_ROOT": str(sandbox.base),
    }
    exclude = subprocess.run(
        [BASH, str(SCRIPT), "integrate", "exclude", "a"],
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    excluded = (sandbox.state / "integ_exclude").read_text(encoding="utf-8")
    include = subprocess.run(
        [BASH, str(SCRIPT), "integrate", "include", "a"],
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    included = (sandbox.state / "integ_exclude").read_text(encoding="utf-8")

    assert exclude.returncode == 0 and include.returncode == 0, exclude.stderr + include.stderr
    assert excluded == "a" and included == ""


def test_the_cli_refuses_a_path_as_a_tree_name(sandbox):
    env = {
        **os.environ,
        **_ID,
        "PREVIEW_DIR": str(sandbox.preview),
        "SCHOOLOS_ROOT": str(sandbox.base),
    }
    result = subprocess.run(
        [BASH, str(SCRIPT), "integrate", "exclude", "../etc"],
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode != 0


# ── قاعدةُ المعاينة لا تحمل هجرةً ليست في الشجرة المعروضة ──────────────


def _db_state(sandbox, body: str) -> dict[str, str]:
    result = sandbox.bash(
        body
        + '\nprintf "GEN=%s\\nDB=%s\\nAPPLIED=%s\\n" "$(sget db_gen)" "$(preview_db)" "$(sget db_migrations | paste -sd, -)"',
        PREVIEW_DRY_RUN="0",
    )
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


@pytest.fixture()
def clean_state(sandbox):
    if sandbox.state.exists():
        shutil.rmtree(sandbox.state)
    yield
    if sandbox.state.exists():
        shutil.rmtree(sandbox.state)


def test_the_migration_list_is_read_from_git_without_django(sandbox):
    result = sandbox.bash('migration_list "$(git -C "$PREVIEW_DIR" rev-parse main)" | paste -sd, -')

    assert result.stdout.strip() == "app/0001_initial,app/0002_base,app/0003_main"


def test_new_migrations_extend_the_recorded_set_and_keep_the_db(sandbox, clean_state):
    state = _db_state(
        sandbox,
        "sset db_migrations 'app/0001_initial\napp/0002_base'\n"
        'prepare_db "$(git -C "$PREVIEW_DIR" rev-parse main)"',
    )

    assert state["GEN"] == ""  # لا قاعدةَ جديدة
    assert state["DB"] == "ss_main_preview"
    assert state["APPLIED"] == "app/0001_initial,app/0002_base,app/0003_main"


def test_a_migration_that_disappeared_from_the_tree_starts_a_new_db_generation(
    sandbox, clean_state
):
    """فرعٌ سُحب من التكامل وهجرتُه مطبَّقةٌ: القاعدةُ لا تُبقى — وإلّا سقطت الصفحاتُ بعمودٍ ناقص."""
    state = _db_state(
        sandbox,
        "sset db_migrations 'app/0001_initial\napp/0002_base\napp/0009_from_a_pulled_branch'\n"
        'prepare_db "$(git -C "$PREVIEW_DIR" rev-parse main)"',
    )

    assert state["GEN"] == "1"
    assert state["DB"] == "ss_main_preview_g1"
    assert "0009" not in state["APPLIED"]  # القاعدةُ الجديدةُ تبدأ من هجرات الشجرة
    assert state["APPLIED"] == "app/0001_initial,app/0002_base,app/0003_main"


def test_generations_keep_counting(sandbox, clean_state):
    state = _db_state(
        sandbox,
        "sset db_gen 2\nsset db_migrations 'app/0777_gone'\n"
        'prepare_db "$(git -C "$PREVIEW_DIR" rev-parse main)"',
    )

    assert state["GEN"] == "3" and state["DB"] == "ss_main_preview_g3"


def test_the_first_run_after_the_upgrade_assumes_the_db_matches_the_last_served_commit(
    sandbox, clean_state
):
    """لا سجلَّ بعدُ: القاعدةُ على ما خدمته آخرُ نسخة — فإن كانت شجرتُها الجديدةُ لا تحوي بعضَه بدأ جيلٌ جديد."""
    state = _db_state(
        sandbox,
        f"sset served_sha {sandbox.main}\n"
        'prepare_db "$(git -C "$PREVIEW_DIR" rev-parse main~1)"',  # قبل main: ينقصه 0003_main
    )

    assert state["GEN"] == "1"


# ── الدوالُّ الصغيرة ────────────────────────────────────────────


def test_same_content_compares_trees_not_commits(sandbox):
    """إيداعان بشجرةٍ واحدةٍ (إعادةُ صياغةٍ بلا تغيير) لا يستحقّان إعادةَ إنشاء الخادم."""
    twin = _git(
        sandbox.repo,
        "commit-tree",
        f"{sandbox.main}^{{tree}}",
        "-p",
        sandbox.main,
        "-m",
        "same tree",
    )
    other = _git(sandbox.repo, "rev-parse", "main~1")

    same = sandbox.bash(
        f"same_content {twin} {sandbox.main} && echo same || echo different"
    ).stdout.strip()
    different = sandbox.bash(
        f"same_content {other} {sandbox.main} && echo same || echo different"
    ).stdout.strip()
    empty = sandbox.bash(
        f'same_content {sandbox.main} "" && echo same || echo different'
    ).stdout.strip()

    assert (same, different, empty) == ("same", "different", "different")


def test_the_label_names_the_base_and_counts_the_branches(sandbox):
    result = sandbox.bash(
        'MAIN_SHA="$(git -C "$PREVIEW_DIR" rev-parse main)"\n'
        'plan_integration "$MAIN_SHA"; target_label; echo "$LABEL"'
    )
    label = result.stdout.strip()

    assert label.startswith("تكامل@") and f"main@{sandbox.main[:7]}" in label
    assert "+ 3 " in label  # a وb وc1
