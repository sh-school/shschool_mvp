"""حقائقُ الفلو الثلاث من `docs/governance/flow.md` ونسخُها المعروفة (W-20261016-015).

المصدرُ الواحد flow.md؛ وأيُّ نسخةٍ معروفةٍ تذكر إصدارَ الفلو أو عددَ دفعات النشر أو رقمَ خطوة الدفع بقيمةٍ
تخالفه يفشل بها حارسُ `tests/test_flow_copies_match.py`. قراءةٌ فقط: لا تعدّل أيَّ ملف.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "docs/governance/flow.md"
#: النسخُ المعروفة صراحةً (لا مسحَ عامّاً للمستودع).
COPIES = (
    "CLAUDE.md",
    ".claude/skills/schoolos-flow/SKILL.md",
    ".claude/skills/schoolos-flow/references/00-contracts.md",
    ".claude/skills/schoolos-flow/references/01-approval-rules.md",
    ".claude/skills/schoolos-flow/references/02-naming-and-numbering.md",
    ".claude/skills/schoolos-flow/references/03-communication-rules.md",
)
_VERSION = re.compile(r"(?:الفلو|work flow|فلو العمل[^\n(]*)\s*\(?\s*v(\d+\.\d+)")
_BATCH_WORDS = {"دفعتا": 2, "دفعتان": 2, "ثلاث دفعات": 3, "أربع دفعات": 4}
_PUSH_STEP = re.compile(r"^(\d+)\.\s+\**[^\n]*ادفع", re.M)


def versions(text: str) -> set[str]:
    return set(_VERSION.findall(text))


def batches(text: str) -> set[int]:
    return {n for word, n in _BATCH_WORDS.items() if re.search(rf"{word}\s+نشر|{word}\s+يومي|{word}\s+نشرٍ", text)}


def push_steps(text: str) -> set[int]:
    return {int(n) for n in _PUSH_STEP.findall(text)}


def facts(text: str) -> dict[str, set]:
    return {"version": versions(text), "batches": batches(text), "push_step": push_steps(text)}


def source_facts(root: Path = ROOT) -> dict[str, set]:
    return facts((root / SOURCE).read_text(encoding="utf-8"))


def mismatches(root: Path = ROOT) -> list[str]:
    """سطورٌ عربيّة: «<الملف>: <الحقيقة> = <قيمة النسخة> والمصدر <قيمة flow.md>»."""
    src = source_facts(root)
    out = []
    for rel in COPIES:
        path = root / rel
        if not path.is_file():
            continue
        got = facts(path.read_text(encoding="utf-8"))
        for key, values in got.items():
            if values and src[key] and not values <= src[key]:
                out.append(f"{rel}: {key} = {sorted(values)} والمصدر {SOURCE} = {sorted(src[key])}")
    return out
