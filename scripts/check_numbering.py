#!/usr/bin/env python3
"""حارسُ تصادم الترقيم: بادئةُ ADR واحدةٌ لملفٍّ واحد، ورمزُ قيدٍ واحدٌ لقيدٍ واحد — عبر الفروع المفتوحة أيضاً.

وقع التصادمُ مرّتين رصدهما إنسانٌ بعد الدمج لا قبله (ADR-0008/0009 وHC21/HC22، 2026-10-01/02): جلستان
متوازيتان تأخذ كلٌّ منهما «الرقمَ التالي» فتحمل الفروعُ المتوازيةُ الرقمَ نفسَه، وكلٌّ منها أخضرُ وحدَه.

ما يفحصه:
  1. بادئاتُ `docs/adr/NNNN-*.md` فريدةٌ في الشجرة.
  2. ولا تطابق بادئةَ ملفٍّ **مختلفٍ** في `origin/main` (ملفٌّ بالاسم نفسه في main هو الملفُّ نفسُه لا تصادم).
  3. ولا تطابق بادئةَ ملفٍّ مختلفٍ في طلبِ دمجٍ مفتوح — يُذكر رقمُ الطلب. مصدرُ الطلبات `gh pr list` (يلزمه
     `GH_TOKEN` في CI) أو ملفُّ JSON بـ`--prs-json` (للاختبار)؛ وإن تعذّر الوصولُ يُطبع تنبيهٌ ولا يفشل الفحصُ المحلّيّ.
  4. رموزُ القيود (`_hard("HCn"` / `_soft("…"`) في `operations/constraint_registry.py` فريدة.

الاستعمال:  python scripts/check_numbering.py [--root .] [--prs-json ملف] [--skip-prs]   (يخرج بـ1 عند تصادم)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ADR_RE = re.compile(r"^docs/adr/(\d{4})-[^/]+\.md$")
CODE_RE = re.compile(r"""^\s*_(?:hard|soft)\(\s*["']([A-Za-z]+\d+)["']""", re.MULTILINE)
REGISTRY = "operations/constraint_registry.py"
MAIN_REF = "origin/main"


def adr_prefix(path: str) -> str | None:
    match = ADR_RE.match(path)
    return match.group(1) if match else None


def _git(root: Path, *args: str) -> str | None:
    # أوامرُ git ثابتةٌ بلا مدخلٍ خارجيّ
    try:
        result = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.decode("utf-8", "replace")


def tree_adrs(root: Path) -> list[str]:
    out = _git(root, "ls-files", "docs/adr")
    return [p for p in (out or "").splitlines() if adr_prefix(p)]


def main_adrs(root: Path) -> list[str] | None:
    out = _git(root, "ls-tree", "-r", "--name-only", MAIN_REF, "docs/adr")
    if out is None:
        return None
    return [p for p in out.splitlines() if adr_prefix(p)]


def open_pr_adrs(prs: list[dict]) -> list[tuple[int, str]]:
    """(رقمُ الطلب، مسارُ ADR) لكلّ ملفّ ADR في طلبٍ مفتوح — من `gh pr list --json number,files`."""
    found: list[tuple[int, str]] = []
    for pr in prs:
        for entry in pr.get("files") or []:
            path = entry["path"] if isinstance(entry, dict) else str(entry)
            if adr_prefix(path):
                found.append((int(pr["number"]), path))
    return found


def load_prs(prs_json: Path | None) -> list[dict] | None:
    if prs_json is not None:
        return json.loads(prs_json.read_text(encoding="utf-8"))
    try:
        # أمرٌ ثابتٌ بلا مدخلٍ خارجيّ
        result = subprocess.run(  # noqa: S603
            ["gh", "pr", "list", "--state", "open", "--limit", "200", "--json", "number,files"],  # noqa: S607
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return json.loads(result.stdout.decode("utf-8", "replace"))


def adr_collisions(
    tree: list[str],
    main: list[str] | None,
    prs: list[tuple[int, str]] | None,
    own_pr: int | None = None,
) -> list[str]:
    """رسائلُ التصادم — فارغةٌ إن لم يتصادم شيء."""
    problems: list[str] = []
    by_prefix: dict[str, set[str]] = defaultdict(set)
    for path in tree:
        by_prefix[adr_prefix(path) or ""].add(path)
    for prefix, paths in sorted(by_prefix.items()):
        if len(paths) > 1:
            problems.append(f"ADR-{prefix} مكرَّرٌ في الشجرة: {', '.join(sorted(paths))}")
    for prefix, paths in sorted(by_prefix.items()):
        for other in main or []:
            if adr_prefix(other) == prefix and other not in paths:
                problems.append(
                    f"ADR-{prefix} ({', '.join(sorted(paths))}) يتصادم مع ملفٍّ مختلفٍ في main: {other}"
                )
        for number, other in prs or []:
            if number == own_pr or other in paths:
                continue
            if adr_prefix(other) == prefix:
                problems.append(
                    f"ADR-{prefix} ({', '.join(sorted(paths))}) يتصادم مع الطلب المفتوح #{number}: {other}"
                )
    return problems


def code_duplicates(text: str) -> list[str]:
    seen: dict[str, int] = defaultdict(int)
    for code in CODE_RE.findall(text):
        seen[code] += 1
    return [
        f"رمزُ القيد {code} معرَّفٌ {n} مرّات في {REGISTRY}" for code, n in sorted(seen.items()) if n > 1
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--prs-json", type=Path, default=None)
    parser.add_argument("--skip-prs", action="store_true")
    parser.add_argument(
        "--own-pr", type=int, default=None, help="رقمُ هذا الطلب فلا يُعدّ متصادماً مع نفسه"
    )
    args = parser.parse_args(argv)

    problems: list[str] = []
    main_list = main_adrs(args.root)
    if main_list is None:
        print(f"::notice::تعذّر قراءةُ {MAIN_REF} — يُتخطّى فحصُ التصادم مع main.")
    prs = None
    if not args.skip_prs:
        loaded = load_prs(args.prs_json)
        if loaded is None:
            print("::notice::تعذّر الوصولُ إلى الطلبات المفتوحة (gh) — يُتخطّى فحصُ التصادم معها.")
        else:
            prs = open_pr_adrs(loaded)
    problems += adr_collisions(tree_adrs(args.root), main_list, prs, args.own_pr)

    registry = args.root / REGISTRY
    if registry.exists():
        problems += code_duplicates(registry.read_text(encoding="utf-8"))

    if not problems:
        print("لا تصادمَ في ترقيم ADR ولا في رموز القيود.")
        return 0
    print("::error::تصادمُ ترقيمٍ — خُذ الرقمَ التالي الحرّ بعد إعادة الأساس على main:")
    for problem in problems:
        print(f"  {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
