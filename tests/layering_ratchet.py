"""سقّاطةُ الطبقات — العرضُ يستقبل ويردّ، والقراءةُ والكتابةُ في طبقتيهما.

الخدماتُ في المنصّة موجودةٌ منذ زمن (`student_affairs/services.py`،
`analytics/services.py`…) لكنّها لم تكن مُلزِمة: `student_affairs/views.py`
بلغ 2616 سطراً، وأثقلُ عروضه مئتا سطرٍ بخمسةٍ وعشرين استدعاءَ ORM. والترحيلُ
كلُّه في طلب دمجٍ واحدٍ لا يُراجَع — فالحارسُ هنا، كسقّاطة الهويّة البصريّة،
لا يطلب الصفرَ دفعةً واحدة بل يمنع الزيادة ويُثبّت كلَّ نقص:

1. **كلُّ دالّةٍ في ملفّ عروض** (`*/views*.py`) — العرضُ نفسُه ومساعدُه وتوابعُ
   أصنافه: سقفُها 60 سطراً (من سطر `def` إلى آخره، بلا المزيِّنات) و5 استدعاءاتِ
   ORM مباشرة (`.objects`، `.filter(`، `.annotate(`، `.aggregate(`،
   `select_related(`، `prefetch_related(`، `Q(`). وكان العدُّ على ما أوّلُ وسائطه
   `request` وحدَه، فنقلُ الاستعلام إلى `_get_director_ctx(school, today)` في
   الملفّ نفسِه — ستٌّ وأربعون استدعاءً — كان يُخفيه عن الحارس.
2. **`core` لا يستورد وحدةً نازلة** — ولا استيراداً كسولاً داخل دالّة: الكسلُ
   يؤخّر الخطأ الدائريّ ولا يُزيل الاقتران. والعدُّ لكلّ وحدةٍ نازلة على النواة
   كلِّها لا لكلّ ملفّ: الاعتمادُ اعتمادُ الحزمة، ونقلُ قراءةٍ من عرضٍ في النواة
   إلى قارئٍ في النواة لا يزيده ولا ينقصه.
3. **`get_school()` في ملفّات العروض** — `request.school` يضعه
   `SchoolContextMiddleware` مرّةً لكلّ طلب.

وقواعدُ السجلّ (`tests/layering_baseline.json`):

* ما تحت السقف لا يُكتب. عرضٌ جديدٌ فوق السقف يسقط — فالجديدُ يُكتب نظيفاً.
* المسجَّلُ **زاد** → يسقط. **نقص** → يسقط كذلك حتى يُثبَّت نقصُه، فلا يبقى
  التحسّنُ هامشاً يُملأ بمخالفةٍ أخرى في العرض نفسه.
* تغييرُ اسم عرضٍ مسجَّل يُسقطه: القديمُ نقص، والجديدُ فوق السقف بلا سجلّ.

والعدُّ بشجرة `ast` لا بالتعابير النمطيّة: التعليقُ والنصُّ لا يُعدّان، ونهايةُ
الدالّة لا تُخمَّن بالمسافة البادئة، والنتيجةُ واحدةٌ على 3.11 محلّيّاً و3.12 في CI.

تثبيتُ النقص (لا يقبل زيادةً — يرفض ويُسمّيها):

    python -m tests.layering_ratchet --update

وإعادةُ القياس من الصفر حين يتغيّر **تعريفُ** العدّ نفسُه — قرارٌ يُراجَع سطراً سطراً:

    python -m tests.layering_ratchet --rebaseline
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
from collections import Counter
from collections.abc import Iterator

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "layering_baseline.json"

MAX_LINES = 60
MAX_ORM = 5

#: توابعُ QuerySet المعدودة — ومعها الوصولُ إلى `.objects` وبناءُ `Q(`.
ORM_METHODS = frozenset({"filter", "annotate", "aggregate", "select_related", "prefetch_related"})

#: ما ليس وحدةً نازلة: النواةُ نفسُها، وإعداداتُ المشروع، والاختبارات.
NOT_DOWNSTREAM = frozenset({"core", "shschool", "tests"})

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def downstream_apps(root: pathlib.Path = ROOT) -> frozenset[str]:
    """كلُّ حزمةٍ في الجذر غيرُ النواة — تُكتشف ولا تُسرد، فالتطبيقُ الجديدُ نازلٌ من يومه."""
    return frozenset(
        p.parent.name for p in root.glob("*/__init__.py") if p.parent.name not in NOT_DOWNSTREAM
    )


# ─── القياس ────────────────────────────────────────────────────────────────


def _orm_calls(node: ast.AST) -> int:
    count = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "objects":
            count += 1
        elif isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute) and func.attr in ORM_METHODS | {"Q"}:
                count += 1
            elif isinstance(func, ast.Name) and func.id == "Q":
                count += 1
    return count


def _get_school_calls(node: ast.AST) -> int:
    count = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if (isinstance(func, ast.Attribute) and func.attr == "get_school") or (
                isinstance(func, ast.Name) and func.id == "get_school"
            ):
                count += 1
    return count


def _views(tree: ast.Module) -> Iterator[tuple[str, FunctionNode]]:
    """(الاسم، العقدة) لكلّ دالّةٍ في رأس ملفّ العروض ولكلّ تابعٍ في أصنافه."""
    for node in tree.body:
        if isinstance(node, FUNCTION_NODES):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, FUNCTION_NODES):
                    yield f"{node.name}.{item.name}", item


def measure_views(source: str, path: str) -> tuple[dict[str, dict[str, int]], int]:
    """(ما فوق السقف من عروض الملفّ، عددُ `get_school()` فيه كلِّه)."""
    tree = ast.parse(source)
    over: dict[str, dict[str, int]] = {}
    for name, node in _views(tree):
        lines = (node.end_lineno or node.lineno) - node.lineno + 1
        orm = _orm_calls(node)
        excess = {}
        if lines > MAX_LINES:
            excess["lines"] = lines
        if orm > MAX_ORM:
            excess["orm"] = orm
        if excess:
            over[f"{path}::{name}"] = excess
    return over, _get_school_calls(tree)


def measure_core_imports(source: str, downstream: frozenset[str]) -> dict[str, int]:
    """وحدةٌ نازلة ← عددُ جُمل الاستيراد منها — في أيّ عمقٍ من الملفّ."""
    found: Counter[str] = Counter()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for top in {name.split(".", 1)[0] for name in names} & downstream:
            found[top] += 1
    return dict(sorted(found.items()))


def view_files(root: pathlib.Path = ROOT) -> list[pathlib.Path]:
    """ملفّاتُ العروض في تطبيقات المشروع — حزمٌ في الجذر، لا مجلّداتٌ مخفيّةٌ ولا نسخٌ مؤقّتة."""
    files = set(root.glob("*/views*.py")) | set(root.glob("*/views/*.py"))
    return sorted(
        p
        for p in files
        if (root / p.relative_to(root).parts[0] / "__init__.py").is_file()
        and p.relative_to(root).parts[0] not in {"shschool", "tests"}
    )


def snapshot(root: pathlib.Path = ROOT) -> dict:
    views: dict[str, dict[str, int]] = {}
    get_school: dict[str, int] = {}
    for path in view_files(root):
        rel = path.relative_to(root).as_posix()
        over, calls = measure_views(path.read_text(encoding="utf-8"), rel)
        views.update(over)
        if calls:
            get_school[rel] = calls

    downstream = downstream_apps(root)
    core_imports: Counter[str] = Counter()
    sites: dict[str, list[str]] = {}
    for path in sorted((root / "core").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for app, count in measure_core_imports(
            path.read_text(encoding="utf-8"), downstream
        ).items():
            core_imports[app] += count
            sites.setdefault(app, []).append(path.relative_to(root).as_posix())

    return {
        "views": views,
        "get_school": get_school,
        "core_imports": dict(sorted(core_imports.items())),
        # للقارئ لا للمقارنة: أين تقع الاستيراداتُ المعدودة أعلاه.
        "core_import_sites": sites,
    }


# ─── المقارنة ──────────────────────────────────────────────────────────────

LABELS = {
    "lines": f"سطراً (السقف {MAX_LINES})",
    "orm": f"استدعاءَ ORM (السقف {MAX_ORM})",
}


def _flatten(data: dict) -> dict[tuple[str, str], tuple[int, str]]:
    """(الموضع، المقياس) ← (العدد، وصفُه) — ثلاثةُ أقسامٍ بصيغةٍ واحدةٍ للمقارنة."""
    flat: dict[tuple[str, str], tuple[int, str]] = {}
    for key, metrics in data.get("views", {}).items():
        for metric, value in metrics.items():
            flat[(key, metric)] = (value, LABELS[metric])
    for path, value in data.get("get_school", {}).items():
        flat[(path, "get_school")] = (value, "استدعاءَ get_school() — استعمل request.school")
    for app, value in data.get("core_imports", {}).items():
        where = "، ".join(data.get("core_import_sites", {}).get(app, []))
        flat[(f"core → {app}", "import")] = (value, f"جملةَ استيرادٍ في النواة ({where})")
    return flat


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(ما زاد أو جاء جديداً فوق السقف، ما نقص ولم يُثبَّت) — كلٌّ سطرٌ يُقرأ."""
    before, now = _flatten(baseline), _flatten(current)
    worse, stale = [], []
    for key in sorted(set(before) | set(now)):
        was, label_was = before.get(key, (0, ""))
        is_, label_now = now.get(key, (0, ""))
        label = label_now or label_was
        if is_ > was:
            worse.append(f"{key[0]}: {was} → {is_} {label}")
        elif is_ < was:
            stale.append(f"{key[0]}: {was} → {is_} {label}")
    return worse, stale


