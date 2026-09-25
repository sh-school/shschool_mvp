#!/usr/bin/env python3
"""PreToolUse (Bash|PowerShell): حارسُ الغيت — يحجب أوامرَ يحظرها بروتوكولُ المحادثات المتوازية (REP-19، قرارُ المالك RD8).

المستودعُ ورأسُه ومكدّسُ خبيئته ومراجعُه مشتركةٌ بين كلّ الجلسات وشجراتها، والمستودعُ عامّ: فهذه ليست ذوقاً بل ما يُبطل عملَ جلسةٍ
أخرى أو ينشر ما لا يُنشر. الخروجُ برمز 2 يمنع الأمرَ ويعيد الرسالةَ إلى Claude. وهو شبكةُ أمانٍ ضدّ الحوادث لا صندوقٌ معزول: لا يرى ما
داخل سكربتٍ يُشغَّل (`bash x.sh`) ولا متغيّراً غيرَ محلول (`$CMD`)، وأيُّ خللٍ في الحارس نفسِه لا يمنع أمراً (يُبلَّغ ويمرّ).
ولا يحرس صدفةَ المستخدم في طرفيّته — فلا يُغني عن إعدادات git المشتركة (REP-11).

المحظور (المعرّفُ هو ما تسمّيه الاختباراتُ ووثيقةُ الحرّاس):
  add-all          add -A/--all/-u بلا مسارٍ صريح، وadd . (مساراتٌ صريحةٌ وحدَها)
  commit-all       commit -a/--all
  stash            stash (عدا list وshow) — المكدّسُ مشترك
  push-main        الدفعُ إلى main/master (وبلا وجهةٍ وأنت عليه)
  push-force       push --force/-f/--force-with-lease/--force-if-includes/+refspec
  push-delete      push --delete/-d/:ref/--prune/--mirror
  push-bulk        push --all/--branches/--tags، ولمرجعٍ تحت archive/ (وسومُ الأرشفة تحمل عملاً فريداً فنشرُها بإذن)
  no-verify        --no-verify، وSKIP=، و-c core.hooksPath، وضبطُ core.hooksPath — لا تجاوزَ لفحوص الإيداع
  reset-hard       reset --hard
  branch-delete    branch -D (وحذفٌ مع --force): -d وحدَه يرفض ما لم يُدمج فيبقى مسموحاً
  tag-delete       tag -d
  ref-delete       update-ref -d لمرجعٍ غير refs/tmp/ (تلك مرجعاتٌ مؤقّتةٌ تنظّفها الجلساتُ بعد التحليل)
  history-rewrite  filter-branch وfilter-repo وreflog expire|delete وgc --prune=now|all وprune
  clean-force      clean -f
  discard-all      checkout|restore . ، وcheckout|switch -f/--discard-changes (إزالةُ شجرةٍ مؤقّتة مسموحةٌ)
  prune-apply      scripts/prune_local_branches ... --apply (حذفُ الفروع يشغّله المالكُ بيده بعد إعادة الأدلّة)

القواعدُ المحلّيّة (كلُّها عدا push-force وpush-delete وpush-bulk) تخصّ هذا المستودعَ وأشجارَه: أمرٌ ينفَّذ في مجلّدٍ خارجه
(`cd /d/shschool-docs && git push origin main`، أو `git -C <مسار خارجيّ>`) لا تسري عليه. ومجلّدٌ غيرُ معلوم (`cd "$P"`) يُعامَل كأنّه فيه.

يفكّ ما يلتفّ به الأمرُ: `git -C x -c k=v push`، والمسارَ الكامل و`git.exe`، و`env`/`sudo`/`command`/`exec`/`time`/`nohup`/`xargs`،
و`bash -c '…'` و`sh -c` و`eval` و`pwsh -Command` و`powershell -EncodedCommand` و`cmd /c`، و`$(…)` وما بين backticks، و`& git`،
وكتلَ `{ … }` في PowerShell، وأسماءَ git المستعارة (`git config alias.*` — بما فيها `!صدفة`). ولا يحلّل أجسامَ heredoc ولا النصَّ بين علامات
الاقتباس (رسالةُ إيداعٍ تذكر `git push --force` لا تُحجب).

التجاوز: إن أذن المالكُ صراحةً في المحادثة بهذا الفعل بعينه فأعِد الأمرَ مسبوقاً بـ GUARD_GIT_ALLOW='<نصُّ الإذن وتاريخُه>' (10 أحرفٍ
فأكثر؛ في PowerShell: $env:GUARD_GIT_ALLOW='…'; …). يُسجَّل في ~/.claude/logs/guard_git_overrides.log. لا يضعه الطرفُ من عنده ولا بطلبِ جلسةٍ أخرى.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import posixpath
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

OVERRIDE_VAR = "GUARD_GIT_ALLOW"
MIN_REASON = 10
MAX_DEPTH = 6
MAIN_REFS = frozenset({"main", "master", "refs/heads/main", "refs/heads/master"})
ARCHIVE_PREFIXES = ("archive/", "refs/tags/archive/", "refs/heads/archive/")
BLANKET_PATHS = frozenset({".", "./", ":/", ":/.", "*", "./*", ":(top)"})
POSIX_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "ash", "fish"})
POWERSHELLS = frozenset({"pwsh", "powershell"})
CONTROL_WORDS = frozenset(
    {
        "if",
        "then",
        "else",
        "elif",
        "fi",
        "while",
        "until",
        "do",
        "done",
        "for",
        "in",
        "case",
        "esac",
    }
    | {"!", "{", "}", "function", "select", "time"}
)
# غلافاتٌ تُنفّذ ما بعدها ← خياراتُها التي تأخذ قيمةً منفصلة
WRAPPERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}),
    "command": frozenset(),
    "builtin": frozenset(),
    "exec": frozenset({"-a"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T", "-U"}),
    "doas": frozenset({"-u", "-C"}),
    "nohup": frozenset(),
    "nice": frozenset({"-n", "--adjustment"}),
    "ionice": frozenset({"-c", "-n", "-p", "-P", "-u"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "setsid": frozenset(),
    "watch": frozenset({"-n", "--interval"}),
    "wsl": frozenset({"-d", "--distribution", "-u", "--user", "--cd"}),
    "xargs": frozenset(
        {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a", "--arg-file", "--delimiter", "--max-args"}
        | {"--max-procs", "--max-lines", "--max-chars", "--eof"}
    ),
}
# أوامرُ git الفرعيّةُ المعروفة: ما خرج عنها قد يكون اسماً مستعاراً فيُسأل عنه `git config`
BUILTINS = frozenset(
    (
        "add am annotate apply archive bisect blame branch bugreport bundle cat-file check-ignore checkout "
        "checkout-index cherry cherry-pick citool clean clone column commit commit-tree config count-objects "
        "credential describe diagnose diff diff-files diff-index diff-tree difftool fast-export fast-import "
        "fetch filter-branch for-each-ref format-patch fsck gc grep gui hash-object help init interpret-trailers "
        "log ls-files ls-remote ls-tree maintenance merge merge-base merge-file merge-tree mergetool mktree mv "
        "name-rev notes pack-objects pack-refs patch-id prune pull push range-diff read-tree rebase reflog "
        "remote repack replace request-pull rerere reset restore rev-list rev-parse revert rm send-email "
        "shortlog show show-branch show-ref sparse-checkout stash status stripspace submodule switch "
        "symbolic-ref tag unpack-file unpack-objects update-index update-ref update-server-info var verify-commit "
        "verify-pack verify-tag version whatchanged worktree write-tree"
    ).split()
)
# خياراتٌ قصيرةٌ تأخذ قيمةً (لفكّ العناقيد `-am` وما شابه)، لكلّ أمرٍ فرعيّ
SHORT_VALUE: dict[str, frozenset[str]] = {
    "commit": frozenset("mFCct"),
    "push": frozenset("o"),
    "clean": frozenset("e"),
    "checkout": frozenset("bBs"),
    "switch": frozenset("cC"),
    "restore": frozenset("s"),
    "branch": frozenset("u"),
    "tag": frozenset("mFu"),
    "stash": frozenset("m"),
    "config": frozenset("f"),
    "update-ref": frozenset("m"),
}
# خياراتٌ قصيرةٌ قيمتُها ملصوقةٌ بها دائماً أو اختياريّاً (`-S<keyid>`): ما بعدها في العنقود قيمةٌ لا خيارات
ATTACHED_VALUE: dict[str, frozenset[str]] = {"commit": frozenset("Su")}
LONG_VALUE: dict[str, frozenset[str]] = {
    "push": frozenset({"--repo", "--receive-pack", "--exec", "--push-option"}),
    "commit": frozenset({"--message", "--file", "--author", "--date", "--fixup", "--squash"}),
    "stash": frozenset({"--message"}),
    "config": frozenset({"--file"}),
    "branch": frozenset(
        {"--set-upstream-to", "--contains", "--merged", "--no-merged", "--sort", "--format"}
    ),
}
GIT_GLOBAL_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}
)
HOOKS_OFF = "لا تجاوزَ لفحوص الإيداع (`--no-verify`، `SKIP=`، `-c core.hooksPath`) — أصلِح ما يفشل بدل إسكاته."


# ── الأنماطُ الناتجة ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Hit:
    rule: str
    message: str


@dataclass
class Analysis:
    hits: list[Hit] = field(default_factory=list)
    override: str = ""


@dataclass
class Ctx:
    powershell: bool
    cwd: str | None
    alias_lookup: Callable[[str], str | None]
    branch_lookup: Callable[[str | None], str | None]  # (مجلّدُ التنفيذ) ← فرعُ الرأس
    family_root: str | None = None  # جذرُ المستودع وأشجارِه (مطبَّعاً)؛ None = غيرُ معلوم فلا استثناء
    cwd_norm: str | None = None
    cur_dir: str | None = None  # بعد `cd` في الأمر نفسِه؛ None = مجلّدُ الجلسة أو غيرُ معلوم
    eff_dir: str | None = None  # مجلّدُ أمر git الجاري تحليلُه
    inline: dict[str, str] = field(default_factory=dict)  # ما ضُبط بـ `git -c k=v` في أمر git الجاري
    env: dict[str, str] = field(
        default_factory=dict
    )  # متغيّراتُ البادئة (`SKIP=… git commit`) في أمر git الجاري


LOCAL_RULES = frozenset(
    {"add-all", "commit-all", "stash", "push-main", "no-verify", "reset-hard", "branch-delete"}
    | {"tag-delete", "ref-delete", "history-rewrite", "clean-force", "discard-all"}
)
CD_COMMANDS = frozenset({"cd", "pushd", "chdir", "set-location", "sl"})


def _norm_dir(path: str | None, base: str | None) -> str | None:
    """مجلّدٌ مطبَّعٌ (شرطاتٌ أماميّة، ومسارُ MSYS `/d/x` ← `D:/x`) أو None إن لم يُعلم (متغيّرٌ أو `~` أو `-`)."""
    if not path or path == "-" or any(ch in path for ch in "$`~*"):
        return None
    p = path.replace("\\", "/")
    m = re.match(r"^/([a-zA-Z])(?:/(.*))?$", p)
    if m:
        p = f"{m.group(1).upper()}:/{m.group(2) or ''}"
    if not (re.match(r"^[a-zA-Z]:/", p) or p.startswith("/")):
        if not base:
            return None
        p = f"{base}/{p}"
    return posixpath.normpath(p)


def _family_root(project_dir: str | None) -> str | None:
    p = _norm_dir(project_dir, None)
    if not p:
        return None
    marker = "/.claude/worktrees/"
    return p.split(marker)[0] if marker in p.lower() else p


def _inside(path: str, root: str) -> bool:
    p, r = path.lower(), root.lower()
    return p == r or p.startswith(r + "/")


def _is_foreign(ctx: Ctx, eff: str | None) -> bool:
    """أمرٌ يُنفَّذ في مجلّدٍ معلومٍ خارجَ هذا المستودع وأشجارِه (مستودعُ الوثائق مثلاً)."""
    return eff is not None and ctx.family_root is not None and not _inside(eff, ctx.family_root)


# ── المُقطِّع: يقسم الأمرَ إلى أوامرَ بسيطةٍ ويستخرج ما بين `$(…)` وbackticks ─────────────


def _heredoc_marker(text: str, i: int) -> tuple[str, bool, int] | None:
    """عند `<<` (لا `<<<`): ← (كلمةُ الإنهاء، هل `<<-`، موضعُ ما بعدها)."""
    j = i + 2
    strip_tabs = False
    if j < len(text) and text[j] == "-":
        strip_tabs, j = True, j + 1
    while j < len(text) and text[j] in " \t":
        j += 1
    m = re.compile(r"""'([^'\n]*)'|"([^"\n]*)"|\\?([^\s;|&<>()'"]+)""").match(text, j)
    if not m:
        return None
    word = next(g for g in m.groups() if g is not None)
    return word, strip_tabs, m.end()


