"""سقّاطةُ الطبقات — العرضُ يستقبل ويردّ، والقراءةُ والكتابةُ في طبقتيهما.

الخدماتُ في المنصّة موجودةٌ منذ زمن (`student_affairs/services.py`،
`analytics/services.py`…) لكنّها لم تكن مُلزِمة: `student_affairs/views.py`
بلغ 2616 سطراً، وأثقلُ عروضه مئتا سطرٍ بخمسةٍ وعشرين استدعاءَ ORM. والترحيلُ
كلُّه في طلب دمجٍ واحدٍ لا يُراجَع — فالحارسُ هنا، كسقّاطة الهويّة البصريّة،
لا يطلب الصفرَ دفعةً واحدة بل يمنع الزيادة ويُثبّت كلَّ نقص:

1. **كلُّ دالّةٍ في ملفّ عروض** (`views.py`، `views_*.py`، `*_views.py`، `views/*.py`) —
   العرضُ نفسُه ومساعدُه وتوابعُ أصنافه: سقفُها 60 سطراً (من سطر `def` إلى آخره، بلا
   المزيِّنات) و5 استدعاءاتِ ORM مباشرة. والمعدودُ: الوصولُ إلى `.objects`؛ وتوابعُ لا
   يملكها غيرُ QuerySet أينما وقعت، ولو على مديرٍ مرتبط (`ORM_METHODS`: `.filter(`،
   `.exclude(`، `.order_by(`، `.values_list(`، `.all(`…)؛ و`get_object_or_404(` و`Q(`
   وأسماؤه المستعارة؛ وتوابعُ يشاركها القاموسُ والطلب (`AMBIGUOUS_METHODS`: `.get(`،
   `.update(`، `.create(`، `.save(`، `.count(`…) حين يكون مستقبِلُها من ORM — سلسلةً
   فيها ما سبق، أو اسماً أُسند منها في الدالّة. وكان العدُّ على ما أوّلُ وسائطه `request`
   وحدَه، فنقلُ الاستعلام إلى `_get_director_ctx(school, today)` في الملفّ نفسِه — ستٌّ
   وأربعون استدعاءً — كان يُخفيه عن الحارس. وكان المعدودُ خمسةَ توابعِ قراءةٍ وحدها،
   فعرضٌ يكتب في ثلاثة جداول بـ`get_object_or_404` و`.save()` و`.update(` يُعدّ أربعةً.
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

#: توابعُ لا يملكها غيرُ QuerySet والمدير — تُعدّ أينما وقعت، ولو على مديرٍ مرتبط
#: (`student.enrollments.exclude(`) لا يُعرف نوعُه من الشجرة.
ORM_METHODS = frozenset(
    {
        "all",
        "annotate",
        "aggregate",
        "bulk_create",
        "bulk_update",
        "defer",
        "distinct",
        "exclude",
        "filter",
        "get_or_create",
        "in_bulk",
        "only",
        "order_by",
        "prefetch_related",
        "select_for_update",
        "select_related",
        "update_or_create",
        "values_list",
    }
)

#: توابعُ يشترك فيها ORM والقاموسُ والقائمةُ والطلب (`request.GET.get(`، `ctx.update(`):
#: تُعدّ حين يكون مستقبِلُها من ORM — سلسلةً فيها استدعاءٌ معدود، أو اسماً أُسند منها.
AMBIGUOUS_METHODS = frozenset(
    {
        "count",
        "create",
        "delete",
        "earliest",
        "exists",
        "first",
        "get",
        "iterator",
        "last",
        "latest",
        "save",
        "update",
        "values",
    }
)

#: دوالُّ تقرأ القاعدةَ بلا مستقبِل.
ORM_FUNCTIONS = frozenset({"get_object_or_404", "get_list_or_404", "Q"})

#: ما يُرجع قاموساً أو عدداً لا سجلّاً: الاسمُ المُسنَد منه ليس من ORM.
SCALAR_RESULTS = frozenset({"aggregate", "count", "exists"})

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


def _q_aliases(tree: ast.Module) -> frozenset[str]:
    """`from django.db.models import Q as W` — فـ`W(` بناءُ `Q(` باسمٍ آخر."""
    return frozenset(
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in ORM_FUNCTIONS and alias.asname
    )


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _OrmCounter:
    """يعدّ استدعاءاتِ ORM في دالّة، ويتتبّع الأسماءَ المُسنَدة منها داخلها.

    `m = Student.objects` ثمّ `m.get(`، و`t = get_object_or_404(...)` ثمّ `t.save()`:
    المستقبِلُ اسمٌ لا يُعرف نوعُه من الشجرة، لكنّ إسنادَه في الدالّة نفسِها يُعرف.
    """

    def __init__(self, node: ast.AST, functions: frozenset[str]) -> None:
        self.node = node
        self.functions = functions
        self.tainted: set[str] = set()
        # نقطةٌ ثابتة: `qs = X.objects…` ثمّ `row = qs.first()` ثمّ `row.save()`.
        while True:
            before = len(self.tainted)
            self._collect_bindings()
            if len(self.tainted) == before:
                break

    def is_orm_call(self, call: ast.Call) -> bool:
        func = call.func
        name = _called_name(func)
        if isinstance(func, ast.Name):
            return name in self.functions
        if not isinstance(func, ast.Attribute):
            return False
        if name in ORM_METHODS or name in self.functions:
            return True
        return name in AMBIGUOUS_METHODS and self.from_orm(func.value)

    def from_orm(self, expr: ast.AST) -> bool:
        """هل جاء هذا التعبيرُ من ORM — على عموده لا في وسائطه.

        العمودُ ما يُستدعى عليه التابع: `X.objects.filter(...)[:5]` ← `X.objects` ← `X`.
        فيه `.objects`، أو استدعاءٌ معدود، أو اسمٌ مُسنَدٌ من ORM. و`{"rows": qs}` ليس منه:
        قاموسُ السياق يحمل QuerySet لكنّ `ctx.update(` ليس استعلاماً.
        """
        node: ast.AST = expr
        while True:
            if isinstance(node, ast.Name):
                return node.id in self.tainted
            if isinstance(node, ast.Attribute):
                if node.attr == "objects":
                    return True
                node = node.value
            elif isinstance(node, ast.Call):
                if self.is_orm_call(node):
                    return True
                node = node.func
                if isinstance(node, ast.Attribute):
                    node = node.value
                else:
                    return False
            elif isinstance(node, ast.Subscript):
                node = node.value
            else:
                return False

    def _collect_bindings(self) -> None:
        for sub in ast.walk(self.node):
            if isinstance(sub, ast.Assign | ast.AnnAssign) and sub.value is not None:
                targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                value = sub.value
                if isinstance(value, ast.Call) and _called_name(value.func) in SCALAR_RESULTS:
                    continue
                if self.from_orm(value):
                    self.tainted.update(t.id for t in targets if isinstance(t, ast.Name))
            elif isinstance(sub, ast.For | ast.AsyncFor) and isinstance(sub.target, ast.Name):
                if self.from_orm(sub.iter):
                    self.tainted.add(sub.target.id)

    def count(self) -> int:
        total = 0
        for sub in ast.walk(self.node):
            if isinstance(sub, ast.Attribute) and sub.attr == "objects":
                total += 1
            elif isinstance(sub, ast.Call) and self.is_orm_call(sub):
                total += 1
        return total


def _orm_calls(node: ast.AST, functions: frozenset[str] = ORM_FUNCTIONS) -> int:
    return _OrmCounter(node, functions).count()


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
    functions = ORM_FUNCTIONS | _q_aliases(tree)
    over: dict[str, dict[str, int]] = {}
    for name, node in _views(tree):
        lines = (node.end_lineno or node.lineno) - node.lineno + 1
        orm = _orm_calls(node, functions)
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
    """ملفّاتُ العروض في تطبيقات المشروع — حزمٌ في الجذر، لا مجلّداتٌ مخفيّةٌ ولا نسخٌ مؤقّتة.

    والاسمُ `views.py` أو `views_*.py` أو `*_views.py` أو ما في حزمة `views/`: كان النمطُ
    `views*.py` وحدَه، فخرجت منه `api_views.py` و`assignment_views.py` و`evaluation_views.py`
    و`observation_views.py` — تسعةُ عروضٍ فوق السقف وأحدَ عشرَ `get_school()` لا يراها أحد.
    """
    files = (
        set(root.glob("*/views.py"))
        | set(root.glob("*/views_*.py"))
        | set(root.glob("*/*_views.py"))
        | set(root.glob("*/views/*.py"))
    )
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