def ratchet_down(baseline: dict, current: dict) -> dict:
    """السجلُّ الجديدُ إن لم يزد شيء — وإلّا `ValueError` بما زاد، فالزيادةُ لا تُسجَّل."""
    worse, _stale = compare(baseline, current)
    if worse:
        raise ValueError("\n".join(worse))
    return current


def totals(data: dict) -> dict[str, int]:
    views = data["views"]
    return {
        "views_over_lines": sum(1 for m in views.values() if "lines" in m),
        "views_over_orm": sum(1 for m in views.values() if "orm" in m),
        "views_over_any_cap": len(views),
        "get_school_in_view_files": sum(data["get_school"].values()),
        "core_files_importing_downstream": len(
            {site for files in data["core_import_sites"].values() for site in files}
        ),
        "core_downstream_import_statements": sum(data["core_imports"].values()),
    }


def _read() -> dict:
    data: dict = json.loads(BASELINE.read_text(encoding="utf-8"))
    return data


def _write(data: dict) -> None:
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: list[str]) -> int:
    current = snapshot()
    if "--rebaseline" in argv:
        _write(current)
    elif "--update" in argv:
        try:
            _write(ratchet_down(_read(), current))
        except ValueError as exc:
            print(
                "لا يُثبَّت سجلٌّ فيه زيادة — أصلحها بدل تسجيلها:\n  " + str(exc).replace("\n", "\n  ")
            )
            return 1
    else:
        worse, stale = compare(_read(), current)
        for line in worse:
            print(f"زاد: {line}")
        for line in stale:
            print(f"نقص ولم يُثبَّت: {line}")
        if worse or stale:
            return 1
    for name, total in totals(current).items():
        print(f"{name}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
