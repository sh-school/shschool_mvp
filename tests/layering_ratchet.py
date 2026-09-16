"""سقّاطةُ الطبقات — العرضُ يستقبل ويردّ، والقراءةُ والكتابةُ في طبقتيهما.

الخدماتُ في المنصّة موجودةٌ منذ زمن (`student_affairs/services.py`،
`analytics/services.py`…) لكنّها لم تكن مُلزِمة: `student_affairs/views.py`
بلغ 2616 سطراً، وأثقلُ عروضه مئتا سطرٍ بخمسةٍ وعشرين استدعاءَ ORM. والترحيلُ
كلُّه في طلب دمجٍ واحدٍ لا يُراجَع — فالحارسُ هنا، كسقّاطة الهويّة البصريّة،
لا يطلب الصفرَ دفعةً واحدة بل يمنع الزيادة ويُثبّت كلَّ نقص:

1. **كلُّ دالّةٍ في ملفّ عروض** (`views.py`، `views_*.py`، `*_views.py`، `views/*.py`) —
   العرضُ نفسُه ومساعدُه وتوابعُ أصنافه: سقفُها 60 سطراً (من سطر `def` إلى آخره، بلا
   المزيِّنات) و5 استدعاءاتِ ORM. والمعدودُ: الوصولُ إلى `.objects`؛ وتوابعُ لا يملكها
   غيرُ QuerySet أينما وقعت (`ORM_METHODS`: `.filter(`، `.exclude(`، `.all(`…)؛
   و`get_object_or_404(` و`Q(` وأسماؤه المستعارة؛ وتوابعُ يشاركها القاموسُ والطلب
   (`AMBIGUOUS_METHODS`: `.get(`، `.update(`، `.create(`، `.save(`، `.count(`…) حين يكون
   مستقبِلُها من ORM — سلسلةً فيها ما سبق، أو اسماً أُسند منها في الدالّة (ولو بتفكيك
   `obj, created =`، أو في حلقةٍ أو مُولِّد، أو بـ`:=`)، أو بناءَ نموذجٍ مستورَد
   (`Cover(...)`)، أو `request.user`، أو `form.save()` من مصنّفٍ مستورَد — أو حين يكون
   مديراً مرتبطاً على نسخةٍ لا يُعرف نوعُها: `photo_set.`، أو تابعاً لا نظيرَ له في
   القاموس على صفةِ نسخة (`student.enrollments.first()`)، أو بوسائطَ لا يقبلها القاموس
   (`.get(pk=1)`، `.count()`، `.values("a")`).
   **والعرضُ يُحمَّل استعلاماتِ مساعديه**: كلَّ دالّةٍ يبلغها من ملفّات العروض — في ملفّه
   أو مستورَدةً — مرّةً واحدة. وكان العدُّ على ما أوّلُ وسائطه `request` وحدَه، فنقلُ
   الاستعلام إلى `_get_director_ctx(school, today)` في الملفّ نفسِه كان يُخفيه؛ ثمّ صار
   لكلّ دالّةٍ وحدَها، فتقسيمُه على `_part1…_part5` بخمسةٍ لكلٍّ منها كان يُخفيه كذلك.
2. **`core` لا يستورد وحدةً نازلة** — ولا استيراداً كسولاً داخل دالّة، ولا بنصٍّ
   (`__import__("x")`، `import_module`، `import_string`، `apps.get_model("app", …)`):
   الكسلُ يؤخّر الخطأ الدائريّ ولا يُزيل الاقتران. والعدُّ لكلّ وحدةٍ نازلة على النواة
   كلِّها لا لكلّ ملفّ: الاعتمادُ اعتمادُ الحزمة، ونقلُ قراءةٍ من عرضٍ في النواة
   إلى قارئٍ في النواة لا يزيده ولا ينقصه.
3. **`get_school()` في ملفّات العروض** — `request.school` يضعه
   `SchoolContextMiddleware` مرّةً لكلّ طلب. والمعدودُ كلُّ إشارةٍ إليه (مستدعاةً،
   أو مستعارةً `g = user.get_school`، أو `getattr(user, "get_school")`)، وكلُّ استدعاءٍ
   لغلافٍ يُرجعه — في الملفّ (`_get_school(request)`) أو مستورَداً من المشروع.

وقواعدُ السجلّ (`tests/layering_baseline.json`):

* ما تحت السقف لا يُكتب. عرضٌ جديدٌ فوق السقف يسقط — فالجديدُ يُكتب نظيفاً.
* المسجَّلُ **زاد** → يسقط. **نقص** → يسقط كذلك حتى يُثبَّت نقصُه، فلا يبقى
  التحسّنُ هامشاً يُملأ بمخالفةٍ أخرى في العرض نفسه.
* تغييرُ اسم عرضٍ مسجَّل يُسقطه: القديمُ نقص، والجديدُ فوق السقف بلا سجلّ.

والعدُّ بشجرة `ast` لا بالتعابير النمطيّة: التعليقُ والنصُّ لا يُعدّان، ونهايةُ
الدالّة لا تُخمَّن بالمسافة البادئة، والنتيجةُ واحدةٌ على 3.11 محلّيّاً و3.12 في CI.

تثبيتُ النقص — ويبقى ما زاد على قيمته المسجَّلة ويُسمّى، فلا يحبس نقصاً وراءه:

    python -m tests.layering_ratchet --update

وقبولُ زيادةٍ كُتبت بلا الحارس — فرعٌ أساسُه قبله، أو main دُمج فيه — بندٌ بندٌ باسمه
وسببه، ويُكتب في `accepted` فيراه المراجع:

    python -m tests.layering_ratchet --accept "assessments/views.py::class_gradebook" \\
        --reason "فرعٌ أساسُه قبل الحارس زاد ثمانيةَ أسطر؛ ترحيلُه في طلبٍ يليه"

وإعادةُ القياس حين يتغيّر **تعريفُ** العدّ نفسُه (`DEFINITION`) — تُقاس الشيفرةُ
المودَعة (`HEAD`) لا الشجرة، بعد أن تمرّ بحارسها القديم، ويُطبع كلُّ بندٍ غيّره التعريف:

    python -m tests.layering_ratchet --rebaseline [--ref HEAD]

فما زاد في العمل الجاري فوق الإيداع يبقى زيادةً تُسقط، وما أُودع زائداً قبلها يُسقط
الإيداعَ بحارسه القديم فتُرفض إعادةُ القياس — لا يذوب بندٌ في «تغيّر التعريف».
وتُشغَّل على المضيف: `git` ليس في الحاوية.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from collections.abc import Iterator

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "layering_baseline.json"

MAX_LINES = 60
MAX_ORM = 5

#: رقمُ تعريف العدّ، ويُكتب في السجلّ. يُرفع مع كلّ تغييرٍ في ما يُعدّ أو في مَن يُحمَّل
#: على العرض، ثمّ `--rebaseline` — وهو وحده ما يُجيز إعادةَ القياس.
DEFINITION = 4

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

#: جذورٌ لا يقع تحتها مديرٌ مرتبط: `os.path.exists(`، `request.session.delete(`، `cache.delete(`.
#: و`request.user` يُستثنى من `request` — نسخةُ نموذج.
NOT_ORM_ROOTS = frozenset(
    {
        "cache",
        "date",
        "datetime",
        "json",
        "math",
        "messages",
        "os",
        "pathlib",
        "re",
        "request",
        "settings",
        "shutil",
        "sys",
        "timezone",
    }
)

#: صفاتٌ هي قواميسُ في Django لا مديرون: `form.cleaned_data.get(`، `self.kwargs.get(`.
DICT_LIKE_ATTRS = frozenset(
    {
        "COOKIES",
        "FILES",
        "GET",
        "META",
        "POST",
        "attrs",
        "cleaned_data",
        "data",
        "environ",
        "errors",
        "extra",
        "fields",
        "headers",
        "initial",
        "kwargs",
        "message_dict",
        "query_params",
        "session",
    }
)

#: من `AMBIGUOUS_METHODS` ما لا يملكه قاموسٌ ولا قائمةٌ ولا نصّ: على صفةِ نسخةٍ
#: (`student.enrollments.first()`) هو مديرٌ مرتبطٌ وإن لم يُعرف نوعُ `student`.
NOT_BUILTIN_METHODS = frozenset(
    {"create", "delete", "earliest", "exists", "first", "iterator", "last", "latest", "save"}
)

#: وحداتٌ اسمُها فيه `models` وليست نماذج: `Count` و`F` و`Lower`.
NOT_MODEL_MODULES = ("django.db.models",)


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


def _imported_classes(tree: ast.Module, segment: str) -> frozenset[str]:
    """أسماءُ ما استُورد من وحدةٍ فيها المقطع (`core.models`، `.models`، `.forms`)."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if segment not in module.split(".") or module.startswith(NOT_MODEL_MODULES):
            continue
        names.update(alias.asname or alias.name for alias in node.names)
    return frozenset(names)


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _chain(expr: ast.AST) -> tuple[str | None, list[str]]:
    """(جذرُ السلسلة، صفاتُها) — `a.b.c` ← ("a", ["b", "c"])؛ والجذرُ `None` إن لم يكن اسماً."""
    attrs: list[str] = []
    node = expr
    while True:
        if isinstance(node, ast.Attribute):
            attrs.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            break
    root = node.id if isinstance(node, ast.Name) else None
    return root, attrs[::-1]


