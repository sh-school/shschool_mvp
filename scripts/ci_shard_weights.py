#!/usr/bin/env python3
"""يولّد `tests/ci_shard_weights.json` من تقارير junit لتشغيلات CI فعليّة (W-20261002-034).

الاستعمال:
    python scripts/ci_shard_weights.py refresh test-results.xml [more.xml …] [--dedicated tests/x.py …]

الوزنُ = **أدنى** مجموعِ زمن اختبارات كلّ ملفٍّ عبر التقارير التي ظهر فيها. الأدنى لا الوسيط ولا المتوسّط: أوّلُ
اختبارٍ يمسّ قاعدةَ البيانات في كلّ عاملِ xdist يحمل كلفةَ إنشائها (~190–350 ث) وهو ملفٌّ ثابتٌ تقريباً في
التشغيلات (قِيس: أربعةُ ملفّاتٍ بوزن ~330 ث بالوسيط وهي ثوانٍ قليلةٌ في تشغيلٍ آخر)، فالوسيطُ يُبقي الشاذّةَ
والأدنى يُسقطها. وهو تحيّزٌ معلنٌ: يُقلّل الملفّاتِ الثقيلةَ فعلاً في مشغّلٍ بطيء؛ والغرضُ توازنٌ نسبيّ لا
تقديرُ زمن. الملفّاتُ المثبَّتةُ (`--dedicated`) تذهب إلى آخر shard وحدَها.

تحديثُه اختياريٌّ للدقّة لا للصحّة: ملفٌّ بلا وزنٍ يأخذ الوسيطَ فيُوزَّع ولا يضيع (انظر tests/ci_sharding.py).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

OUT = Path("tests/ci_shard_weights.json")


def resolve_file(classname: str, root: Path) -> str | None:
    """classname في junit (`tests.test_x.Class`) ← مسار الملفّ النسبيّ، بتجريب الأطول فالأقصر."""
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end])
        if (root / f"{candidate}.py").is_file():
            return f"{candidate}.py"
    return None


def per_file_seconds(junit: Path, root: Path) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = resolve_file(case.get("classname", ""), root)
        if name:
            totals[name] += float(case.get("time", 0))
    return totals


def refresh(junits: list[Path], dedicated: list[str], root: Path = Path(".")) -> dict:
    runs = [per_file_seconds(j, root) for j in junits]
    files = set().union(*runs) if runs else set()
    weights = {f: round(min(r[f] for r in runs if f in r), 1) for f in sorted(files)}
    default = round(statistics.median(weights.values()), 1) if weights else 1.0
    return {"default": default, "dedicated": sorted(dedicated), "weights": weights}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    ref = sub.add_parser("refresh")
    ref.add_argument("junit", nargs="+", type=Path)
    ref.add_argument("--dedicated", nargs="*", default=[])
    args = parser.parse_args(argv)

    data = refresh(args.junit, args.dedicated)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(data['weights'])} ملفّاً، الافتراضيُّ {data['default']} ث، المثبَّت: {data['dedicated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
