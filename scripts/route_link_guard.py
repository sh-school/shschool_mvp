"""scripts/route_link_guard.py — حارسُ روابط المسارات الجديدة (استشاري) — W-20261106-025.

عيبُ #1367: شاشةٌ جديدةٌ بمسارٍ جديدٍ لا يصل إليها المستخدمُ من أيّ مكان، لأنّ رابطها الوحيد
في قالبها هي. هذا الحارسُ نصّيٌّ خالصٌ بلا Django ولا خطّ أساس: يقرأ نصَّ `git diff` ويفحص
المسارات المضافة فيه وحدَها، فلا تدخل المسارات القديمةُ أبداً.

القواعد:
* يجمع من الأسطر المضافة في `**/urls.py` كلَّ `path(...)` أو `re_path(...)` له `name=`
  (ولو توزّع على عدّة أسطر)، و`app_name` من الملفّ.
* يتجاهل المسارَ ذا المعامل `<...>` أو الذي أحدُ أجزائه `api` أو `export` أو `download`
  أو `pdf` أو `xlsx` أو `webhook`. (`pdf` و`xlsx` تصديرُ ملفٍّ لا شاشةٌ، ورابطُه في قالب الشاشة نفسها.)
* يعدّ المسارَ مرتبطاً إذا ورد `app:name` في `{% url %}` أو `reverse` أو `redirect`، أو ورد
  مساره في `href`، داخل ملفٍّ ليس جديداً في هذا الفرق (فالرابطُ الذاتيّ في قالبٍ جديدٍ لا يُحتسب).

المخرج: قائمةُ المسارات المخالفة، ورمزُ الخروج 1 عند وجودها.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

IGNORED_SEGMENTS = frozenset({"api", "export", "download", "pdf", "xlsx", "webhook"})

_PATH_START_RE = re.compile(r"\b(?:re_path|path)\(")
_STRING_RE = re.compile(r"""[rb]?(["'])(.*?)\1""", re.DOTALL)
_NAME_RE = re.compile(r"""\bname\s*=\s*(["'])(.+?)\1""")
_APP_NAME_RE = re.compile(r"""^\s*app_name\s*=\s*(["'])(.+?)\1""", re.MULTILINE)


@dataclass
class FileDiff:
    path: str
    is_new: bool = False
    added: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NewRoute:
    file: str
    app_name: str
    route: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.app_name}:{self.name}" if self.app_name else self.name


def parse_diff(diff_text: str) -> list[FileDiff]:
    """يقسّم نصَّ diff إلى ملفّاته مع الأسطر المضافة وأسطر السياق."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    pending_new = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current = None
            pending_new = False
        elif line.startswith("--- "):
            pending_new = line.strip() == "--- /dev/null"
        elif line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current = None
            else:
                current = FileDiff(path=target.removeprefix("b/"), is_new=pending_new)
                files.append(current)
        elif current is None:
            continue
        elif line.startswith("+"):
            current.added.append(line[1:])
        elif line.startswith(" "):
            current.context.append(line[1:])
    return files


def _balanced_call(text: str, open_index: int) -> str:
    """نصُّ ما بين القوسين المتقابلين ابتداءً من قوسٍ مفتوح؛ يتجاوز النصوصَ الحرفيّة."""
    depth = 0
    quote = ""
    for i in range(open_index, len(text)):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : i]
    return text[open_index + 1 :]


def extract_new_routes(
    files: list[FileDiff], read_file: Callable[[str], str] | None = None
) -> list[NewRoute]:
    """المسارات المسمّاة المضافة في ملفّات urls.py، مع app_name من الملفّ."""
    routes: list[NewRoute] = []
    for f in files:
        if PurePosixPath(f.path).name != "urls.py":
            continue
        added_text = "\n".join(f.added)
        seen_text = "\n".join(f.context + f.added)
        match = _APP_NAME_RE.search(seen_text)
        if not match and read_file is not None:
            match = _APP_NAME_RE.search(read_file(f.path))
        app_name = match.group(2) if match else ""
        for start in _PATH_START_RE.finditer(added_text):
            call = _balanced_call(added_text, start.end() - 1)
            route_match = _STRING_RE.match(call.lstrip())
            name_match = _NAME_RE.search(call)
            if not route_match or not name_match:
                continue
            routes.append(NewRoute(f.path, app_name, route_match.group(2), name_match.group(2)))
    return routes


def is_checked(route: str) -> bool:
    """هل يُفحص هذا المسار؟ لا فحصَ للمعاملات ولا لمسارات الواجهة البرمجيّة والتنزيل."""
    if "<" in route or "(?P" in route:
        return False
    return not IGNORED_SEGMENTS & set(route.strip("/").split("/"))


def is_linked(route: NewRoute, files: list[FileDiff]) -> bool:
    """هل ورد رابطُ المسار في أسطرٍ مضافةٍ بملفٍّ غير جديدٍ (وليس urls.py ولا اختباراً)؟"""
    full = re.escape(route.full_name)
    patterns = [
        re.compile(r"""\{%\s*url\s+(["'])""" + full + r"\1"),
        re.compile(r"""\b(?:reverse|reverse_lazy|redirect)\(\s*(["'])""" + full + r"\1"),
    ]
    if route.route.strip("/"):
        patterns.append(
            re.compile(r"""href\s*=\s*(["'])[^"']*""" + re.escape(route.route) + r"""["'?#]""")
        )
    for f in files:
        parts = PurePosixPath(f.path).parts
        if f.is_new or "tests" in parts or parts[-1] == "urls.py":
            continue
        text = "\n".join(f.added)
        if any(p.search(text) for p in patterns):
            return True
    return False


def find_violations(
    diff_text: str, read_file: Callable[[str], str] | None = None
) -> list[NewRoute]:
    files = parse_diff(diff_text)
    return [
        r
        for r in extract_new_routes(files, read_file)
        if is_checked(r.route) and not is_linked(r, files)
    ]


def _read_working_tree(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="قاعدة الطلب")
    parser.add_argument("--head", default="HEAD", help="رأس الطلب")
    parser.add_argument("--diff-file", help="ملفّ diff جاهز بدل git")
    args = parser.parse_args(argv)
    if args.diff_file:
        with open(args.diff_file, encoding="utf-8") as fh:
            diff_text = fh.read()
    elif args.base:
        # وسائطُ ثابتةٌ بلا shell.
        argv_git = ["git", "diff", "--unified=3", f"{args.base}...{args.head}"]
        diff_text = subprocess.run(  # noqa: S603
            argv_git, check=True, capture_output=True, text=True, encoding="utf-8"
        ).stdout
    else:
        diff_text = sys.stdin.read()
    violations = find_violations(diff_text, _read_working_tree)
    for v in violations:
        print(f"مسارٌ جديدٌ بلا رابطٍ من خارج شاشته: {v.full_name} ({v.route!r}) في {v.file}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