Heredoc = tuple[str, bool, "list[str] | None"]  # (كلمةُ الإنهاء، `<<-`، كلماتُ الأمر صاحبِ العلامة)


def _skip_heredocs(
    text: str, i: int, pending: list[Heredoc]
) -> tuple[int, list[tuple[list[str] | None, str]]]:
    """عند أوّل موضعٍ بعد سطرٍ فيه علاماتُ heredoc: يتخطّى الأجسامَ ← (ما بعد أسطر الإنهاء، [(صاحبُ العلامة، الجسم)])."""
    n = len(text)
    bodies: list[tuple[list[str] | None, str]] = []
    for word, strip_tabs, owner in pending:
        body: list[str] = []
        while i < n:
            j = text.find("\n", i)
            line = text[i : n if j < 0 else j]
            i = n if j < 0 else j + 1
            if (line.lstrip("\t") if strip_tabs else line).rstrip("\r") == word:
                break
            body.append(line)
        bodies.append((owner, "\n".join(body)))
    return i, bodies


def _feeds_a_shell(owner: list[str] | None) -> bool:
    """جسمُ heredoc نصٌّ تنفّذه صدفةٌ (`bash <<EOF`) لا بياناتٌ (`cat <<EOF` و`python - <<EOF` و`git commit -F - <<EOF`)."""
    for w in owner or []:
        if not ASSIGN_RE.match(w):
            return _base(w) in POSIX_SHELLS
    return False