def _is_request_user(expr: ast.AST) -> bool:
    """`request.user` و`self.request.user` — نسخةُ نموذجٍ لا قاموس."""
    if not (isinstance(expr, ast.Attribute) and expr.attr == "user"):
        return False
    value = expr.value
    return (isinstance(value, ast.Name) and value.id == "request") or (
        isinstance(value, ast.Attribute) and value.attr == "request"
    )


def _target_names(target: ast.AST) -> list[str]:
    """`x` و`x, created` و`(a, (b, c))` — كلُّ اسمٍ في هدف الإسناد."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        return [name for elt in target.elts for name in _target_names(elt)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


class _OrmCounter:
    """يعدّ استدعاءاتِ ORM في دالّة، ويتتبّع الأسماءَ المُسنَدة منها داخلها.

    `m = Student.objects` ثمّ `m.get(`، و`t = get_object_or_404(...)` ثمّ `t.save()`،
    و`o = Cover(...)` ثمّ `o.save()`، و`o, created = X.objects.get_or_create()`:
    المستقبِلُ اسمٌ لا يُعرف نوعُه من الشجرة، لكنّ إسنادَه في الدالّة نفسِها يُعرف.
    """

    def __init__(
        self,
        node: ast.AST,
        functions: frozenset[str],
        models: frozenset[str] = frozenset(),
        forms: frozenset[str] = frozenset(),
    ) -> None:
        self.node = node
        self.functions = functions
        self.models = models
        self.forms = forms
        self.tainted: set[str] = set()
        self.form_names: set[str] = set()
        # نقطةٌ ثابتة: `qs = X.objects…` ثمّ `row = qs.first()` ثمّ `row.save()`.
        while True:
            before = len(self.tainted) + len(self.form_names)
            self._collect_bindings()
            if len(self.tainted) + len(self.form_names) == before:
                break

    # ── ما يُعدّ ──

    def _is_form_save(self, call: ast.Call) -> bool:
        func = call.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "save"
            and isinstance(func.value, ast.Name)
            and func.value.id in self.form_names
        )

    def _writes(self, call: ast.Call) -> bool:
        """`form.save()` تكتب، و`form.save(commit=False)` تبني نسخةً ولا تكتب."""
        return not any(
            kw.arg == "commit" and isinstance(kw.value, ast.Constant) and kw.value.value is False
            for kw in call.keywords
        )

    def _related_manager(self, call: ast.Call, name: str) -> bool:
        """مديرٌ مرتبطٌ على نسخةٍ لا يُعرف نوعُها: تشهد له الصفةُ أو شكلُ الوسائط.

        `photo_set.` اسمُ Django الافتراضيّ؛ و`.get(pk=1)` بلا وسيطٍ موضعيّ ليست
        `dict.get`؛ و`.count()` بلا وسيطٍ ليست `list.count`؛ و`.values('a')` بوسيطٍ
        ليست `dict.values`؛ وما لا نظيرَ له في القاموس (`create` `first` `exists`…)
        على صفةِ نسخة. ويُستثنى ما جذرُه طلبٌ أو وحدةٌ معروفة وما مرّ بقاموس.
        """
        func = call.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Attribute):
            return False
        root, attrs = _chain(func.value)
        if root is None or root in NOT_ORM_ROOTS or DICT_LIKE_ATTRS & set(attrs):
            return False
        if attrs[-1].endswith("_set"):
            return True
        if name in NOT_BUILTIN_METHODS:
            return True
        if name == "get":
            return not call.args and bool(call.keywords)
        if name == "count":
            return not call.args and not call.keywords
        if name == "values":
            return bool(call.args)
        return False

    def is_orm_call(self, call: ast.Call) -> bool:
        func = call.func
        name = _called_name(func)
        if isinstance(func, ast.Name):
            return name in self.functions
        if not isinstance(func, ast.Attribute):
            return False
        if name in ORM_METHODS or name in self.functions:
            return True
        if name not in AMBIGUOUS_METHODS:
            return False
        if self._is_form_save(call):
            return self._writes(call)
        return self.from_orm(func.value) or self._related_manager(call, name)

    def from_orm(self, expr: ast.AST) -> bool:
        """هل جاء هذا التعبيرُ من ORM — على عموده لا في وسائطه.

        العمودُ ما يُستدعى عليه التابع: `X.objects.filter(...)[:5]` ← `X.objects` ← `X`.
        فيه `.objects`، أو استدعاءٌ معدود، أو اسمٌ مُسنَدٌ من ORM، أو بناءُ نموذجٍ
        مستورَد (`Cover(...)`)، أو `request.user`. و`{"rows": qs}` ليس منه:
        قاموسُ السياق يحمل QuerySet لكنّ `ctx.update(` ليس استعلاماً.
        """
        node: ast.AST = expr
        while True:
            if _is_request_user(node):
                return True
            if isinstance(node, ast.Name):
                return node.id in self.tainted
            if isinstance(node, ast.Attribute):
                if node.attr == "objects":
                    return True
                if node.attr in DICT_LIKE_ATTRS:
                    return False
                node = node.value
            elif isinstance(node, ast.NamedExpr):
                node = node.value
            elif isinstance(node, ast.Call):
                if self.is_orm_call(node):
                    return True
                if isinstance(node.func, ast.Name) and node.func.id in self.models:
                    return True
                if self._is_form_save(node):
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

    # ── الإسنادُ داخل الدالّة ──

    def _bind(self, targets: list[ast.AST], value: ast.AST) -> None:
        if isinstance(value, ast.Call) and _called_name(value.func) in SCALAR_RESULTS:
            return
        names = [name for target in targets for name in _target_names(target)]
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in self.forms
        ):
            self.form_names.update(names)
        elif self.from_orm(value):
            self.tainted.update(names)

    def _collect_bindings(self) -> None:
        for sub in ast.walk(self.node):
            if isinstance(sub, ast.Assign):
                self._bind(sub.targets, sub.value)
            elif isinstance(sub, ast.AnnAssign) and sub.value is not None:
                self._bind([sub.target], sub.value)
            elif isinstance(sub, ast.NamedExpr):
                self._bind([sub.target], sub.value)
            elif isinstance(sub, ast.For | ast.AsyncFor | ast.comprehension):
                if self.from_orm(sub.iter):
                    self.tainted.update(_target_names(sub.target))
            elif isinstance(sub, ast.With | ast.AsyncWith):
                for item in sub.items:
                    if item.optional_vars is not None:
                        self._bind([item.optional_vars], item.context_expr)

    def count(self) -> int:
        total = 0
        for sub in ast.walk(self.node):
            if isinstance(sub, ast.Attribute) and sub.attr == "objects":
                total += 1
            elif isinstance(sub, ast.Call) and self.is_orm_call(sub):
                total += 1
        return total


# ─── الوحدةُ ومساعدوها ─────────────────────────────────────────────────────


def _is_get_school_ref(node: ast.AST) -> bool:
    """`x.get_school` (مستدعاةً أو مستعارة)، و`get_school(`، و`getattr(x, "get_school")`."""
    if isinstance(node, ast.Attribute) and node.attr == "get_school":
        return True
    if isinstance(node, ast.Name) and node.id == "get_school" and isinstance(node.ctx, ast.Load):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "get_school"
    )


class _Module:
    """ملفٌّ مقروء: دوالُّه وتوابعُ أصنافه، وأسماءُ ما استورده من وحدات المشروع."""

    def __init__(self, source: str, path: str, index: _Index | None = None) -> None:
        self.path = path
        self.index = index
        self.tree = ast.parse(source)
        self.functions = ORM_FUNCTIONS | _q_aliases(self.tree)
        self.models = _imported_classes(self.tree, "models")
        self.forms = _imported_classes(self.tree, "forms")
        # الاسمُ المؤهَّل ← العقدة: `view` و`Page.get`.
        self.defs: dict[str, FunctionNode] = {}
        self.owner: dict[str, str | None] = {}
        for node in self.tree.body:
            if isinstance(node, FUNCTION_NODES):
                self.defs[node.name] = node
                self.owner[node.name] = None
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, FUNCTION_NODES):
                        qual = f"{node.name}.{item.name}"
                        self.defs[qual] = item
                        self.owner[qual] = node.name
        # الاسمُ المحلّيّ ← (الوحدة المنقوطة، الاسمُ فيها أو None للوحدة نفسِها).
        self.imports: dict[str, tuple[str, str | None]] = {}
        for node in self.tree.body:
            if isinstance(node, ast.ImportFrom):
                module = self._absolute(node)
                if module is None:
                    continue
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self.imports[alias.asname] = (alias.name, None)
        self._own_orm: dict[str, int] = {}
        self._wrappers: frozenset[str] | None = None

    def _absolute(self, node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        package = pathlib.PurePosixPath(self.path).parts[:-1]
        if node.level > 1:
            package = package[: len(package) - (node.level - 1)]
        return ".".join([*package, *([node.module] if node.module else [])])

    # ── من يُستدعى ──

    def callees(self, qual: str) -> Iterator[tuple[_Module, str]]:
        """دوالُّ المشروع التي تستدعيها هذه الدالّة: في الملفّ نفسِه أو مستورَدةً منه."""
        cls = self.owner[qual]
        for sub in ast.walk(self.defs[qual]):
            if not isinstance(sub, ast.Call):
                continue
            target = self._resolve(sub.func, cls)
            if target is not None:
                yield target

    def _resolve(self, func: ast.expr, cls: str | None) -> tuple[_Module, str] | None:
        if isinstance(func, ast.Name):
            if func.id in self.defs and self.owner[func.id] is None:
                return self, func.id
            if func.id in self.imports and self.index is not None:
                module, name = self.imports[func.id]
                if name is not None:
                    return self.index.function(module, name)
            return None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            if base in {"self", "cls"} and cls is not None:
                qual = f"{cls}.{func.attr}"
                return (self, qual) if qual in self.defs else None
            if base in self.imports and self.index is not None:
                module, name = self.imports[base]
                dotted = module if name is None else f"{module}.{name}"
                return self.index.function(dotted, func.attr)
        return None

    # ── ORM ──

    def own_orm(self, qual: str) -> int:
        if qual not in self._own_orm:
            self._own_orm[qual] = _OrmCounter(
                self.defs[qual], self.functions, self.models, self.forms
            ).count()
        return self._own_orm[qual]

    def orm_with_helpers(self, qual: str) -> int:
        """ما في الدالّة وما في كلِّ مساعدٍ تبلغه من ملفّات العروض — كلٌّ مرّةً واحدة.

        السقفُ لكلّ دالّةٍ وحدَها كان يُقسم: عرضٌ بخمسةٍ وعشرين استدعاءً يصير خمسَ
        دوالٍّ `_part1…_part5` بخمسةٍ لكلٍّ منها، والاستعلاماتُ كلُّها في ملفّ العروض.
        و`selectors.py` و`services.py` ليسا ملفَّي عروض — فالنقلُ إليهما وحدَه يُنقص.
        """
        seen: set[tuple[str, str]] = set()
        total = 0
        stack: list[tuple[_Module, str]] = [(self, qual)]
        while stack:
            module, name = stack.pop()
            if (module.path, name) in seen:
                continue
            seen.add((module.path, name))
            total += module.own_orm(name)
            stack.extend(
                (callee, callee_name)
                for callee, callee_name in module.callees(name)
                if _is_view_path(callee.path)
            )
        return total

    # ── get_school ──

    def wrappers(self) -> frozenset[str]:
        """دوالُّ تُرجع `get_school()` — بنفسها، أو باسمٍ أُسند منه، أو بغلافٍ آخر."""
        if self._wrappers is not None:
            return self._wrappers
        self._wrappers = frozenset()
        found: set[str] = set()
        while True:
            before = len(found)
            for qual, node in self.defs.items():
                if qual not in found and self._returns_school(qual, node, found):
                    found.add(qual)
            self._wrappers = frozenset(found)
            if len(found) == before:
                return self._wrappers

    def _yields_school(self, expr: ast.AST | None, cls: str | None, names: set[str]) -> bool:
        if expr is None:
            return False
        if isinstance(expr, ast.IfExp):
            return self._yields_school(expr.body, cls, names) or self._yields_school(
                expr.orelse, cls, names
            )
        if isinstance(expr, ast.BoolOp):
            return any(self._yields_school(v, cls, names) for v in expr.values)
        if isinstance(expr, ast.Name):
            return expr.id in names
        if isinstance(expr, ast.Call):
            if _is_get_school_ref(expr) or _is_get_school_ref(expr.func):
                return True
            if isinstance(expr.func, ast.Name) and expr.func.id in names:
                return True
            if isinstance(expr.func, ast.Call) and _is_get_school_ref(expr.func):
                return True
            return self.is_wrapper_call(expr, cls)
        return _is_get_school_ref(expr)

    def _returns_school(self, qual: str, node: FunctionNode, found: set[str]) -> bool:
        cls = self.owner[qual]
        names: set[str] = set()
        for _ in range(3):  # `s = user.get_school()` ثمّ `school = s` ثمّ `return school`
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and self._yields_school(sub.value, cls, names):
                    names.update(n for t in sub.targets for n in _target_names(t))
        return any(
            isinstance(sub, ast.Return) and self._yields_school(sub.value, cls, names)
            for sub in ast.walk(node)
        )

    def is_wrapper_call(self, call: ast.Call, cls: str | None) -> bool:
        target = self._resolve(call.func, cls)
        if target is None:
            return False
        module, name = target
        if module is self:
            # أثناء البحث عن الأغلفة: ما وُجد حتّى الآن.
            return name in (self._wrappers or frozenset())
        return name in module.wrappers()

    def get_school_calls(self) -> int:
        """كلُّ إشارةٍ إلى `get_school` في الملفّ، وكلُّ استدعاءٍ لغلافٍ عليه."""
        self.wrappers()  # تُحسب كاملةً قبل العدّ: `is_wrapper_call` يقرأ ما وُجد منها
        total = 0
        owners = {
            id(sub): self.owner[qual] for qual, node in self.defs.items() for sub in ast.walk(node)
        }
        for sub in ast.walk(self.tree):
            if _is_get_school_ref(sub):
                total += 1
            elif (
                isinstance(sub, ast.Call)
                and not _is_get_school_ref(sub.func)
                and self.is_wrapper_call(sub, owners.get(id(sub)))
            ):
                total += 1
        return total


def _is_view_path(path: str) -> bool:
    parts = pathlib.PurePosixPath(path).parts
    name = parts[-1]
    return (
        name == "views.py"
        or (name.startswith("views_") and name.endswith(".py"))
        or name.endswith("_views.py")
        or (len(parts) >= 2 and parts[-2] == "views" and name.endswith(".py"))
    )


class _Index:
    """وحداتُ المشروع مقروءةً مرّةً واحدة — ليُتبَع المساعدُ المستورَدُ إلى ملفّه."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.modules: dict[str, _Module | None] = {}

    def module(self, dotted: str) -> _Module | None:
        if dotted not in self.modules:
            self.modules[dotted] = None
            base = self.root.joinpath(*dotted.split("."))
            for candidate in (base.with_suffix(".py"), base / "__init__.py"):
                if (
                    candidate.is_file()
                    and (self.root / dotted.split(".")[0] / "__init__.py").is_file()
                ):
                    rel = candidate.relative_to(self.root).as_posix()
                    self.modules[dotted] = _Module(candidate.read_text(encoding="utf-8"), rel, self)
                    break
        return self.modules[dotted]

    def function(self, dotted: str, name: str) -> tuple[_Module, str] | None:
        module = self.module(dotted)
        if module is not None and name in module.defs and module.owner[name] is None:
            return module, name
        return None


