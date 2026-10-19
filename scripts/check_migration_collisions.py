"""حارسُ تصادم أرقام الهجرات بين الطلبات المفتوحة (W-20261019-002).

العطب: فرعان يضيفان هجرةً بالرقم نفسه في التطبيق نفسه ولا يظهر التصادمُ إلّا عند الدمج
(W-20261004-021 مع #1124)، فيُعاد الترقيمُ ويُعاد الاعتماد. هذا الفحصُ يقارن هجراتِ الفرع المضافة
(عن merge-base) بهجرات الطلبات المفتوحة وبما دخل main بعد الأساس، ويفشل عند تكرار الرقم.

الاستعمال:   python scripts/check_migration_collisions.py [--base origin/main]
الخروج:      0 لا تصادم، 1 تصادم، 3 غير مقيس (gh أو الشبكة أو git غائب) — لا نجاحَ صامتاً.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

MIGRATION_RE = re.compile(r"^(?P<app>[\w./-]+?)/migrations/(?P<num>\d{4})_[\w]+\.py$")

OK, COLLISION, MISSING = 0, 1, 3


class NotMeasuredError(Exception):
    """أداةٌ أو شبكةٌ غائبة فلا قياسَ."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")  # noqa: S603
    except FileNotFoundError as exc:
        raise NotMeasuredError(f"{cmd[0]} غير مثبَّت") from exc


def migration_keys(paths: list[str]) -> dict[tuple[str, str], str]:
    """(التطبيق، الرقم) ← المسار، لأوراق الهجرات وحدَها."""
    keys: dict[tuple[str, str], str] = {}
    for path in paths:
        match = MIGRATION_RE.match(path)
        if match:
            keys[(match["app"], match["num"])] = path
    return keys


def find_collisions(
    mine: list[str], others: dict[str, list[str]]
) -> list[tuple[str, str, str, str, str]]:
    """(التطبيق، الرقم، صاحب التصادم، ملفّي، ملفّه) — الملفُّ ذاتُه ليس تصادماً."""
    own = migration_keys(mine)
    found = []
    for label, paths in others.items():
        for key, other_path in migration_keys(paths).items():
            own_path = own.get(key)
            if own_path and own_path != other_path:
                found.append((key[0], key[1], label, own_path, other_path))
    return found


def branch_added_paths(base: str) -> tuple[list[str], str]:
    merge_base = _run(["git", "merge-base", "HEAD", base])
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        raise NotMeasuredError(f"تعذّر merge-base مع {base}")
    sha = merge_base.stdout.strip()
    committed = _run(["git", "diff", "--name-only", "--diff-filter=A", sha, "HEAD"])
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"])
    if committed.returncode != 0:
        raise NotMeasuredError("تعذّر git diff")
    return sorted(set(committed.stdout.splitlines()) | set(untracked.stdout.splitlines())), sha


def main_added_since(base: str, merge_base: str) -> list[str]:
    diff = _run(["git", "diff", "--name-only", "--diff-filter=A", merge_base, base])
    if diff.returncode != 0:
        raise NotMeasuredError("تعذّر git diff لـmain")
    return diff.stdout.splitlines()


def _gh_json(args: list[str]):
    proc = _run(["gh", *args])
    if proc.returncode != 0:
        raise NotMeasuredError(f"gh فشل: {(proc.stderr or '').strip()[:120]}")
    try:
        return json.loads(proc.stdout or "null")
    except ValueError as exc:
        raise NotMeasuredError("ردُّ gh ليس JSON") from exc


def open_pull_requests() -> dict[str, dict]:
    """الطلبات المفتوحة: «#رقم (فرع)» ← {head: sha, files: [المضافة]}."""
    prs = _gh_json(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,headRefName,headRefOid",
        ]
    )
    result = {}
    for pr in prs or []:
        files = _gh_json(
            ["api", f"repos/{{owner}}/{{repo}}/pulls/{pr['number']}/files", "--paginate", "--slurp"]
        )
        added = [f["filename"] for page in files or [] for f in page if f.get("status") == "added"]
        result[f"#{pr['number']} ({pr['headRefName']})"] = {
            "head": pr["headRefOid"],
            "branch": pr["headRefName"],
            "files": added,
        }
    return result


def current_branch_and_head() -> tuple[str, str]:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    return branch, head


def is_own_pr(info: dict, branch: str, head: str) -> bool:
    return info["head"] == head or info["branch"] == branch or info["branch"].endswith("/" + branch)


def run(base: str = "origin/main") -> tuple[int, str]:
    try:
        mine, merge_base = branch_added_paths(base)
        if not migration_keys(mine):
            return OK, "لا هجرةَ مضافةً في الفرع — لا تصادمَ ممكن"
        branch, head = current_branch_and_head()
        others = {
            label: info["files"]
            for label, info in open_pull_requests().items()
            if not is_own_pr(info, branch, head)
        }
        others[f"{base} بعد الأساس"] = main_added_since(base, merge_base)
    except NotMeasuredError as exc:
        return MISSING, f"غير مقيس: {exc}"
    collisions = find_collisions(mine, others)
    if not collisions:
        return OK, f"لا تصادمَ مع {len(others) - 1} طلباً مفتوحاً ولا مع main"
    lines = [
        f"تصادم: التطبيق {app} الرقم {num} مع {label}: ملفّك {own} وملفّه {theirs}"
        for app, num, label, own, theirs in collisions
    ]
    return COLLISION, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="تصادمُ أرقام الهجرات بين الطلبات المفتوحة")
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    code, message = run(args.base)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
