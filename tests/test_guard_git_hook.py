"""[CI] حارسُ الغيت (REP-19، RD8): `.claude/hooks/guard_git.py` يحجب ما يحظره بروتوكولُ المحادثات المتوازية، ولا يحجب ما سواه.

المستودعُ ومكدّسُه ومراجعُه مشتركةٌ بين كلّ الجلسات وهو عامّ: `git add -A` يبتلع عملَ جلسةٍ أخرى، و`--force` يعيد كتابةَ فرعٍ منشور، و`reset --hard`
يمحو ما لم يُودَع، و`--no-verify` يتجاوز فحوصَ الأسرار، والدفعُ الجماعيّ ينشر ما لا يُنشر. فالاختباراتُ هنا تُثبت ثلاثةً:
(1) كلُّ قاعدةٍ تحجب أمثلتَها بأيّ شكلٍ يلتفّ به الأمرُ (`bash -c` و`env` و`$(…)` و`xargs` و`&` في PowerShell وأسماءُ git المستعارة…)، ولكلّ قاعدةٍ مثالٌ
لا يحجبه غيرُها (فلا تكون قاعدةٌ زائدةً على غيرها فتُحذف بلا أن يسقط شيء)؛
(2) ما سوى ذلك يمرّ — والقائمةُ مأخوذةٌ من أوامرَ حقيقيّةٍ في نصوص الجلسات (رسائلُ إيداعٍ تذكر الأوامرَ المحظورة، `git add -A <مسار>`، حذفُ مرجعٍ مؤقّت،
مستودعُ الوثائق المنفصل) لأنّ الإيجابيّ الكاذب يُعطّل عملَ الجلسات فتُعطَّل الحمايةُ كلُّها؛
(3) الحارسُ نفسُه شبكةُ أمان: خللٌ فيه أو مدخلٌ فاسدٌ لا يمنع أمراً، والتجاوزُ صريحٌ مُسجَّل، والـhook مسجَّلٌ فعلاً في `.claude/settings.json` لـBash وPowerShell.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "guard_git.py"
LAUNCHER = ROOT / ".claude" / "hooks" / "guard_git.sh"
SETTINGS = ROOT / ".claude" / "settings.json"


def _load():
    spec = importlib.util.spec_from_file_location("guard_git", GUARD)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()
PROJECT = "D:/shschool_mvp/.claude/worktrees/task-1"  # هيئةٌ ثابتةٌ: المقارنةُ نصّيّةٌ فلا تتوقّف على نظام التشغيل


def analyse(command, tool="Bash", aliases=None, branch="claude/x", cwd=PROJECT):
    return guard.check(
        command,
        tool=tool,
        cwd=cwd,
        project_dir=PROJECT,
        alias_lookup=(aliases or {}).get,
        branch_lookup=lambda where: branch,
    )


def rules(command, **kwargs):
    return {h.rule for h in analyse(command, **kwargs).hits}


# ── 1) لكلّ قاعدةٍ أمثلتُها — ومعها المثالُ الذي لا يحجبه غيرُها ─────────────────────────

BLOCKED = [
    # add-all
    ("add-all", "git add -A"),
    ("add-all", "git add ."),
    ("add-all", "git add --all"),
    ("add-all", "git add -u"),
    ("add-all", "git add -Av"),
    ("add-all", "git add -- ."),
    ("add-all", "git add ./"),
    ("add-all", "git add -f ."),
    ("add-all", "git -C sub add -A"),
    ("add-all", "cd sub && git add ."),
    # commit-all
    ("commit-all", "git commit -a -m x"),
    ("commit-all", "git commit -am x"),
    ("commit-all", "git commit --all -m x"),
    ("commit-all", "git commit -m x -a"),
    ("commit-all", "git commit -qam x"),
    # stash
    ("stash", "git stash"),
    ("stash", "git stash push -m x"),
    ("stash", "git stash pop"),
    ("stash", "git stash apply"),
    ("stash", "git stash drop"),
    ("stash", "git stash -u"),
    ("stash", "git -c core.safecrlf=false stash push -u -q -m tag"),
    # push-main
    ("push-main", "git push origin main"),
    ("push-main", "git push origin HEAD:main"),
    ("push-main", "git push origin HEAD:refs/heads/main"),
    ("push-main", "git push origin master"),
    ("push-main", "git push origin claude/x:main"),
    # push-force
    ("push-force", "git push --force origin x"),
    ("push-force", "git push -f origin x"),
    ("push-force", "git push --force-with-lease origin x"),
    ("push-force", "git push --force-with-lease=x:abc123 origin x"),
    ("push-force", "git push --force-if-includes origin x"),
    ("push-force", "git push origin +x"),
    ("push-force", "git push -fu origin x"),
    ("push-force", "git push -uf origin x"),
    ("push-force", "git push origin +HEAD:refs/heads/claude/x"),
    # push-delete
    ("push-delete", "git push origin --delete claude/x"),
    ("push-delete", "git push origin -d claude/x"),
    ("push-delete", "git push origin :claude/x"),
    ("push-delete", "git push --prune origin"),
    ("push-delete", "git push --mirror origin"),
    # push-bulk
    ("push-bulk", "git push --all origin"),
    ("push-bulk", "git push origin --tags"),
    ("push-bulk", "git push origin --branches"),
    ("push-bulk", "git push origin refs/tags/archive/x-2026-09-25"),
    ("push-bulk", "git push origin archive/x-2026-09-25"),
    ("push-bulk", "git push origin HEAD:refs/heads/archive/x"),
    # no-verify
    ("no-verify", "git commit --no-verify -m x"),
    ("no-verify", "git commit -n -m x"),
    ("no-verify", "git commit -nm x"),
    ("no-verify", "git push --no-verify origin x"),
    ("no-verify", "git merge --no-verify x"),
    ("no-verify", "git -c core.hooksPath=/dev/null commit -m x"),
    ("no-verify", "SKIP=ruff,detect-secrets git commit -m x"),
    ("no-verify", "git config core.hooksPath /dev/null"),
    # reset-hard
    ("reset-hard", "git reset --hard"),
    ("reset-hard", "git reset --hard origin/main"),
    ("reset-hard", "git reset -q --hard HEAD~1"),
    ("reset-hard", "git reset HEAD~1 --hard"),
    # branch-delete
    ("branch-delete", "git branch -D x"),
    ("branch-delete", "git branch -Df x"),
    ("branch-delete", "git branch -d -f x"),
    ("branch-delete", "git branch --delete --force x"),
    ("branch-delete", "git branch --merged | xargs git branch -D"),
    ("branch-delete", "git branch -D $(git branch --list 'tmp/*')"),
    # tag-delete
    ("tag-delete", "git tag -d x"),
    ("tag-delete", "git tag --delete x"),
    # ref-delete
    ("ref-delete", "git update-ref -d refs/heads/x"),
    ("ref-delete", "git update-ref --delete refs/tags/x"),
    ("ref-delete", "git update-ref -d refs/remotes/origin/x abc123"),
    # history-rewrite
    ("history-rewrite", "git filter-branch --all"),
    ("history-rewrite", "git filter-repo --force"),
    ("history-rewrite", "git reflog expire --expire=now --all"),
    ("history-rewrite", "git reflog delete HEAD@{1}"),
    ("history-rewrite", "git gc --prune=now"),
    ("history-rewrite", "git gc --prune=all"),
    ("history-rewrite", "git prune"),
    # clean-force
    ("clean-force", "git clean -f"),
    ("clean-force", "git clean -fd"),
    ("clean-force", "git clean -fdx"),
    ("clean-force", "git clean --force"),
    # discard-all
    ("discard-all", "git checkout ."),
    ("discard-all", "git checkout -- ."),
    ("discard-all", "git restore ."),
    ("discard-all", "git checkout main -- ."),
    ("discard-all", "git checkout -f main"),
    ("discard-all", "git switch -f main"),
    ("discard-all", "git switch --discard-changes main"),
    ("discard-all", "git restore --worktree --staged ."),
    # prune-apply
    ("prune-apply", "bash scripts/prune_local_branches.sh --apply"),
    ("prune-apply", "python scripts/prune_local_branches.py --apply --max 50"),
    ("prune-apply", "py -3 scripts/prune_local_branches.py --json --apply"),
    ("prune-apply", "./scripts/prune_local_branches.sh --apply"),
    ("prune-apply", "bash -c 'bash scripts/prune_local_branches.sh --apply'"),
]

# أوامرُ تنتهك أكثرَ من قاعدةٍ معاً
MULTI = [
    ({"push-main", "push-delete"}, "git push origin :main"),
    ({"push-main", "push-force"}, "git push origin +main"),
    ({"push-main", "push-force"}, "git push --force origin HEAD:refs/heads/main"),
    ({"add-all", "commit-all"}, "git add . && git commit -am x"),
    ({"push-force", "no-verify"}, "git push --force --no-verify origin x"),
]

# أشكالُ الالتفاف: نفسُ الفعل المحظور (force-push) بكلّ ما يمكن أن يلفّه — يجب أن يُحجب كلُّها
WRAPPED = [
    "bash -c 'git push -f origin x'",
    'sh -c "git push -f origin x"',
    "bash -lc 'git push -f origin x'",
    "bash --login -c 'git push -f origin x'",
    "bash -o pipefail -c 'git push -f origin x'",
    "zsh -c 'git push -f origin x'",
    "env git push -f origin x",
    "env -i A=b git push -f origin x",
    "A=1 B=2 git push -f origin x",
    "command git push -f origin x",
    "exec git push -f origin x",
    "sudo -u root git push -f origin x",
    "nohup git push -f origin x",
    "time git push -f origin x",
    "timeout 30 git push -f origin x",
    "nice -n 5 git push -f origin x",
    "echo x | xargs -I{} git push -f origin {}",
    "echo x | xargs git push -f origin",
    'eval "git push -f origin x"',
    "echo $(git push -f origin x)",
    "echo `git push -f origin x`",
    'echo "value: $(git push -f origin x)"',
    "(git push -f origin x)",
    "{ git push -f origin x; }",
    "if true; then git push -f origin x; fi",
    "for b in a b; do git push -f origin $b; done",
    "true && git push -f origin x",
    "false || git push -f origin x",
    "git status; git push -f origin x",
    "git status\ngit push -f origin x",
    "git push -f origin x 2>&1",
    "git push -f origin x > out.txt",
    "git push -f origin x 2>/dev/null | tail -1",
    "/usr/bin/git push -f origin x",
    r'"C:\Program Files\Git\cmd\git.exe" push -f origin x',
    "git.exe push -f origin x",
    "git -C /x push -f origin x",
    "git -C sub -C ../up -c a=b --no-pager push -f origin x",
    "git --git-dir=/x/.git push -f origin x",
    "wsl git push -f origin x",
    "cmd /c git push -f origin x",
    'cmd.exe /c "git push -f origin x"',
    'pwsh -Command "git push -f origin x"',
    "powershell -NoProfile -c 'git push -f origin x'",
    "bash <<'EOF'\ngit push -f origin x\nEOF",
    "git commit -m \"$(cat <<'EOF'\nmsg\nEOF\n)\" && git push -f origin x",
]


@pytest.mark.parametrize(("rule", "command"), BLOCKED, ids=[f"{r}:{c[:48]}" for r, c in BLOCKED])
def test_a_forbidden_command_is_blocked_by_exactly_its_rule(rule, command):
    assert rules(command) == {rule}


@pytest.mark.parametrize(("expected", "command"), MULTI, ids=[c[:60] for _, c in MULTI])
def test_a_command_breaking_two_rules_reports_both(expected, command):
    assert rules(command) == expected


@pytest.mark.parametrize("command", WRAPPED, ids=[c.replace("\n", "⏎")[:60] for c in WRAPPED])
def test_the_forbidden_action_is_caught_however_the_command_is_wrapped(command):
    assert "push-force" in rules(command)


def test_every_rule_is_pinned_by_an_example_only_it_blocks(monkeypatch):
    """قاعدةٌ يحجب مثالَها غيرُها زائدةٌ: تُحذف فلا يسقط شيء. فتُعطَّل كلُّ قاعدةٍ على حدة ويُطلَب أن يمرّ أمثلتُها."""
    known = set(guard.GIT_RULES) | set(guard.WORD_RULES)
    assert {rule for rule, _ in BLOCKED} == known, "لكلّ قاعدةٍ أمثلة، ولا مثالَ لقاعدةٍ غير معرَّفة"
    for rule in sorted(known):
        monkeypatch.setattr(
            guard, "GIT_RULES", {k: v for k, v in guard.GIT_RULES.items() if k != rule}
        )
        monkeypatch.setattr(
            guard, "WORD_RULES", {k: v for k, v in guard.WORD_RULES.items() if k != rule}
        )
        for r, command in BLOCKED:
            if r == rule:
                assert rules(command) == set(), f"{rule}: «{command}» يحجبه غيرُها"
        monkeypatch.undo()


# ── PowerShell ─────────────────────────────────────────────────────────────────

POWERSHELL_BLOCKED = [
    ("push-force", "& git push --force origin x"),
    ("push-force", "$out = git push -f 2>&1"),
    ("push-force", "git push -f; git status"),
    ("push-force", "Invoke-Expression 'git push -f origin x'"),
    ("push-force", 'iex "git push --force origin x"'),
    ("push-force", r'& "C:\Program Files\Git\cmd\git.exe" push -f origin x'),
    ("push-force", "if ($true) { git push -f origin x }"),
    ("push-force", 'pwsh -Command "git push --force"'),
    ("branch-delete", "git branch --merged | ForEach-Object { git branch -D $_.Trim() }"),
    ("add-all", "git.exe add ."),
    ("reset-hard", "git reset --hard HEAD~1"),
    ("stash", "$x = git stash"),
]


@pytest.mark.parametrize(
    ("rule", "command"), POWERSHELL_BLOCKED, ids=[c[:50] for _, c in POWERSHELL_BLOCKED]
)
def test_powershell_commands_are_guarded_too(rule, command):
    assert rule in rules(command, tool="PowerShell")


def test_an_encoded_powershell_command_is_decoded_and_checked():
    encoded = base64.b64encode("git push --force origin x".encode("utf-16-le")).decode()

    assert rules(f"powershell -EncodedCommand {encoded}") == {"push-force"}
    assert rules(f"pwsh -enc {encoded}", tool="PowerShell") == {"push-force"}


def test_a_powershell_here_string_message_is_not_analysed():
    command = "git commit -m @'\nnote: git push --force and git reset --hard\n'@"

    assert rules(command, tool="PowerShell") == set()


# ── 2) ما يمرّ — أوامرُ سليمةٌ منها ما مأخوذٌ من نصوص الجلسات الحقيقيّة ─────────────────────

ALLOWED = [
    "git status",
    "git status -sb",
    "git log --oneline -5",
    "git diff",
    "git diff --stat main...HEAD",
    "git show HEAD",
    "git fetch origin --prune",
    "git fetch origin main",
    "git merge origin/main",
    "git merge --ff-only origin/main",
    "git rebase origin/main",
    "git cherry-pick abc123",
    "git add a.py b.py",
    "git add -A a.py b.py",
    "git add -A -- static/css templates tests",
    "git add -u -- AAdocs/claude/roadmap/",
    "git add -n .",
    "git add -p",
    'git commit -m "msg"',
    "git commit -F msg.txt",
    "git commit --amend --no-edit",
    "git commit -S -m x",
    "git commit -Sabcd1234 -m x",
    "git commit -m 'fix -a and --force and reset --hard in text'",
    "git commit -m 'docs: لا `git push --force` ولا `git add -A`'",
    "git commit -m \"$(cat <<'EOF'\nsubject\n\nلا `git push --force` ولا git reset --hard؛ وdon't stash\nEOF\n)\"",
    "git commit -F - <<'EOF'\ngit add -A here is only text\nEOF",
    "git push origin HEAD:refs/heads/claude/x",
    "git push -u origin claude/x",
    "git push origin claude/x",
    "git push origin refs/heads/claude/x:refs/heads/claude/x",
    "git push origin refs/tags/v1.0",
    "git push origin main:claude/backup",
    "git push --dry-run origin claude/x",
    "git push",
    "git push origin",
    "git push -u origin HEAD",
    "git reset --soft HEAD~1",
    "git reset HEAD file.py",
    "git reset --mixed HEAD~1",
    "git stash list",
    "git stash show -p",
    "git branch",
    "git branch -vv",
    "git branch --list 'claude/*'",
    "git branch -d merged-branch",
    "git branch -m old new",
    "git branch --contains abc123",
    "git branch --merged origin/main",
    "git tag -l",
    "git tag v1",
    "git tag -a x -m msg",
    "git update-ref refs/tmp/x HEAD",
    "git update-ref -d refs/tmp/x",
    "git gc",
    "git prune -n",
    "git prune --dry-run",
    "git reflog",
    "git reflog show",
    "git clean -n",
    "git clean -nd",
    "git clean -f -n",
    "git checkout -b x",
    "git checkout main",
    "git checkout -- file.py",
    "git checkout origin/main -- path/file.py",
    "git restore file.py",
    "git restore --staged .",
    "git switch -c x",
    "git switch main",
    "git worktree add ../x",
    "git worktree list",
    "git worktree remove --force ../tmp-wt",
    "git log --grep='--force'",
    'git log -S"reset --hard"',
    'git grep -n "push --force"',
    'echo "git push --force"',
    'grep -rn "git stash" docs/',
    "python -c \"print('git push -f')\"",
    "bash scripts/prune_local_branches.sh",
    "bash scripts/prune_local_branches.sh --json",
    "python scripts/prune_local_branches.py --archive",
    "cat <<'EOF'\ngit push -f\nEOF",
    "python - <<'PY'\nimport subprocess\nsubprocess.run(['git', 'push', '-f'])\nPY",
    "git status # git push --force",
    'MSG="git push --force"; echo "$MSG"',
    "gh pr merge 5 --squash",
    "gh pr create --title x",
    "git config user.name",
    "git config --get alias.x",
    "git config core.hooksPath",
    "git config --global alias.co checkout",
    "git status\n\n\n",
    "",
    "   ",
]


@pytest.mark.parametrize(
    "command", ALLOWED, ids=[c.replace("\n", "⏎")[:60] or "empty" for c in ALLOWED]
)
def test_a_legitimate_command_is_not_blocked(command):
    assert rules(command) == set()


# ── مستودعٌ خارجيٌّ (الوثائق) وما يخصّ هذا المستودعَ ──────────────────────────────────────

FOREIGN = [
    "cd /d/shschool-docs && git add -A && git commit -m x && git push origin main",
    r"cd D:\shschool-docs; git add -A; git push origin main",
    "git -C /d/shschool-docs push origin main",
    "git -C /tmp/scratch reset --hard",
    "cd /tmp/mirror && git filter-repo --force --invert-paths --path x",
    "cd ../../../../shschool-docs && git stash",
]
OURS = [
    ("add-all", "cd /d/shschool_mvp && git add -A"),
    ("add-all", "cd /d/shschool_mvp/.claude/worktrees/other && git add -A"),
    ("add-all", 'cd "$P" && git add -A'),
    ("add-all", "git -C /d/shschool_mvp add -A"),
    ("add-all", "cd sub && git add -A"),
    ("reset-hard", "cd /tmp/x && cd /d/shschool_mvp && git reset --hard"),
]


@pytest.mark.parametrize("command", FOREIGN, ids=[c[:60] for c in FOREIGN])
def test_a_command_run_in_another_repository_is_not_ours_to_guard(command):
    assert rules(command) == set()


@pytest.mark.parametrize(("rule", "command"), OURS, ids=[c[:60] for _, c in OURS])
def test_a_command_run_here_or_somewhere_unknown_is_guarded(rule, command):
    assert rule in rules(command)


def test_pushing_force_or_deleting_or_bulk_is_guarded_even_from_another_repository():
    for command in (
        "cd /tmp/mirror && git push --force origin x",
        "git -C /tmp/mirror push origin --delete x",
        "cd /tmp/mirror && git push origin --tags",
    ):
        assert rules(command), command


def test_a_session_whose_own_directory_is_another_repository_is_not_guarded_for_local_rules():
    assert rules("git add -A", cwd="D:/shschool-docs") == set()
    assert rules("git add -A", cwd=PROJECT) == {"add-all"}


def test_pushing_without_a_target_while_on_main_is_blocked_but_not_on_a_feature_branch():
    for command in ("git push", "git push origin", "git push -u origin HEAD"):
        assert rules(command, branch="main") == {"push-main"}, command
        assert rules(command, branch="claude/x") == set(), command
    assert rules("git push origin claude/x", branch="main") == set()


# ── الأسماءُ المستعارة تُفكّ فلا تُخفي المحظور ─────────────────────────────────────────

ALIASES = {
    "wip": "!git add -A && git commit -m 'WIP'",
    "cma": "commit -am",
    "save": "stash push",
    "pop": "stash pop",
    "pf": "push --force",
    "pf2": "pf origin",  # اسمٌ مستعارٌ لاسمٍ مستعار
    "st": "status -sb",
    "co": "checkout",
}


@pytest.mark.parametrize(
    ("rule", "command"),
    [
        ("add-all", "git wip"),
        ("commit-all", "git cma 'msg'"),
        ("stash", "git save"),
        ("stash", "git pop"),
        ("push-force", "git pf origin x"),
        ("push-force", "git pf2 x"),
        ("discard-all", "git co ."),
    ],
)
def test_a_git_alias_does_not_hide_a_forbidden_command(rule, command):
    assert rules(command, aliases=ALIASES) == {rule}


def test_a_harmless_alias_and_an_unknown_subcommand_pass():
    assert rules("git st", aliases=ALIASES) == set()
    assert rules("git nonexistent-thing", aliases=ALIASES) == set()


def test_an_alias_given_inline_is_resolved_and_a_cycle_does_not_hang():
    assert rules("git -c alias.zz='push --force' zz origin x") == {"push-force"}
    assert rules("git a", aliases={"a": "b", "b": "a"}) == set()


def test_the_real_git_configuration_is_asked_for_aliases_when_none_is_injected(tmp_path):
    if not shutil.which("git"):
        pytest.skip("يحتاج git")
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=str(tmp_path / "empty"), GIT_CONFIG_NOSYSTEM="1")
    (tmp_path / "empty").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "alias.zap", "!git add -A"], cwd=repo, env=env, check=True)
    old = dict(os.environ)
    os.environ.update(env)
    try:
        result = guard.check("git zap", cwd=str(repo), project_dir=str(repo))
    finally:
        os.environ.clear()
        os.environ.update(old)

    assert {h.rule for h in result.hits} == {"add-all"}


# ── المُقطِّع: ما يُحلَّل وما لا يُحلَّل ───────────────────────────────────────────────────


def test_the_lexer_splits_commands_and_extracts_substitutions():
    commands, nested = guard.lex("a b && c 'd e' | f \"g $(h i)\"; j `k l`")

    assert commands == [["a", "b"], ["c", "d e"], ["f", "g $()"], ["j", "`cmd`"]]
    assert nested == ["h i", "k l"]


def test_a_heredoc_body_is_skipped_and_the_command_after_it_is_still_seen():
    commands, nested = guard.lex("cat <<'EOF' | tee f\ngit push -f\nEOF\ngit add -A")

    assert commands == [["cat"], ["tee", "f"], ["git", "add", "-A"]]
    assert nested == []


def test_backticks_inside_double_quotes_run_in_bash_so_a_message_naming_a_forbidden_command_that_way_is_blocked():
    """في Bash `git commit -m "… `git add -A` …"` تنفّذ `git add -A` فعلاً — وهذا بالضبط حادثُ الرسالة التي تذكر أمراً بين backticks؛
    والحلُّ heredoc بحدٍّ مقتبَس أو علامةُ اقتباسٍ مفردة. وفي PowerShell الـbacktick هروبٌ لا تنفيذ."""
    message = 'git commit -m "docs: لا `git add -A` ولا `git push --force`"'

    assert rules(message) == {"add-all", "push-force"}
    assert rules(message, tool="PowerShell") == set()
    assert rules(message.replace('"', "'")) == set()


def test_a_heredoc_body_with_quotes_and_parens_inside_a_substitution_does_not_break_the_parse():
    command = "git commit -m \"$(cat <<'EOF'\nit's (a) \"quoted\" line with ) and ' inside\nEOF\n)\" && git push -f"

    assert rules(command) == {"push-force"}


def test_an_odd_apostrophe_in_a_heredoc_body_does_not_swallow_the_command_that_follows_the_substitution():
    """رسالةُ الإيداع بالـheredoc تحمل غالباً علامةَ اقتباسٍ واحدة («don't»)؛ فلو عُدّت فاتحةً لابتلعت ما بعدَ `)` من أوامر."""
    command = "git commit -m \"$(cat <<'EOF'\nit's a note\nEOF\n)\" && git push -f origin x"

    assert rules(command) == {"push-force"}


def test_the_body_of_a_heredoc_that_feeds_a_shell_is_analysed_but_data_heredocs_are_not():
    assert rules("bash <<'EOF'\ngit reset --hard\nEOF") == {"reset-hard"}
    assert rules("sh -s <<EOF\ngit stash\nEOF") == {"stash"}
    assert rules("cat <<'EOF'\ngit reset --hard\nEOF") == set()
    assert rules("psql -f - <<'SQL'\ngit stash\nSQL") == set()


def test_an_unquoted_windows_path_keeps_its_backslashes():
    commands, _ = guard.lex(r"C:\Users\mesue\git.exe push -f")

    assert commands == [[r"C:\Users\mesue\git.exe", "push", "-f"]]


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'unterminated",
        'git commit -m "unterminated',
        "echo $(git status",
        "echo `git status",
        "cat <<EOF\nno terminator ever",
        "git push -f (",
        ")))((( ;;; ||| &&&",
        "$(" * 40,
        "'" * 51,
        "bash -c 'bash -c \"bash -c \\'git push -f\\'\"'",
        "\x00\x01 git \udcff",
        "a" * 100_000,
    ],
    ids=lambda c: repr(c)[:30],
)
def test_a_malformed_command_never_crashes_the_analysis(command):
    analyse(command)
    analyse(command, tool="PowerShell")


