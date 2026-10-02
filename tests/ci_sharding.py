"""تقسيمُ pytest على shards متوازية في CI (W-20261002-034، merge-speedup-8 بند 4).

تُفعَّل بمتغيّرات البيئة `CI_SHARD_INDEX` (من 1) و`CI_SHARD_COUNT` عبر `-p tests.ci_sharding`؛ وبلا
المتغيّرين لا تفعل شيئاً (التشغيلُ المحلّيّ والليليّ كما هما).

**لا يضيع اختبارٌ:** كلُّ shard يجمع المجموعةَ كلَّها بقواعد pytest نفسِها ثمّ يُسقط ما ليس له؛ والإسنادُ دالّةٌ
حتميّةٌ في **ملفّ** الاختبار وحدَه، فكلُّ عنصرٍ مجموعٍ ينتمي إلى shard واحدٍ بالضبط مهما كانت قواعدُ الجمع.
ويكتب `CI_SHARD_REPORT` عدَّ المجموع والمختار، فيتحقّق المُجمِّعُ في CI أنّ مجموعَ المختار = المجموع.

الأوزان: `tests/ci_shard_weights.json` — وسيطُ زمن كلّ ملفٍّ من junit تشغيلاتٍ فعليّة
(`scripts/ci_shard_weights.py refresh`)، ويثبَّت فيه `dedicated` (ملفّاتٌ ثقيلة تذهب إلى آخر shard وحدَها).
ملفٌّ جديدٌ لا وزنَ له يأخذ `default` (وسيطُ الأوزان) فيُوزَّع لا يُهمَل.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

WEIGHTS_FILE = Path(__file__).with_name("ci_shard_weights.json")


def load_weights(path: Path = WEIGHTS_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "weights": data.get("weights", {}),
        "default": float(data.get("default", 1.0)),
        "dedicated": list(data.get("dedicated", [])),
    }


def assign(files, count: int, data: dict) -> dict[str, int]:
    """يُسند كلَّ ملفٍّ إلى shard (1..count): ثابتٌ للمثبَّتات، وحشوٌ جشعٌ بالوزن لبقيّتها. حتميّ."""
    weights, default, dedicated = data["weights"], data["default"], set(data["dedicated"])
    loads = [0.0] * count
    result: dict[str, int] = {}
    for name in sorted(f for f in files if f in dedicated):
        result[name] = count
        loads[count - 1] += weights.get(name, default)
    rest = sorted(
        (f for f in files if f not in dedicated), key=lambda f: (-weights.get(f, default), f)
    )
    for name in rest:
        lightest = min(range(count), key=lambda i: (loads[i], i))
        result[name] = lightest + 1
        loads[lightest] += weights.get(name, default)
    return result


def _file_of(item) -> str:
    return item.nodeid.split("::", 1)[0]


def pytest_collection_modifyitems(config, items):
    raw_count = os.environ.get("CI_SHARD_COUNT")
    raw_index = os.environ.get("CI_SHARD_INDEX")
    if not raw_count or not raw_index:
        return
    count, index = int(raw_count), int(raw_index)
    if not 1 <= index <= count:
        raise ValueError(f"CI_SHARD_INDEX={index} خارج 1..{count}")

    mapping = assign({_file_of(i) for i in items}, count, load_weights())
    selected = [i for i in items if mapping[_file_of(i)] == index]
    deselected = [i for i in items if mapping[_file_of(i)] != index]
    total = len(items)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected

    # عاملٌ واحدٌ يكتب التقرير (gw0 تحت xdist، أو العمليّة الوحيدة بلا xdist).
    report = os.environ.get("CI_SHARD_REPORT")
    worker = getattr(config, "workerinput", {}).get("workerid", "gw0")
    if report and worker == "gw0":
        files = sorted({_file_of(i) for i in selected})
        Path(report).write_text(
            json.dumps(
                {
                    "index": index,
                    "count": count,
                    "total": total,
                    "selected": len(selected),
                    "files": files,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
