#!/usr/bin/env python3
"""PreToolUse(Bash): يمنع أوامرَ غيت التي يحظرها CLAUDE.md في المحادثات المتوازية.

المستودعُ ورأسُه ومكدّسُ خبيئته مشتركةٌ بين كلّ الجلسات وشجراتها، فهذه ليست
ذوقاً بل ما يُبطل عملَ جلسةٍ أخرى. الخروجُ برمز 2 يعيد الرسالةَ إلى Claude.
"""
import json
import re
import shlex
import sys

SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
MAIN_REFS = {"main", "refs/heads/main", "master"}


sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')


def git_args(segment: str):
    """(subcommand, args) إن كان المقطعُ أمرَ git، وإلّا None. تُتجاوَز خياراتُ -C و-c."""
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        return None
    if not tokens or tokens[0] not in {"git", "git.exe"}:
        return None
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in {"-C", "-c", "--git-dir", "--work-tree"} else 1
    if i >= len(tokens):
        return None
    return tokens[i], tokens[i + 1 :]


def violation(sub: str, args: list[str]) -> str | None:
    flags = {a for a in args if a.startswith("-")}
    if sub == "add" and (flags & {"-A", "--all"} or "." in args or "-u" in flags):
        return "لا `git add -A/.` — مساراتٍ صريحةٍ وحدها؛ وإلّا ابتلعتَ عملَ جلسةٍ أخرى نصفَ مكتوب."
    if sub == "commit" and any(re.fullmatch(r"-[a-zA-Z]*a[a-zA-Z]*", f) for f in flags):
        return "لا `git commit -a` — أضِف المساراتِ صراحةً بـ`git add <مسار>` ثمّ أودِع."
    if sub == "commit" and "--all" in flags:
        return "لا `git commit --all` — أضِف المساراتِ صراحةً بـ`git add <مسار>` ثمّ أودِع."
    if sub == "stash" and not (args and args[0] in {"list", "show"}):
        return "لا `git stash` — المكدّسُ مشترك: تخبّئ أنت ويستخرج غيرُك. استعمل إيداعاً مؤقّتاً."
    if sub == "push":
        for a in args:
            target = a.split(":")[-1] if ":" in a else a
            if a in MAIN_REFS or (":" in a and target in MAIN_REFS):
                return "لا دفعَ إلى main مباشرةً — `git push origin HEAD:refs/heads/claude/<اسم-المهمّة>` وطلبُ دمج."
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    for segment in SEGMENT_SPLIT.split(command):
        parsed = git_args(segment.strip())
        if not parsed:
            continue
        reason = violation(*parsed)
        if reason:
            print(f"محجوب بقاعدة CLAUDE.md: {reason}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