def _read_single(text: str, i: int, powershell: bool) -> tuple[str, int]:
    """محتوى '…' يبدأ عند i (بعد الفاتحة) ← (المحتوى، موضعُ ما بعد الخاتمة). في PowerShell `''` علامةٌ حرفيّة."""
    out: list[str] = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == "'":
            if powershell and i + 1 < n and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(c)
        i += 1
    return "".join(out), n


def _read_double(text: str, i: int, powershell: bool, nested: list[str]) -> tuple[str, int]:
    """محتوى "…" ← (المحتوى، ما بعد الخاتمة)؛ وما فيه من `$(…)` وbackticks يُضاف إلى nested لتُحلَّل أوامرُه."""
    out: list[str] = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            if powershell and i + 1 < n and text[i + 1] == '"':
                out.append('"')
                i += 2
                continue
            return "".join(out), i + 1
        if powershell and c == "`" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        if not powershell and c == "\\" and i + 1 < n and text[i + 1] in '$`"\\\n':
            if text[i + 1] != "\n":
                out.append(text[i + 1])
            i += 2
            continue
        if c == "$" and i + 1 < n and text[i + 1] == "(":
            inner, i = _read_parens(text, i + 2, powershell)
            nested.append(inner)
            out.append("$()")
            continue
        if not powershell and c == "`":
            j = text.find("`", i + 1)
            end = n if j < 0 else j
            nested.append(text[i + 1 : end])
            out.append("`cmd`")
            i = min(end + 1, n)
            continue
        out.append(c)
        i += 1
    return "".join(out), n


