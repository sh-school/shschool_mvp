"""[FILE-SIZE] سقّاطةُ حجم ملفّات الشيفرة — راجع `tests/test_file_size.py`.

الملفُّ الذي يتجاوز `HARD_LIMIT` سطراً تتصادم عليه الجلساتُ المتوازية ويعسُر فهمُه ومراجعتُه
(`attendance.py` بلغ 2200 سطرٍ قبل أن يُفكَّك، و`custom.css` قبله). فالملفُّ الجديد لا يتجاوز
الحدَّ، والقائمُ الذي تجاوزه مسجَّلٌ بحجمه ولا يكبر، وإذا صغُر سُجِّل نقصُه فلا يُنفَق ثانيةً.

الحدُّ إنذارٌ لا حاكمٌ على التصميم: الحكمُ الحقيقيّ مسؤوليّةٌ واحدةٌ لكلّ وحدة، والرقمُ يستدعي
السؤالَ في المراجعة. والنموذجُ عند التجاوز: حزمةٌ حسب المسؤوليّة (`staff_affairs/attendance/`).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "file_size_baseline.json"
HARD_LIMIT = 900
WARN_LIMIT = 600
# هامشٌ لا يُحسب زيادةً: سطرٌ أو سطران في ملفٍّ كبير لا يُسقط جلساتٍ متوازيةً ولا يتصادم فيه السجلّ
# (كلُّ جلسةٍ ستعدّل الأساسَ نفسَه). أمّا نموُّ عشراتِ الأسطر فيسقط.
TOLERANCE = 25

# الهجراتُ مولَّدة، والاختباراتُ تطول بعدد الحالات لا بتعقيدٍ في التصميم.
_SKIP_DIRS = {
    "migrations",
    "tests",
    "node_modules",
    "staticfiles",
    "static",
    "templates",
    "docs",
    "AAdocs",
    "data",
    "__pycache__",
    "worktrees",
    "site-packages",
}


def _is_skipped(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".") or name.startswith("venv")


def measure() -> dict[str, int]:
    """أسطرُ كلّ ملفّ `.py` تجاوز `WARN_LIMIT` (المفتاحُ مسارٌ نسبيٌّ بشرطات مائلة)."""
    sizes: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not _is_skipped(d)]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            lines = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
            if lines >= WARN_LIMIT:
                sizes[path.relative_to(ROOT).as_posix()] = lines
    return dict(sorted(sizes.items()))


def compare(baseline: dict[str, int], current: dict[str, int]) -> tuple[list[str], list[str]]:
    """(الأسوأ، القديم): ملفٌّ جديدٌ فوق الحدّ أو مسجَّلٌ كبُر فوق الهامش؛ ومسجَّلٌ صغُر كثيراً أو نزل تحت الحدّ."""
    worse, stale = [], []
    for path, lines in current.items():
        if path in baseline:
            if lines > baseline[path] + TOLERANCE:
                worse.append(f"{path}: {baseline[path]} → {lines}")
        elif lines > HARD_LIMIT:
            worse.append(f"{path}: {lines} سطراً (الحدُّ {HARD_LIMIT}) وهو غيرُ مسجَّل")
    for path, recorded in baseline.items():
        lines = current.get(path, 0)
        # نزل تحت الحدّ (أو اختفى): يُحذف من الأساس. وصغُر كثيراً: يُثبَّت نقصُه فلا يُنفَق ثانيةً.
        if lines <= HARD_LIMIT or lines < recorded - TOLERANCE:
            stale.append(f"{path}: {recorded} → {lines}")
    return worse, stale


def snapshot() -> dict[str, int]:
    return {p: n for p, n in measure().items() if n > HARD_LIMIT}


def main(argv: list[str]) -> int:
    if "--update" in argv:
        BASELINE.write_text(
            json.dumps(snapshot(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"سُجّل {len(snapshot())} ملفّاً في {BASELINE.name}")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    worse, stale = compare(baseline, measure())
    for line in worse:
        print("WORSE", line)
    for line in stale:
        print("STALE", line)
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