def _views(tree: ast.Module) -> Iterator[tuple[str, FunctionNode]]:
    """(الاسم، العقدة) لكلّ دالّةٍ في رأس ملفّ العروض ولكلّ تابعٍ في أصنافه."""
    for node in tree.body:
        if isinstance(node, FUNCTION_NODES):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, FUNCTION_NODES):
                    yield f"{node.name}.{item.name}", item


def measure_views(
    source: str, path: str, index: _Index | None = None
) -> tuple[dict[str, dict[str, int]], int]:
    """(ما فوق السقف من عروض الملفّ، عددُ `get_school()` فيه كلِّه)."""
    module = _Module(source, path, index)
    if index is not None:
        index.modules.setdefault(_dotted(path), module)
    over: dict[str, dict[str, int]] = {}
    for name, node in _views(module.tree):
        lines = (node.end_lineno or node.lineno) - node.lineno + 1
        orm = module.orm_with_helpers(name)
        excess = {}
        if lines > MAX_LINES:
            excess["lines"] = lines
        if orm > MAX_ORM:
            excess["orm"] = orm
        if excess:
            over[f"{path}::{name}"] = excess
    return over, module.get_school_calls()


def _dotted(path: str) -> str:
    parts = list(pathlib.PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


#: استيرادٌ بنصٍّ لا بجملة: `__import__("x")`، `import_module("x")`، `import_string("x.y")`.
DYNAMIC_IMPORTS = frozenset({"__import__", "import_module", "import_string"})


def _dynamic_import(node: ast.Call) -> str | None:
    """الوحدةُ التي يستوردها استدعاءٌ بنصٍّ ثابت — أو `None`.

    `apps.get_model("clinic", "Visit")` و`apps.get_model("clinic.Visit")` اقترانٌ
    بالتطبيق كالاستيراد: النموذجُ يُطلب باسمه، والتطبيقُ لازمٌ للنواة.
    """
    name = _called_name(node.func)
    first = node.args[0] if node.args else None
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    if name in DYNAMIC_IMPORTS:
        return first.value
    if name == "get_model":
        return first.value.split(".", 1)[0]
    return None


def measure_core_imports(source: str, downstream: frozenset[str]) -> dict[str, int]:
    """وحدةٌ نازلة ← عددُ جُمل الاستيراد منها — في أيّ عمقٍ من الملفّ، ولو بنصّ."""
    found: Counter[str] = Counter()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        elif isinstance(node, ast.Call) and (module := _dynamic_import(node)):
            names = [module]
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
    index = _Index(root)
    for path in view_files(root):
        rel = path.relative_to(root).as_posix()
        over, calls = measure_views(path.read_text(encoding="utf-8"), rel, index)
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


def ratchet_down(baseline: dict, current: dict) -> tuple[dict, list[str]]:
    """(السجلُّ بكلّ نقصٍ مُثبَّتاً، وما زاد ولم يُسجَّل).

    كان يرفض السجلَّ كلَّه إن زاد بندٌ واحد: فرعٌ دُمج فيه عملُ فرعٍ آخرَ — نقصٌ هنا
    وزيادةٌ هناك — لا يستطيع تثبيتَ النقص حتى يُصلح الزيادة، فلا مخرجَ غيرُ
    `--rebaseline` الذي يُخفي الزيادةَ مع النقص. فالنقصُ يُثبَّت، والزيادةُ تبقى
    على قيمتها المسجَّلة فتُسقط الحارسَ حتى تُصلَح أو تُقبَل باسمها (`accept`).
    """
    worse, _stale = compare(baseline, current)
    views: dict[str, dict[str, int]] = {}
    for key in set(baseline["views"]) | set(current["views"]):
        was, is_ = baseline["views"].get(key, {}), current["views"].get(key, {})
        metrics = {m: min(was.get(m, 0), is_.get(m, 0)) for m in set(was) | set(is_)}
        if kept := {m: v for m, v in sorted(metrics.items()) if v > 0}:
            views[key] = kept

    def lower(section: str) -> dict[str, int]:
        was, is_ = baseline[section], current[section]
        pairs = ((k, min(was.get(k, 0), is_.get(k, 0))) for k in set(was) | set(is_))
        return {k: v for k, v in sorted(pairs) if v > 0}

    core_imports = lower("core_imports")
    recorded = {
        "views": dict(sorted(views.items())),
        "get_school": lower("get_school"),
        "core_imports": core_imports,
        "core_import_sites": {
            app: current["core_import_sites"].get(app) or baseline["core_import_sites"][app]
            for app in core_imports
        },
    }
    if baseline.get("accepted"):
        recorded["accepted"] = baseline["accepted"]
    if "definition" in baseline:
        recorded["definition"] = baseline["definition"]
    return recorded, worse


#: أقصرُ سببٍ يُقبل به تجاوز: جملةٌ تُقرأ لا «ok».
MIN_REASON = 20


def accept(baseline: dict, current: dict, where: str, reason: str) -> dict:
    """يرفع بنداً زاد إلى قيمته الجارية، ويكتب في `accepted` الموضعَ والقيمتين والسبب.

    للشيفرة التي كُتبت بلا الحارس: فرعٌ أساسُه قبله، أو main دُمج فيه. كلُّ بندٍ
    باسمه وسببه، والفرقُ في السجلّ يُراجَع في طلب الدمج — لا `--rebaseline` يُعيد
    القياسَ كلَّه فيذوب البندُ بين مئة. ويرفض ما لم يزد، والسببَ القصير، ولا يلمس
    بنداً غيرَه.
    """
    if len(reason.strip()) < MIN_REASON:
        raise ValueError(f"اذكر سببَ القبول في {MIN_REASON} حرفاً على الأقلّ — لماذا لا يُصلَح الآن.")
    before, now = _flatten(baseline), _flatten(current)
    grew = sorted(
        (metric, before.get((where, metric), (0, ""))[0], value)
        for (key, metric), (value, _label) in now.items()
        if key == where and value > before.get((key, metric), (0, ""))[0]
    )
    if not grew:
        raise ValueError(f"«{where}» لم يزد — لا شيءَ يُقبل. انسخ الموضعَ كما يطبعه الفحص قبل «:».")
    recorded = json.loads(json.dumps(baseline))
    for metric, _was, value in grew:
        if metric in LABELS:
            recorded["views"].setdefault(where, {})[metric] = value
        elif metric == "get_school":
            recorded["get_school"][where] = value
        else:
            app = where.removeprefix("core → ")
            recorded["core_imports"][app] = value
            recorded["core_import_sites"][app] = current["core_import_sites"][app]
    recorded["accepted"] = [
        *baseline.get("accepted", []),
        *(
            {"where": where, "metric": metric, "from": was, "to": value, "reason": reason.strip()}
            for metric, was, value in grew
        ),
    ]
    return recorded


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


def rebaseline_tree(tree: pathlib.Path) -> tuple[dict, list[str]]:
    """(السجلُّ مقيساً بهذا التعريف على نسخةٍ مودَعة، وكلُّ بندٍ غيّره التعريف).

    كان `--rebaseline` يقيس الشجرةَ الجارية ويكتبها بلا قيد: عرضٌ زاد في التغيير نفسِه
    يدخل السجلَّ بقيمته الجديدة بين مئة سطرٍ غيّرها التعريف، ولا يُذكر في `accepted`.
    فالآن: (1) لا يُعاد القياس إلّا إن اختلف رقمُ التعريف عن المسجَّل؛ (2) النسخةُ
    المودَعة تمرّ بحارسها هي وسجلِّها هي أوّلاً — فما أُودع زائداً يُرفض هنا؛ (3) يُقاس
    الإيداعُ لا الشجرة — فما زاد في العمل الجاري يبقى زيادةً بعد إعادة القياس.
    """
    old: dict = json.loads((tree / "tests" / "layering_baseline.json").read_text(encoding="utf-8"))
    if old.get("definition") == DEFINITION:
        raise ValueError(
            f"التعريف {DEFINITION} هو المسجَّل — لا إعادةَ قياس. ثبّت النقصَ بـ--update، "
            "أو اقبل الزيادةَ باسمها بـ--accept؛ وإن غيّرتَ ما يُعدّ فارفع DEFINITION."
        )
    proc = subprocess.run(
        [sys.executable, "-m", "tests.layering_ratchet"],
        cwd=tree,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(
            "الإيداعُ لا يمرّ بحارسه هو — أصلحه أو اقبل زيادتَه باسمها قبل إعادة القياس:\n"
            + proc.stdout
            + proc.stderr
        )
    recorded = {**snapshot(tree), "definition": DEFINITION}
    if old.get("accepted"):
        recorded["accepted"] = old["accepted"]
    raised, lowered = compare(old, recorded)
    report = [f"رفعه التعريف: {line}" for line in raised]
    report += [f"أنقصه التعريف: {line}" for line in lowered]
    return recorded, report


def export_ref(ref: str, dest: pathlib.Path, root: pathlib.Path = ROOT) -> None:
    """نسخةُ `ref` كما أُودعت، في `dest` — بلا ما في الشجرة من عملٍ جارٍ."""
    archive = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", ref], capture_output=True, check=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")


def _read() -> dict:
    data: dict = json.loads(BASELINE.read_text(encoding="utf-8"))
    return data


def _write(data: dict) -> None:
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.layering_ratchet")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true")
    mode.add_argument("--rebaseline", action="store_true")
    mode.add_argument("--accept", metavar="WHERE")
    parser.add_argument("--reason", default="")
    parser.add_argument("--ref", default="HEAD", help="الإيداعُ الذي يُعاد قياسُه")
    args = parser.parse_args(argv)

    current = snapshot()
    if args.rebaseline:
        with tempfile.TemporaryDirectory() as tmp:
            export_ref(args.ref, pathlib.Path(tmp))
            try:
                recorded, report = rebaseline_tree(pathlib.Path(tmp))
            except ValueError as exc:
                print(exc)
                return 1
        _write(recorded)
        print("\n".join(report) or "لم يغيّر التعريفُ بنداً.")
        worse, stale = compare(recorded, current)
        for line in worse:
            print(f"زاد فوق الإيداع: {line}")
        for line in stale:
            print(f"نقص فوق الإيداع ولم يُثبَّت: {line}")
        if worse or stale:
            return 1
    elif args.accept:
        try:
            _write(accept(_read(), current, args.accept, args.reason))
        except ValueError as exc:
            print(exc)
            return 1
    elif args.update:
        recorded, worse = ratchet_down(_read(), current)
        _write(recorded)
        if worse:
            print(
                "ثُبِّت النقص، ولا يُثبَّت ما زاد — أصلحه، أو اقبله باسمه إن كُتب بلا الحارس:\n"
                '  python -m tests.layering_ratchet --accept "<الموضع>" --reason "<لماذا>"\n  '
                + "\n  ".join(worse)
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