def test_nesting_beyond_the_depth_limit_is_cut_not_followed_forever():
    command = "git push -f"
    for _ in range(guard.MAX_DEPTH + 3):
        command = "bash -c '" + command.replace("'", "'\\''") + "'"

    assert isinstance(analyse(command).hits, list)


@pytest.mark.parametrize(
    ("args", "sub", "shorts", "longs", "pos"),
    [
        (["-am", "msg"], "commit", {"-a"}, set(), []),
        (["-ma", "msg-text"], "commit", set(), set(), ["msg-text"]),
        (["-qam", "msg", "file"], "commit", {"-q", "-a"}, set(), ["file"]),
        (["-Sabcd", "-m", "x"], "commit", set(), set(), []),
        (["-fu", "origin", "x"], "push", {"-f", "-u"}, set(), ["origin", "x"]),
        (["--force-with-lease=x:1", "origin"], "push", set(), {"--force-with-lease"}, ["origin"]),
        (["-o", "opt", "origin", "x"], "push", set(), set(), ["origin", "x"]),
        (["--", "-a", "file"], "commit", set(), set(), []),
    ],
)
def test_option_clusters_are_split_up_to_the_first_option_that_takes_a_value(
    args, sub, shorts, longs, pos
):
    opts = guard.parse_opts(args, sub)

    assert (opts.shorts, opts.longs, opts.pos) == (shorts, longs, pos)


