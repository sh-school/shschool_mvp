#!/usr/bin/env python3
"""فحصُ CI: سطرُ الاعتماد في وصف الطلب يطابق رأسَه (W-20261003-003).

الفلو (docs/governance/flow.md، الخطوة 7): وصفُ الطلب فيه «اعتُمد من المالك على 8500 — <التاريخ> — الرأس <sha8>»، أو
سطرُ التفويض المسجَّل «اعتُمد بتفويض 0101 على الرأس <sha> — <التاريخ>». فرأسٌ زائدٌ بعد الاعتماد (إيداعٌ أو دفعٌ لاحق) يترك
السطرَ على رأسٍ قديم، وهذا الفحصُ يُسقط الطلبَ حينها بدل أن يعتمد الدامجُ على نظره.

المنطقُ نفسُه الذي في `pr_evidence.py` (مصدرٌ واحدٌ للتعابير: `auto_merge_gate.APPROVAL` و`pr_evidence.DELEGATED`)،
لا منطقَ ثانٍ. ولا يقرأ هذا الفحصُ دفترَ المايسترو (خارج المستودع)؛ شاهدُه وصفُ الطلب ورأسُه من GitHub وحدَهما.

الحكم:
  - مستثنى: مؤلّفٌ آليّ (`dependabot[bot]` وأمثالُه ينتهي اسمُه بـ`[bot]`) — لا يمرّ بفلو الاعتماد البشريّ.
  - ✘ no_line: لا سطرَ اعتمادٍ أصلاً.
  - ✘ no_head: سطرُ المالك بلا «الرأس <sha>» (لا ربطَ بالرأس).
  - ✘ stale_head: كلُّ الأسطر على رؤوسٍ لا تطابق رأسَ الطلب الحاليّ.
  - ✔ ok: سطرٌ واحدٌ على الأقلّ يطابق الرأسَ (بادئةٌ مشتركةٌ من 7 أحرفٍ فأكثر).

    python scripts/pr_approval_head_check.py <رقم الطلب> [--repo owner/name]

رمز الخروج: 0 ناجح أو مستثنى، 1 فشل الاعتماد، 2 خطأ قراءةٍ من GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_merge_gate as gate  # noqa: E402
import pr_evidence as ev  # noqa: E402

MIN_HEAD = 7

#: سطرُ المالك بصيغتي gate.APPROVAL مع «— الرأس <sha>» اختياريّاً (غيابُه فشلُ ربطٍ لا غيابُ سطر).
OWNER_HEAD = re.compile(
    gate.APPROVAL.pattern + r"(?: — الرأس ([0-9a-f]{7,40}))?",
)


def same_head(written: str, head: str) -> bool:
    """بادئةٌ مشتركةٌ من MIN_HEAD أحرفٍ فأكثر (الدفترُ يحمل 7 أو 8 أحرف)."""
    written, head = written.lower(), head.lower()
    return (
        len(written) >= MIN_HEAD
        and len(head) >= MIN_HEAD
        and (head.startswith(written) or written.startswith(head))
    )


def is_automation(author: str, is_bot: bool = False) -> bool:
    """gh يعيد الآليَّ بـ`is_bot` واسمٍ مثل `app/dependabot` (وفي REST `dependabot[bot]`)."""
    return is_bot or author.startswith("app/") or author.endswith("[bot]")


def verdict(body: str, head: str, author: str = "", is_bot: bool = False) -> tuple[str, str]:
    """(الحالة، الرسالة) — حكمٌ نقيٌّ بلا شبكة."""
    if is_automation(author, is_bot):
        return "exempt", f"مؤلّفٌ آليّ ({author}): خارجَ فلو الاعتماد البشريّ"
    owner = list(OWNER_HEAD.finditer(body or ""))
    delegated = ev.DELEGATED.findall(body or "")
    if not owner and not delegated:
        return "no_line", "لا سطرَ اعتمادٍ في وصف الطلب"
    written = [m.group(1) for m in owner if m.group(1)] + delegated
    if any(same_head(w, head) for w in written):
        return "ok", "سطرُ الاعتماد يطابق الرأس"
    if not written:
        return "no_head", "سطرُ اعتماد المالك بلا «— الرأس <sha8>»: لا ربطَ بالرأس"
    return (
        "stale_head",
        f"سطرُ الاعتماد على رأسٍ قديم ({', '.join(w[:8] for w in written)}) والرأسُ الحاليّ {head[:8]}",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("number")
    ap.add_argument("--repo")
    args = ap.parse_args(argv)
    cmd = ["gh", "pr", "view", args.number, "--json", "body,headRefOid,author"] + (
        ["--repo", args.repo] if args.repo else []
    )
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", check=False)  # noqa: S603
    if proc.returncode != 0:
        print(f"تعذّرت قراءةُ الطلب: {proc.stderr.strip()[:200]}", file=sys.stderr)
        return 2
    data = json.loads(proc.stdout)
    state, message = verdict(
        data.get("body") or "",
        data.get("headRefOid") or "",
        (data.get("author") or {}).get("login", ""),
    )
    ok = state in ("ok", "exempt")
    print(f"{'✔' if ok else '✘'} {state}: {message}")
    if not ok:
        print(
            "::error::سطرُ الاعتماد لا يطابق رأسَ الطلب — يفتح الطلبَ 0601 بعد ✔ approval_check ويكتب "
            "«اعتُمد من المالك على 8500 — <التاريخ> — الرأس <sha8>»",
            file=sys.stderr,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
