#!/usr/bin/env python3
"""المسارات الحسّاسة: وسمٌ وتعليقٌ على الطلب الذي يمسّها — W-20261002-005.

يقرأ قائمةَ `security/sensitive_paths.json` **من فرع الأساس** (`git show <base>:...`) لا من رأس الطلب،
وإلا أفرغها طلبٌ ليتهرّب. غيابُ الملف أو فسادُه يُفشل الخطوةَ بصوتٍ عالٍ (رمز 2). وجودُ مسارٍ حسّاسٍ
لا يُفشلها: يُنشر وسمٌ وتعليقٌ فقط (لا حجبَ بذاته؛ الإلزامُ لـ0105)، لكنّ فشلَ النشر نفسِه يُفشل الخطوة (رمز 3).

الأوامر:
  scan --base origin/main [--post PR --repo OWNER/NAME]   يطبع الفئات الملموسة ويُنشر الوسمَ عند --post.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

LIST_PATH = "security/sensitive_paths.json"
LABEL = "مراجعة-أمنية-إلزامية"
MARKER = "<!-- sensitive-paths -->"
_TOUCH, _CONTENT = (
    "mandatory_review_when_diff_touches",
    "mandatory_review_when_diff_content_matches",
)


class SensitiveConfigError(Exception):
    """القائمةُ مفقودةٌ أو فاسدة — تُفشل الخطوة ولا تمرّ صامتة."""


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`*` داخل المقطع، `**` عبر المقاطع، و`**/` تقبل الصفرَ من المجلّدات، و`?` حرفٌ واحد."""
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(rf"^{out}$")


def _content_patterns(cat: str, spec: object) -> list[str]:
    pats = spec.get("patterns") if isinstance(spec, dict) else spec
    if not isinstance(pats, list) or not pats or not all(isinstance(p, str) and p for p in pats):
        raise SensitiveConfigError(f"فئةُ المحتوى {cat}: أنماطٌ نصّيّةٌ غير فارغةٍ مطلوبة")
    for p in pats:
        try:
            re.compile(p)
        except re.error as exc:
            raise SensitiveConfigError(f"فئةُ المحتوى {cat}: نمطٌ فاسد {p!r}: {exc}") from exc
    return pats


def load_rules(text: str | None) -> dict:
    if not text or not text.strip():
        raise SensitiveConfigError(f"{LIST_PATH} غائبٌ أو فارغٌ في فرع الأساس")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SensitiveConfigError(f"{LIST_PATH} فاسد: {exc}") from exc
    touches = data.get(_TOUCH) if isinstance(data, dict) else None
    if not isinstance(touches, dict) or not touches:
        raise SensitiveConfigError(f"{_TOUCH} غائبٌ أو ليس قاموساً غير فارغ")
    for cat, pats in touches.items():
        if (
            not isinstance(pats, list)
            or not pats
            or not all(isinstance(p, str) and p for p in pats)
        ):
            raise SensitiveConfigError(f"الفئة {cat}: قائمةُ أنماطٍ نصّيّةٍ غير فارغة مطلوبة")
    content = data.get(_CONTENT, {})
    if not isinstance(content, dict):
        raise SensitiveConfigError(f"{_CONTENT} ليس قاموساً")
    for cat, spec in content.items():
        if cat != "note":
            _content_patterns(cat, spec)
    return data


def match_paths(paths: list[str], rules: dict) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for cat, pats in rules[_TOUCH].items():
        regs = [glob_to_regex(p) for p in pats]
        found = sorted(p for p in paths if any(r.match(p) for r in regs))
        if found:
            hits[cat] = found
    return hits


def added_lines_by_file(diff: str) -> dict[str, list[str]]:
    """الأسطرُ المضافة لكلّ ملفٍّ من فرقٍ موحَّد؛ تُحفظ ببادئة «+».

    ترويسةُ الملف (`+++ `) لا تُقبل إلا داخل ترويسة `diff --git` قبل أوّل `@@`؛ فسطرٌ مضافٌ نصُّه «++ b/x»
    لا يحوّل نسبةَ ما بعده إلى ملفٍّ آخر فيفلت من مرشّح الملفات."""
    files: dict[str, list[str]] = {}
    current: str | None = None
    in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_header, current = True, None
        elif in_header and line.startswith("+++ "):
            name = line[4:]
            current = None if name == "/dev/null" else name.removeprefix("b/")
        elif line.startswith("@@"):
            in_header = False
        elif not in_header and line.startswith("+") and current is not None:
            files.setdefault(current, []).append(line)
    return files


def match_content(diff: str, rules: dict) -> dict[str, list[str]]:
    added = added_lines_by_file(diff)
    hits: dict[str, list[str]] = {}
    for cat, spec in rules.get(_CONTENT, {}).items():
        if cat == "note":
            continue
        regs = [re.compile(p) for p in _content_patterns(cat, spec)]
        file_regs = (
            [glob_to_regex(g) for g in spec.get("files", [])] if isinstance(spec, dict) else []
        )
        found = sorted(
            f
            for f, lines in added.items()
            if (not file_regs or any(r.match(f) for r in file_regs))
            and any(rx.search(line) for line in lines for rx in regs)
        )
        if found:
            hits[cat] = found
    return hits