# ── 3) الحارسُ شبكةُ أمان، والتجاوزُ صريحٌ مُسجَّل ─────────────────────────────────────────


def _run(payload, tmp_path, extra_env=None, raw=None):
    env = {k: v for k, v in os.environ.items() if k not in ("GUARD_GIT_ALLOW",)}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), CLAUDE_PROJECT_DIR=PROJECT)
    env.update(extra_env or {})
    data = raw if raw is not None else json.dumps(payload).encode("utf-8")
    return subprocess.run(
        [sys.executable, str(GUARD)], input=data, capture_output=True, env=env, timeout=60
    )


def _payload(command, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": PROJECT}


def test_a_blocked_command_exits_2_and_tells_claude_why_and_how_to_ask(tmp_path):
    proc = _run(_payload("git push --force origin x"), tmp_path)
    err = proc.stderr.decode("utf-8")

    assert proc.returncode == 2
    assert "[push-force]" in err
    assert "GUARD_GIT_ALLOW" in err and "المالك" in err


def test_an_allowed_command_and_every_other_tool_exit_0(tmp_path):
    assert _run(_payload("git status"), tmp_path).returncode == 0
    assert (
        _run({"tool_name": "Edit", "tool_input": {"command": "git push -f"}}, tmp_path).returncode
        == 0
    )
    assert _run({"tool_name": "Bash", "tool_input": {}}, tmp_path).returncode == 0
    assert _run({"tool_name": "Bash"}, tmp_path).returncode == 0


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[]",
        b"null",
        b'{"tool_name": "Bash", "tool_input": "x"}',
        b"\xff\xfe\x00",
    ],
)
def test_a_malformed_hook_input_never_blocks(raw, tmp_path):
    assert _run(None, tmp_path, raw=raw).returncode == 0