def _read_parens(text: str, i: int, powershell: bool) -> tuple[str, int]:
    """ما بين `(` الفاتحة (عند i بعدها) وخاتمتها المتوازنة ← (المحتوى، ما بعد الخاتمة). يتخطّى الاقتباسَ وأجسامَ heredoc."""
    depth, n, start = 1, len(text), i
    pending: list[Heredoc] = []
    while i < n:
        c = text[i]
        if c == "'":
            _, i = _read_single(text, i + 1, powershell)
            continue
        if c == '"':
            _, i = _read_double(text, i + 1, powershell, [])
            continue
        if (c == "\\" and not powershell) or (c == "`" and powershell):
            i += 2
            continue
        if (
            c == "<"
            and not powershell
            and text.startswith("<<", i)
            and not text.startswith("<<<", i)
        ):
            marker = _heredoc_marker(text, i)
            if marker:
                pending.append((marker[0], marker[1], None))
                i = marker[2]
                continue
        if c == "\n" and pending:
            i, _ = _skip_heredocs(text, i + 1, pending)
            pending = []
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    return text[start:], n


def lex(text: str, powershell: bool = False) -> tuple[list[list[str]], list[str]]:
    """الأمرُ ← (أوامرُ بسيطةٌ كلٌّ منها قائمةُ كلمات، نصوصٌ مضمَّنةٌ `$(…)`/backticks تُحلَّل بدورها)."""
    commands: list[list[str]] = []
    nested: list[str] = []
    words: list[str] = []
    buf: list[str] | None = None
    pending: list[Heredoc] = []
    i, n = 0, len(text)

    def end_word() -> None:
        nonlocal buf
        if buf is not None:
            words.append("".join(buf))
            buf = None

    def end_command() -> None:
        nonlocal words
        end_word()
        if words:
            commands.append(words)
        words = []

    def add(piece: str) -> None:
        nonlocal buf
        if buf is None:
            buf = []
        buf.append(piece)

    while i < n:
        c = text[i]
        if c == "\n":
            end_command()
            i += 1
            if pending:
                i, bodies = _skip_heredocs(text, i, pending)
                nested.extend(body for owner, body in bodies if _feeds_a_shell(owner))
                pending = []
            continue
        if c in " \t\r":
            end_word()
            i += 1
            continue
        if c == "\\" and not powershell:
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt == "\n":
                i += 2
            elif nxt and nxt in " \t'\"\\$`;&|<>()*?[]#~!{}":
                add(nxt)
                i += 2
            else:  # مسارُ ويندوز غيرُ مقتبَس: تبقى الشرطةُ حرفيّة
                add(c)
                i += 1
            continue
        if c == "`" and powershell:
            if i + 1 < n:
                add(text[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == "#" and buf is None:
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "'":
            piece, i = _read_single(text, i + 1, powershell)
            add(piece)
            continue
        if c == '"':
            piece, i = _read_double(text, i + 1, powershell, nested)
            add(piece)
            continue
        if c == "$" and i + 1 < n and text[i + 1] == "'" and not powershell:
            piece, i = _read_single(text, i + 2, False)
            add(piece)
            continue
        if c == "$" and i + 1 < n and text[i + 1] == "(":
            inner, i = _read_parens(text, i + 2, powershell)
            nested.append(inner)
            add("$()")
            continue
        if c == "`":
            j = text.find("`", i + 1)
            end = n if j < 0 else j
            nested.append(text[i + 1 : end])
            add("`cmd`")
            i = min(end + 1, n)
            continue
        if c == "@" and powershell and buf is None and i + 1 < n and text[i + 1] in "'\"":
            quote = text[i + 1]
            head = re.compile(r"[ \t]*\r?\n").match(text, i + 2)
            if head:  # here-string في PowerShell: نصٌّ حرفيٌّ حتى سطرٍ يبدأ بـ '@ أو "@
                end = re.compile(r"\r?\n" + re.escape(quote) + "@").search(text, head.end() - 1)
                add("@here@")
                i = end.end() if end else n
                continue
        if (
            c == "<"
            and not powershell
            and text.startswith("<<", i)
            and not text.startswith("<<<", i)
        ):
            marker = _heredoc_marker(text, i)
            if marker:
                end_word()
                pending.append((marker[0], marker[1], words))
                i = marker[2]
                continue
        if c in ";|&":  # وعاملُ الاستدعاء `& git` في PowerShell يفصل فيبقى `git …` أمراً قائماً بذاته
            end_command()
            i += 1
            continue
        if c in "()" or (powershell and c in "{}"):
            end_command()
            i += 1
            continue
        add(c)
        i += 1
    end_command()
    return commands, nested


# ── فكُّ ما يلتفّ به الأمرُ ────────────────────────────────────────────────────


def _base(word: str) -> str:
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECT_RE = re.compile(r"^(?:\d+|&)?(?:>>?|<)(?:&(?:\d+|-))?")


def _strip_redirects(words: list[str]) -> list[str]:
    """يحذف التحويلاتِ (`>f` و`2>&1` و`> f`) فلا تُحسب مواضعَ للأمر."""
    out: list[str] = []
    i = 0
    while i < len(words):
        m = REDIRECT_RE.match(words[i])
        if m:
            operator_only = m.end() == len(words[i]) and not re.search(r"[<>]&", m.group(0))
            i += 2 if operator_only else 1
            continue
        out.append(words[i])
        i += 1
    return out


def _unwrap(name: str, rest: list[str]) -> list[str] | None:
    """ما بعد غلافٍ (خياراتُه ومتغيّراتُه) هو الأمرُ المنفَّذ؛ None إن كان الغلافُ لا ينفّذ شيئاً (`command -v`)."""
    valued = WRAPPERS[name]
    i = 0
    while i < len(rest):
        w = rest[i]
        if w == "--":
            i += 1
            break
        if name == "env" and ASSIGN_RE.match(w):
            i += 1
            continue
        if w.startswith("-") and len(w) > 1:
            if name == "command" and w in ("-v", "-V"):
                return None
            i += 2 if (w in valued and "=" not in w) else 1
            continue
        break
    if name == "timeout" and i < len(rest):
        i += 1  # المدّة
    return rest[i:]


def _c_strings(shell: str, args: list[str]) -> list[str]:
    """النصوصُ التي تنفّذها صدفةٌ: بعد `-c` (وعناقيدِه `-lc`)، أو ما يعقب -Command/-EncodedCommand/`/c`."""
    found: list[str] = []
    if shell in POSIX_SHELLS:
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:] and i + 1 < len(args):
                found.append(args[i + 1])
                break
    elif shell in POWERSHELLS:
        for i, a in enumerate(args):
            low = a.lower()
            if low in ("-command", "-c", "-com", "-comm", "-comma", "-comman"):
                found.append(" ".join(args[i + 1 :]))
                break
            if low in ("-encodedcommand", "-e", "-ec", "-enc", "-encodedc") and i + 1 < len(args):
                try:
                    found.append(base64.b64decode(args[i + 1]).decode("utf-16-le"))
                except ValueError:
                    pass
                break
    elif shell == "cmd":
        for i, a in enumerate(args):
            if a.lower() in ("/c", "/k", "/r"):
                found.append(" ".join(args[i + 1 :]))
                break
    return found


# ── تحليلُ أمر git ──────────────────────────────────────────────────────────────


@dataclass
class Opts:
    longs: set[str] = field(default_factory=set)
    longvals: dict[str, str] = field(default_factory=dict)
    shorts: set[str] = field(default_factory=set)
    pos: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)  # ما بعد `--`


