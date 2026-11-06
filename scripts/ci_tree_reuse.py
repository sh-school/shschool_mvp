#!/usr/bin/env python3
"""إعادةُ استعمال فحص الطلب في طابور الدمج — W-20261106-009.

إن كانت شجرةُ git لـ«main + الطلب» في الطابور مطابقةً بايتاً ببايت للشجرة التي فُحصت على الطلب
(تشغيلُ pull_request ناجحٌ لـQuality Gate) فلا حاجةَ لإعادة المجموعة كاملةً: pytest-shards وtest-coverage تُتخطّيان.

الأوامر:
  fingerprint        يطبع بصمةَ شجرة HEAD (يستعملها تشغيلُ الطلب ليرفعها artifact).
  check              يقرّر التطابقَ في الطابور ويكتب `match=true|false` في GITHUB_OUTPUT.

الفشلُ مغلق: أيُّ خطأٍ أو غيابٍ أو شكٍّ ⇒ match=false ⇒ فحصٌ كاملٌ كما كان. ولا يخرج `check` بغير 0.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ARTIFACT_NAME = "tree-fingerprint"
ARTIFACT_FILE = "tree.txt"
WORKFLOW_FILE = "quality-gate.yml"
_TREE_RE = re.compile(r"[0-9a-f]{40}")
# مرجعُ الطابور: refs/heads/gh-readonly-queue/<فرع>/pr-<رقم>-<sha>
_QUEUE_REF_RE = re.compile(r"gh-readonly-queue/.+/pr-(\d+)-[0-9a-f]{7,40}$")


def pr_number(head_ref: str | None) -> int | None:
    """رقمُ الطلب من مرجع الطابور؛ None إن لم يطابق الصيغةَ."""
    match = _QUEUE_REF_RE.search((head_ref or "").strip())
    return int(match.group(1)) if match else None


def valid_tree(value: str | None) -> str | None:
    """بصمةٌ سليمة (40 خانةً ستّ عشريّة) أو None."""
    text = (value or "").strip().lower()
    return text if _TREE_RE.fullmatch(text) else None


def trees_match(local: str | None, reviewed: str | None) -> bool:
    """تطابقٌ تامٌّ بين بصمتَين سليمتَين؛ غيابُ إحداهما أو فسادُها ⇒ لا تطابق."""
    a, b = valid_tree(local), valid_tree(reviewed)
    return a is not None and a == b


def _run(*cmd: str) -> str:
    # أوامرُ ثابتة (git/gh) ووسائطها من بيئة الوظيفة نفسِها لا من مدخلٍ خارجيّ
    return subprocess.run(  # noqa: S603
        cmd, check=True, capture_output=True, text=True, timeout=120
    ).stdout


def local_tree() -> str:
    return _run("git", "rev-parse", "HEAD^{tree}").strip()


def reviewed_tree(repo: str, number: int) -> str | None:
    """بصمةُ الشجرة من artifact آخر تشغيل pull_request ناجحٍ على رأس الطلب؛ None عند أيّ خطأ أو غياب."""
    try:
        head = _run("gh", "api", f"repos/{repo}/pulls/{number}", "--jq", ".head.sha").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            return None
        runs = _run(
            "gh",
            "api",
            f"repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs"
            f"?event=pull_request&status=success&head_sha={head}&per_page=1",
            "--jq",
            ".workflow_runs[0].id // empty",
        ).strip()
        if not runs.isdigit():
            return None
        with tempfile.TemporaryDirectory() as tmp:
            _run("gh", "run", "download", runs, "-R", repo, "-n", ARTIFACT_NAME, "-D", tmp)
            return valid_tree((Path(tmp) / ARTIFACT_FILE).read_text(encoding="utf-8"))
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def decide(repo: str | None, head_ref: str | None) -> bool:
    """هل شجرةُ الطابور مطابقةٌ لما فُحص على الطلب؟ مغلقٌ عند الشك."""
    number = pr_number(head_ref)
    if not repo or number is None:
        return False
    try:
        local = local_tree()
    except (subprocess.SubprocessError, OSError):
        return False
    return trees_match(local, reviewed_tree(repo, number))


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    if command == "fingerprint":
        print(local_tree())
        return 0
    if command == "check":
        try:
            match = decide(os.environ.get("GH_REPO"), os.environ.get("HEAD_REF"))
        except Exception:  # noqa: BLE001 — لا استثناءَ يُسقط الوظيفة؛ الشكُّ فحصٌ كامل
            match = False
        line = f"match={'true' if match else 'false'}"
        print(line)
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return 0
    print("usage: ci_tree_reuse.py fingerprint|check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