def test_the_override_with_a_stated_reason_lets_the_command_through_and_is_logged(tmp_path):
    reason = "owner approved 2026-10-01 REP-13"
    proc = _run(_payload(f"GUARD_GIT_ALLOW='{reason}' git push --force origin x"), tmp_path)

    assert proc.returncode == 0
    log = (tmp_path / ".claude" / "logs" / "guard_git_overrides.log").read_text(encoding="utf-8")
    assert reason in log and "push-force" in log


def test_the_powershell_form_of_the_override_works_too(tmp_path):
    command = "$env:GUARD_GIT_ALLOW = 'owner approved 2026-10-01'; git push -f origin x"

    assert _run(_payload(command, "PowerShell"), tmp_path).returncode == 0
    assert (
        _run(
            _payload("$env:GUARD_GIT_ALLOW='owner approved 2026-10-01'; git push -f", "PowerShell"),
            tmp_path,
        ).returncode
        == 0
    )


@pytest.mark.parametrize(
    "command",
    [
        "GUARD_GIT_ALLOW='short' git push -f origin x",
        "GUARD_GIT_ALLOW= git push -f origin x",
        "git push -f origin x  # GUARD_GIT_ALLOW='owner approved 2026-10-01'",
        "git commit -am \"docs: explain GUARD_GIT_ALLOW='owner approved 2026-10-01'\"",
        "echo GUARD_GIT_ALLOW='owner approved 2026-10-01'; git push -f origin x",
    ],
    ids=[
        "reason too short",
        "empty reason",
        "in a comment",
        "inside a commit message",
        "as an argument not a prefix",
    ],
)
def test_the_override_needs_a_real_reason_at_command_position(command, tmp_path):
    assert _run(_payload(command), tmp_path).returncode == 2