def parse_opts(args: list[str], sub: str) -> Opts:
    """يفكّ الخياراتِ والمواضعَ. العناقيدُ القصيرة (`-am`) تُفكّ حرفاً حرفاً حتى أوّل خيارٍ يأخذ قيمةً."""
    short_value = SHORT_VALUE.get(sub, frozenset())
    attached = ATTACHED_VALUE.get(sub, frozenset())
    long_value = LONG_VALUE.get(sub, frozenset())
    o = Opts()
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            o.after = list(args[i:])
            break
        if a.startswith("--"):
            name, _, val = a.partition("=")
            o.longs.add(name)
            if val:
                o.longvals[name] = val
            elif name in long_value and i < len(args):
                o.longvals[name] = args[i]
                i += 1
            continue
        if len(a) > 1 and a.startswith("-") and not a[1:].isdigit():
            for k, ch in enumerate(a[1:]):
                if ch in attached:
                    break
                if ch in short_value:
                    if k == len(a) - 2 and i < len(args):
                        i += 1  # القيمةُ في الكلمة التالية
                    break
                o.shorts.add("-" + ch)
            continue
        o.pos.append(a)
    return o


def _git_output(args: list[str], cwd: str | None) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],  # noqa: S603, S607 — قائمةُ وسائطَ بلا صدفة، والمُدخَلُ جزءٌ من اسمِ مفتاحٍ لا خيار
            cwd=cwd or None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout.strip() or None) if proc.returncode == 0 else None


def _dst(ref: str) -> str:
    """وجهةُ refspec: ما بعد `:` (بلا `+` في أوّله)، أو المرجعُ نفسُه إن لم يكن فيه `:`."""
    ref = ref.lstrip("+")
    return ref.split(":", 1)[1] if ":" in ref else ref