def scan(paths: list[str], diff: str, rules: dict) -> dict[str, dict[str, list[str]]]:
    return {"paths": match_paths(paths, rules), "content": match_content(diff, rules)}


def render(result: dict[str, dict[str, list[str]]]) -> str:
    lines = [MARKER, f"### مراجعةٌ أمنيّةٌ إلزاميّة — الطلبُ يمسّ مساراتٍ حسّاسة (وسم «{LABEL}»)", ""]
    for kind, title in (("paths", "مسارٌ ملموس"), ("content", "محتوىً مضاف")):
        for cat, files in result[kind].items():
            shown = ", ".join(f"`{f}`" for f in files[:8]) + (
                f" … (+{len(files) - 8})" if len(files) > 8 else ""
            )
            lines.append(f"- **{cat}** ({title}): {shown}")
    lines += ["", "لا حجبَ آليّ هنا؛ المراجعةُ الإلزاميّةُ لـ0105 قبل المعاينة."]
    return "\n".join(lines)


def _run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8")  # noqa: S603


def read_base_list(base: str) -> str | None:
    out = _run(["git", "show", f"{base}:{LIST_PATH}"])
    return out.stdout if out.returncode == 0 else None


def changed(base: str) -> tuple[list[str], str]:
    names = _run(["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"])
    diff = _run(["git", "diff", "--no-renames", "-U0", f"{base}...HEAD"])
    if names.returncode != 0 or diff.returncode != 0:
        raise SensitiveConfigError(f"تعذّر حسابُ الفرق مقابل {base}: {names.stderr or diff.stderr}")
    return [n for n in names.stdout.splitlines() if n.strip()], diff.stdout


def _existing_comment(pr: str, repo: str) -> str | None:
    out = _run(
        [
            "gh",
            "api",
            f"repos/{repo}/issues/{pr}/comments",
            "--paginate",
            "-q",
            ".[]|[.id,.body]|@json",
        ]
    )
    if out.returncode != 0:
        raise RuntimeError(f"تعذّرت قراءةُ التعليقات: {out.stderr.strip()}")
    for line in out.stdout.splitlines():
        cid, body = json.loads(line)
        if MARKER in (body or ""):
            return str(cid)
    return None


def post(pr: str, repo: str, body: str | None) -> None:
    """يضع الوسمَ والتعليقَ (أو يزيلهما إن لم يعد الطلبُ يمسّ شيئاً). أيُّ فشلٍ يرفع RuntimeError فتفشل الخطوة."""
    existing = _existing_comment(pr, repo)
    if body is None:
        if existing:
            _run(["gh", "api", "-X", "DELETE", f"repos/{repo}/issues/comments/{existing}"])
        _run(
            ["gh", "api", "-X", "DELETE", f"repos/{repo}/issues/{pr}/labels/{LABEL}"]
        )  # غيابُه ليس خطأ
        return
    _run(
        [
            "gh",
            "api",
            "-X",
            "POST",
            f"repos/{repo}/labels",
            "-f",
            f"name={LABEL}",
            "-f",
            "color=B60205",
        ]
    )  # موجودٌ مسبقاً: لا بأس
    lab = _run(
        ["gh", "api", "-X", "POST", f"repos/{repo}/issues/{pr}/labels", "-f", f"labels[]={LABEL}"]
    )
    if lab.returncode != 0:
        raise RuntimeError(f"تعذّر وضعُ الوسم: {lab.stderr.strip()}")
    url = (
        f"repos/{repo}/issues/comments/{existing}"
        if existing
        else f"repos/{repo}/issues/{pr}/comments"
    )
    res = _run(
        ["gh", "api", "-X", "PATCH" if existing else "POST", url, "-F", "body=@-"], stdin=body
    )
    if res.returncode != 0:
        raise RuntimeError(f"تعذّر نشرُ التعليق: {res.stderr.strip()}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan")
    sc.add_argument("--base", required=True)
    sc.add_argument("--post", metavar="PR_NUMBER")
    sc.add_argument("--repo")
    args = ap.parse_args()
    try:
        rules = load_rules(read_base_list(args.base))
        paths, diff = changed(args.base)
    except SensitiveConfigError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    result = scan(paths, diff, rules)
    touched = bool(result["paths"] or result["content"])
    print(render(result) if touched else "لا يمسّ مساراً حسّاساً.")
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"sensitive={'true' if touched else 'false'}\n")
    if args.post:
        if not args.repo:
            print("::error::--post يحتاج --repo", file=sys.stderr)
            return 2
        try:
            post(args.post, args.repo, render(result) if touched else None)
        except RuntimeError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