def test_an_internal_failure_lets_the_command_through_and_says_so(monkeypatch, capsys):
    class Stdin:
        buffer = type(
            "Buffer", (), {"read": lambda self: json.dumps(_payload("git add -A")).encode()}
        )()

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(guard, "check", broken)
    monkeypatch.setattr(sys, "stdin", Stdin())

    assert guard.main() == 0
    assert "تعذّر تحليلُ الأمر" in capsys.readouterr().err


def test_analysing_a_typical_command_takes_well_under_a_millisecond_each():
    import time

    started = time.perf_counter()
    for _ in range(500):
        analyse(
            "cd /d/shschool_mvp && python manage.py test --keepdb -q 2>&1 | tail -20; git status --short | head -5"
        )
    assert time.perf_counter() - started < 5


# ── الـhook مسجَّلٌ فعلاً، ومُشغِّلُه يجد بايثون ───────────────────────────────────────────


def test_the_hook_is_registered_for_bash_and_powershell_and_points_at_an_existing_launcher():
    hooks = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]
    entries = hooks["PreToolUse"]
    guard_entries = [e for e in entries if any("guard_git.sh" in h["command"] for h in e["hooks"])]

    assert len(guard_entries) == 1
    matcher = guard_entries[0]["matcher"].split("|")
    assert {"Bash", "PowerShell"} <= set(matcher)
    command = guard_entries[0]["hooks"][0]
    assert command["type"] == "command" and 0 < command["timeout"] <= 30
    assert '"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_git.sh"' in command["command"]
    assert LAUNCHER.is_file() and GUARD.is_file()