def _add_all(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "add":
        return None
    o = parse_opts(args, sub)
    if "--dry-run" in o.longs or "-n" in o.shorts:
        return None
    paths = set(o.pos + o.after)
    whole_tree = (o.longs & {"--all", "--update"} or o.shorts & {"-A", "-u"}) and not paths
    if whole_tree or BLANKET_PATHS & paths:
        return "لا `git add -A/--all/-u/.` بلا مساراتٍ — مساراتٍ صريحةٍ وحدَها؛ وإلّا ابتلعتَ عملَ جلسةٍ أخرى نصفَ مكتوب."
    return None


def _commit_all(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "commit":
        return None
    o = parse_opts(args, sub)
    if "--all" in o.longs or "-a" in o.shorts:
        return "لا `git commit -a/--all` — أضِف المساراتِ صراحةً بـ`git add <مسار>` ثمّ أودِع."
    return None


def _stash(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "stash":
        return None
    o = parse_opts(args, sub)
    if o.pos and o.pos[0] in ("list", "show"):
        return None
    return "لا `git stash` — المكدّسُ مشترك: تخبّئ أنت ويستخرج غيرُك. استعمل إيداعاً مؤقّتاً."


def _push_main(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "push":
        return None
    o = parse_opts(args, sub)
    if any(_dst(r) in MAIN_REFS for r in o.pos):
        return "لا دفعَ إلى main مباشرةً — `git push origin HEAD:refs/heads/claude/<اسم-المهمّة>` وطلبُ دمج."
    refs = o.pos[1:]
    if not any(":" in r for r in refs) and (not refs or "HEAD" in refs) and "--all" not in o.longs:
        if ctx.branch_lookup(ctx.eff_dir) in ("main", "master"):
            return "أنت على main — لا دفعَ منه مباشرةً؛ `git push origin HEAD:refs/heads/claude/<اسم-المهمّة>` وطلبُ دمج."
    return None


def _push_force(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "push":
        return None
    o = parse_opts(args, sub)
    if o.longs & {"--force", "--force-with-lease", "--force-if-includes"} or "-f" in o.shorts:
        return "لا force-push (`--force`/`-f`/`--force-with-lease`) — الفرعُ المنشورُ يُحدَّث بإيداعٍ إضافيٍّ أو دمجٍ لا بإعادة كتابة."
    if any(p.startswith("+") for p in o.pos):
        return (
            "لا force-push بـ`+refspec` — الفرعُ المنشورُ يُحدَّث بإيداعٍ إضافيٍّ أو دمجٍ لا بإعادة كتابة."
        )
    return None


def _push_delete(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "push":
        return None
    o = parse_opts(args, sub)
    if (
        o.longs & {"--delete", "--prune", "--mirror"}
        or "-d" in o.shorts
        or any(p.startswith(":") for p in o.pos)
    ):
        return "لا حذفَ مرجعٍ بعيدٍ (`--delete`/`-d`/`:ref`/`--prune`/`--mirror`) — حذفُ الفروع قرارُ المالك بعد إعادة الأدلّة."
    return None


def _push_bulk(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "push":
        return None
    o = parse_opts(args, sub)
    if o.longs & {"--all", "--branches", "--tags"} or any(
        _dst(p).startswith(ARCHIVE_PREFIXES) for p in o.pos
    ):
        return "لا دفعَ جماعيّاً (`--all`/`--branches`/`--tags`) ولا لمرجعٍ تحت `archive/` — وسومُ الأرشفة والفروعُ غيرُ المنشورة قد تحمل ما لا يُنشر (المستودعُ عامّ)."
    return None


def _no_verify(sub: str, args: list[str], ctx: Ctx) -> str | None:
    o = parse_opts(args, sub)
    if "--no-verify" in o.longs or (sub == "commit" and "-n" in o.shorts):
        return HOOKS_OFF
    if sub == "config" and any(p.lower() == "core.hookspath" for p in o.pos) and len(o.pos) >= 2:
        return HOOKS_OFF
    if ctx.inline.get("core.hookspath") is not None:
        return HOOKS_OFF
    if "SKIP" in ctx.env and sub in ("commit", "push", "merge", "rebase", "am", "cherry-pick"):
        return HOOKS_OFF
    return None


def _reset_hard(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub == "reset" and "--hard" in parse_opts(args, sub).longs:
        return "لا `git reset --hard` — يمحو تعديلاتٍ غيرَ مودَعةٍ قد تكون عملَ جلسةٍ أخرى؛ أودِع أوّلاً أو استعمل `--soft`."
    return None


def _branch_delete(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "branch":
        return None
    o = parse_opts(args, sub)
    delete = "--delete" in o.longs or bool(o.shorts & {"-d", "-D"})
    forced = "--force" in o.longs or "-f" in o.shorts
    if "-D" in o.shorts or (delete and forced):
        return "لا حذفَ فرعٍ بالقوّة (`git branch -D`) — قد يُسقط إيداعاتٍ لم تُدمج؛ حذفُ الفروع بيد المالك بعد إعادة الأدلّة (`scripts/prune_local_branches.sh`). و`-d` يرفض ما لم يُدمج."
    return None


def _tag_delete(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "tag":
        return None
    o = parse_opts(args, sub)
    if "--delete" in o.longs or "-d" in o.shorts:
        return "لا حذفَ وسمٍ (`git tag -d`) — وسومُ الأرشفة هي نسخةُ الاسترجاع."
    return None


def _ref_delete(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "update-ref":
        return None
    o = parse_opts(args, sub)
    if ("--delete" in o.longs or "-d" in o.shorts) and not (
        o.pos and o.pos[0].startswith("refs/tmp/")
    ):
        return "لا `git update-ref -d` لمرجعٍ غيرِ `refs/tmp/` — حذفٌ مباشرٌ بلا فحصِ الطرف."
    return None


def _history_rewrite(sub: str, args: list[str], ctx: Ctx) -> str | None:
    o = parse_opts(args, sub)
    rewrite = "لا إعادةَ كتابةِ تاريخٍ ولا محوَ كائنات (`filter-branch`/`filter-repo`/`reflog expire|delete`/`gc --prune=now`/`prune`) — نافذةُ التنظيف قرارُ المالك."
    if sub in ("filter-branch", "filter-repo"):
        return rewrite
    if sub == "reflog" and o.pos and o.pos[0] in ("expire", "delete"):
        return rewrite
    if sub == "gc" and o.longvals.get("--prune", "").lower() in ("now", "all"):
        return rewrite
    if sub == "prune" and "--dry-run" not in o.longs and "-n" not in o.shorts:
        return rewrite
    return None


def _clean_force(sub: str, args: list[str], ctx: Ctx) -> str | None:
    if sub != "clean":
        return None
    o = parse_opts(args, sub)
    forced = "--force" in o.longs or "-f" in o.shorts
    dry = "--dry-run" in o.longs or "-n" in o.shorts
    if forced and not dry:
        return "لا `git clean -f` — يمسح ما لم يُودَع ولا رجوعَ عنه (قد يكون عملَ جلسةٍ أخرى)؛ أضِف `-n` للمعاينة."
    return None


def _discard_all(sub: str, args: list[str], ctx: Ctx) -> str | None:
    discard = "لا تجاهلَ جماعيّاً لتعديلاتٍ غيرِ مودَعة (`checkout|restore .`، `checkout|switch -f`) — سمِّ الملفّاتِ صراحةً."
    o = parse_opts(args, sub)
    if sub in ("checkout", "restore") and BLANKET_PATHS & set(o.pos + o.after):
        staged = "--staged" in o.longs or "-S" in o.shorts
        worktree = "--worktree" in o.longs or "-W" in o.shorts
        return None if (sub == "restore" and staged and not worktree) else discard
    if sub in ("checkout", "switch") and (
        o.longs & {"--force", "--discard-changes"} or "-f" in o.shorts
    ):
        return discard
    return None


GIT_RULES: dict[str, Callable[[str, list[str], Ctx], str | None]] = {
    "add-all": _add_all,
    "commit-all": _commit_all,
    "stash": _stash,
    "push-main": _push_main,
    "push-force": _push_force,
    "push-delete": _push_delete,
    "push-bulk": _push_bulk,
    "no-verify": _no_verify,
    "reset-hard": _reset_hard,
    "branch-delete": _branch_delete,
    "tag-delete": _tag_delete,
    "ref-delete": _ref_delete,
    "history-rewrite": _history_rewrite,
    "clean-force": _clean_force,
    "discard-all": _discard_all,
}
PRUNE_TOOL = re.compile(r"(^|[\\/])prune_local_branches(\.sh|\.py)?$")


def _prune_apply(words: list[str]) -> str | None:
    if any(PRUNE_TOOL.search(w) for w in words) and any(
        w == "--apply" or w.startswith("--apply=") for w in words
    ):
        return "لا `prune_local_branches --apply` من جلسة — حذفُ الفروع يشغّله المالكُ بيده بعد أن تُعاد الأدلّةُ قبله بدقائق (REP-08)."
    return None


WORD_RULES: dict[str, Callable[[list[str]], str | None]] = {"prune-apply": _prune_apply}


def _parse_git(args: list[str]) -> tuple[str, list[str], dict[str, str], list[str]] | None:
    """بعد كلمة git: تُتجاوَز الخياراتُ العامّة ← (الأمرُ الفرعيّ، وسائطُه، ما ضُبط بـ -c، مساراتُ -C)."""
    inline: dict[str, str] = {}
    dirs: list[str] = []
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-c" and i + 1 < len(args):
            key, _, val = args[i + 1].partition("=")
            inline[key.lower()] = val
            i += 2
        elif a == "-C" and i + 1 < len(args):
            dirs.append(args[i + 1])
            i += 2
        elif a in GIT_GLOBAL_VALUE:
            i += 2
        else:
            i += 1
    if i >= len(args):
        return None
    return args[i], args[i + 1 :], inline, dirs


def _resolve_alias(
    sub: str, args: list[str], inline: dict[str, str], ctx: Ctx, depth: int = 0
) -> tuple[str, list[str], str]:
    """يفكّ الاسمَ المستعار ← (الأمرُ الفرعيّ، وسائطُه، نصُّ صدفةٍ إن كان الاسمُ `!…`)."""
    if sub in BUILTINS or depth > MAX_DEPTH:
        return sub, args, ""
    alias = inline.get(f"alias.{sub.lower()}") or ctx.alias_lookup(sub)
    if not alias:
        return sub, args, ""
    alias = alias.strip()
    if alias.startswith("!"):
        return sub, args, alias[1:].strip()
    commands, _ = lex(alias)
    if not commands:
        return sub, args, ""
    return _resolve_alias(commands[0][0], commands[0][1:] + args, inline, ctx, depth + 1)


def _git_hits(args: list[str], env: dict[str, str], ctx: Ctx, depth: int, out: Analysis) -> None:
    parsed = _parse_git(args)
    if not parsed:
        return
    sub, rest, inline, dirs = parsed
    eff = ctx.cur_dir or ctx.cwd_norm
    for d in dirs:
        eff = _norm_dir(d, eff)
    ctx.eff_dir, ctx.inline, ctx.env = eff, inline, env
    foreign = _is_foreign(ctx, eff)
    sub, rest, shell_alias = _resolve_alias(sub, rest, inline, ctx)
    if shell_alias:
        _analyze(shell_alias, ctx, depth + 1, out)
        return
    for rule_id, rule in GIT_RULES.items():
        if foreign and rule_id in LOCAL_RULES:
            continue
        message = rule(sub, rest, ctx)
        if message:
            out.hits.append(Hit(rule_id, message))


def _override_word(words: list[str]) -> str:
    """أوّلُ أمرٍ بسيط: `GUARD_GIT_ALLOW='…'` بادئةً، أو `$env:GUARD_GIT_ALLOW='…'` في PowerShell ← السبب أو ''."""
    if not words:
        return ""
    first = words[0]
    if first.startswith(OVERRIDE_VAR + "="):
        return first.split("=", 1)[1]
    if first.lower().startswith("$env:" + OVERRIDE_VAR.lower()):
        rest = first[len("$env:" + OVERRIDE_VAR) :]
        if rest.startswith("="):
            return rest[1:]
        if rest == "" and len(words) >= 3 and words[1] == "=":
            return words[2]
    return ""


def _analyze_words(raw: list[str], ctx: Ctx, depth: int, out: Analysis) -> None:
    for rule_id, word_rule in WORD_RULES.items():
        message = word_rule(raw)
        if message:
            out.hits.append(Hit(rule_id, message))
    reason = _override_word(raw).strip()
    if len(reason) >= MIN_REASON and not out.override:
        out.override = reason
    words = _strip_redirects(raw)
    env: dict[str, str] = {}
    for _ in range(MAX_DEPTH + 4):
        while words and ASSIGN_RE.match(words[0]):
            key, _, val = words[0].partition("=")
            env[key] = val
            words = words[1:]
        if not words:
            return
        if words[0].startswith("$") and len(words) > 1 and words[1] == "=":
            words = words[2:]  # `$out = git …` في PowerShell: ما بعد `=` هو الأمر
            continue
        head = _base(words[0])
        if head in CONTROL_WORDS or head in ("&", ".", "call"):
            words = words[1:]
            continue
        if head in CD_COMMANDS:
            target = next((w for w in words[1:] if not w.startswith("-")), "")
            ctx.cur_dir = _norm_dir(target, ctx.cur_dir or ctx.cwd_norm)
            return
        if head == "git":
            _git_hits(words[1:], env, ctx, depth, out)
            return
        if head in WRAPPERS:
            inner = _unwrap(head, words[1:])
            if inner is None:
                return
            words = inner
            continue
        if head in ("eval", "iex", "invoke-expression"):
            _analyze(" ".join(words[1:]), ctx, depth + 1, out)
            return
        if head in POSIX_SHELLS or head in POWERSHELLS or head == "cmd":
            for text in _c_strings(head, words[1:]):
                _analyze(text, ctx, depth + 1, out, powershell=head in POWERSHELLS)
            return
        return


def _analyze(
    command: str, ctx: Ctx, depth: int, out: Analysis, powershell: bool | None = None
) -> None:
    if depth > MAX_DEPTH:
        return
    ps = ctx.powershell if powershell is None else powershell
    commands, nested = lex(command, ps)
    for words in commands:
        _analyze_words(words, ctx, depth, out)
    for inner in nested:
        _analyze(inner, ctx, depth + 1, out, ps)


def check(
    command: str,
    *,
    tool: str = "Bash",
    cwd: str | None = None,
    project_dir: str | None = None,
    alias_lookup: Callable[[str], str | None] | None = None,
    branch_lookup: Callable[[str | None], str | None] | None = None,
) -> Analysis:
    """الأمرُ ← ما ينتهكه من القواعد وسببُ التجاوز إن وُجد. الأسماءُ المستعارة وفرعُ الرأس يُسألان عنهما git عند الحاجة فقط."""
    cache: dict[str, str | None] = {}

    def default_alias(name: str) -> str | None:
        if name not in cache:
            cache[name] = _git_output(["config", "--get", f"alias.{name}"], cwd)
        return cache[name]

    def default_branch(where: str | None) -> str | None:
        return _git_output(["symbolic-ref", "--short", "-q", "HEAD"], where or cwd)

    ctx = Ctx(
        powershell=tool == "PowerShell",
        cwd=cwd,
        alias_lookup=alias_lookup or default_alias,
        branch_lookup=branch_lookup or default_branch,
        family_root=_family_root(
            project_dir if project_dir is not None else os.environ.get("CLAUDE_PROJECT_DIR")
        ),
        cwd_norm=_norm_dir(cwd, None),
    )
    out = Analysis()
    _analyze(command, ctx, 0, out)
    unique: list[Hit] = []
    for hit in out.hits:
        if hit not in unique:
            unique.append(hit)
    out.hits = unique
    return out


def _log_override(command: str, reason: str, hits: list[Hit], cwd: str | None) -> None:
    try:
        folder = os.path.join(os.path.expanduser("~"), ".claude", "logs")
        os.makedirs(folder, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{stamp} | {cwd or ''} | {','.join(h.rule for h in hits)} | {reason} | {command[:300]!r}\n"
        with open(os.path.join(folder, "guard_git_overrides.log"), "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return 0
    tool = payload.get("tool_name", "")
    command = payload["tool_input"].get("command", "")
    if tool not in ("Bash", "PowerShell") or not isinstance(command, str) or not command.strip():
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    try:
        result = check(command, tool=tool, cwd=cwd)
    except Exception as exc:  # شبكةُ أمانٍ: خللُ الحارس لا يمنع أمراً
        print(f"guard_git: تعذّر تحليلُ الأمر ({type(exc).__name__}) فمرّ بلا فحص", file=sys.stderr)
        return 0
    if not result.hits:
        return 0
    if result.override:
        _log_override(command, result.override, result.hits, cwd)
        return 0
    first, others = result.hits[0], [h.rule for h in result.hits[1:]]
    print(f"محجوب بحارس الغيت (REP-19) [{first.rule}]: {first.message}", file=sys.stderr)
    if others:
        print(f"وقواعدُ أخرى في الأمر نفسِه: {', '.join(others)}", file=sys.stderr)
    print(
        f"إن أذن المالكُ صراحةً في هذه المحادثة بهذا الفعل بعينه: أعِد الأمرَ مسبوقاً بـ {OVERRIDE_VAR}='<نصُّ الإذن وتاريخُه>' "
        f"(في PowerShell: $env:{OVERRIDE_VAR}='…'; …). لا تضعه من عندك ولا بطلبِ جلسةٍ أخرى.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
