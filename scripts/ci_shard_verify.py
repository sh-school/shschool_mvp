#!/usr/bin/env python3
"""يتحقّق المُجمِّعُ أنّ الـshards غطّت المجموعةَ كلَّها بلا فقدٍ ولا تكرار (W-20261002-034).

الاستعمال:  python scripts/ci_shard_verify.py <مجلّد تقارير shard-report-*.json> <عدد الـshards>

يفشل (رمز 1) إن: غاب تقريرُ shard، أو اختلف المجموعُ المجموعُ بين الـshards، أو لم يساوِ مجموعُ المختار
المجموعَ الكلّيّ، أو ظهر ملفٌّ في أكثر من shard. تقاريرُها يكتبها `tests/ci_sharding.py`. وبلا هذا الحارس
قد يسقط ملفٌّ بين الـshards فيمرّ CI أخضرَ بلا أن يُشغَّل اختباره.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def verify(directory: Path, expected: int) -> list[str]:
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.rglob("shard-report-*.json"))]
    problems: list[str] = []
    indexes = sorted(r["index"] for r in reports)
    if indexes != list(range(1, expected + 1)):
        problems.append(f"تقارير الـshards {indexes} لا تساوي 1..{expected} — shard غاب أو تكرّر")
    if any(r["count"] != expected for r in reports):
        problems.append("shard شغّل بعددٍ غير المتوقَّع")
    totals = {r["total"] for r in reports}
    if len(totals) > 1:
        problems.append(f"المجموعُ المجموعُ يختلف بين الـshards: {sorted(totals)}")
    elif totals and sum(r["selected"] for r in reports) != next(iter(totals)):
        problems.append(
            f"مجموعُ المختار {sum(r['selected'] for r in reports)} ≠ الكلّ {next(iter(totals))} — اختبارٌ ضاع أو تكرّر"
        )
    # بياناتُ التغطية أيضاً: لو غاب ملفُّ shard لسقطت تغطيتُه من الدمج بصمتٍ فيُحكم بتغطيةٍ أقلّ (أو بالخطأ أعلى
    # إن اختلّت العتبة) — مراجعة 0105. الأسماءُ `.coverage.shardN` يكتبها pytest-cov بـCOVERAGE_FILE.
    covered = sorted(
        int(p.name.rsplit("shard", 1)[1])
        for p in directory.rglob(".coverage.shard*")
        if p.name.rsplit("shard", 1)[1].isdigit()
    )
    if covered != list(range(1, expected + 1)):
        problems.append(f"ملفّاتُ التغطية .coverage.shardN {covered} لا تساوي 1..{expected} — تغطيةُ shard ستسقط من الدمج")
    seen: dict[str, int] = {}
    for r in reports:
        for name in r["files"]:
            if name in seen and seen[name] != r["index"]:
                problems.append(f"{name} في shardَين: {seen[name]} و{r['index']}")
            seen[name] = r["index"]
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    problems = verify(Path(argv[1]), int(argv[2]))
    if problems:
        for line in problems:
            print(f"::error::{line}")
        return 1
    print(f"الـshards الـ{argv[2]} غطّت المجموعةَ كلَّها بلا فقدٍ ولا تكرار.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