def test_registering_the_guard_did_not_drop_the_session_start_hook():
    hooks = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]

    commands = [h["command"] for e in hooks["SessionStart"] for h in e["hooks"]]
    assert "bash scripts/session-start-prod.sh" in commands
    assert (ROOT / "scripts" / "session-start-prod.sh").is_file()


def test_the_launcher_and_the_guard_are_stored_with_unix_line_endings():
    for path in (GUARD, LAUNCHER):
        assert b"\r\n" not in path.read_bytes(), f"{path.name}: CRLF يكسر `bash` على السطر الأوّل"


@pytest.mark.skipif(
    not shutil.which("bash") or os.name == "nt",
    reason="المُشغِّلُ bash؛ على ويندوز يُجرَّب يدويّاً في Git Bash",
)
def test_the_launcher_passes_stdin_through_and_keeps_the_exit_code(tmp_path):
    def run(command):
        return subprocess.run(
            ["bash", str(LAUNCHER)],
            input=json.dumps(_payload(command)).encode(),
            capture_output=True,
            env={**os.environ, "HOME": str(tmp_path), "CLAUDE_PROJECT_DIR": PROJECT},
            timeout=60,
        )

    assert run("git add -A").returncode == 2
    assert run("git status").returncode == 0


def test_the_guard_uses_only_the_standard_library():
    imported = set()
    for line in GUARD.read_text(encoding="utf-8").splitlines():
        if line.startswith(("import ", "from ")):
            imported.add(line.split()[1].split(".")[0])

    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
