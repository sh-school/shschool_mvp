"""الرقمُ الشخصيُّ لا يُكشف بالجملة — والوثيقةُ الفرديّةُ تُسمّى ويُدقَّق توليدُها.

القاعدةُ في `core/privacy.py`: كشفٌ جماعيٌّ (قائمةٌ، جدولٌ، ردُّ بحثٍ JSON) مستورٌ
دائماً، ووثيقةٌ فرديّةٌ رسميّةٌ تُسلَّم لصاحبها تحمل الرقمَ كاملاً بشرط أثرٍ في
سجلّ التدقيق. وهذا الحارسُ يمشي ثلاثةَ مسالك:

1. **القوالبُ الحيّة**: `national_id` خامٌ (بلا `|mask_id`) داخل `{% for %}` يسقط
   أينما كان — وخارجَها لا يمرّ إلّا في وثيقةٍ مسمّاةٍ في `INDIVIDUAL_DOCUMENTS`.
2. **ردودُ JSON**: دالّةٌ تبني `JsonResponse` وفيها قاموسٌ مفتاحُه `nid` أو
   `national_id` بقيمةٍ من الرقم غيرِ مستورةٍ تسقط.
3. **المصدِّرون**: كلُّ مسارٍ يولّد PDF أو Excel يستدعي `log_export` — بنفسه أو
   عبر مساعدٍ في وحدته يستدعيه.
4. **ملفّاتُ Excel** (قرار المالك 2026-09-14): الرقمُ كاملٌ حيث يعود الملفُّ
   بالاستيراد أو الرفع الوزاريّ فيُطابَق عليه، ومستورٌ في كلّ Excel سواه. وكلُّ
   دالّةٍ تكتب الرقمَ في ورقةٍ أو تسجّل تصديرَ `xlsx` تحمل تصنيفَها مكتوباً:
   «الرقم الشخصيّ: مطابقةٌ وزاريّة — كامل» (واسمُها في `EXCEL_FULL_NUMBER`،
   ورايةُ التدقيق صادقة) أو «الرقم الشخصيّ: مستور» (وكلُّ كتابةٍ للرقم عبر
   `mask_national_id`، والرايةُ كاذبة).

والقائمتان المسمّاتان تُراجَعان كأيّ شيفرة: اسمٌ يُضاف إليهما قرارٌ يُسأل عنه.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver

BASE_DIR = Path(settings.BASE_DIR)

#: الوثائقُ الفرديّةُ الرسميّة — الرقمُ فيها كاملٌ عمداً، وتوليدُها مدقَّق.
INDIVIDUAL_DOCUMENTS = frozenset(
    {
        "reports/certificate.html",
        "reports/student_result.html",
        "reports/student_result_pdf.html",
        "student_affairs/student_profile_pdf.html",
        "behavior/pdf/student_warning.html",
        "behavior/pdf/student_undertaking.html",
        "behavior/pdf/parent_undertaking.html",
        "behavior/pdf/student_report.html",
    }
)

RENDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z_.]*national_id)((?:\|[^}]*?)?)\s*\}\}")
#: `{{ form.national_id.value }}` قيمةٌ تُعاد إلى حقل إدخال — سترُها يحفظ نجوماً.
INPUT_VALUE = re.compile(r"form\.national_id")
FOR_OPEN = re.compile(r"\{%\s*for\s")
FOR_CLOSE = re.compile(r"\{%\s*endfor\s*%\}")


def _template_roots() -> list[Path]:
    return [BASE_DIR / "templates"] + sorted(p for p in BASE_DIR.glob("*/templates") if p.is_dir())


def _raw_renders():
    """(القالب، التعبير، هل داخل حلقة) لكلّ رقمٍ يُعرض خاماً."""
    for root in _template_roots():
        for path in sorted(root.rglob("*.html")):
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
            for match in RENDER.finditer(text):
                expr, filters = match.group(1), match.group(2)
                if "mask_id" in filters or INPUT_VALUE.search(expr):
                    continue
                before = text[: match.start()]
                depth = len(FOR_OPEN.findall(before)) - len(FOR_CLOSE.findall(before))
                yield rel, expr, depth > 0


class TestTemplatesNeverBareTheNumberInBulk:
    @pytest.mark.parametrize(
        ("path", "expr", "in_loop"), list(_raw_renders()), ids=lambda v: str(v)
    )
    def test_a_raw_number_is_individual_and_named(self, path, expr, in_loop):
        assert not in_loop, (
            f"{path}: «{expr}» خامٌ داخل {{% for %}} — كشفٌ جماعيّ، أضِف |mask_id "
            "(و{% load privacy %})"
        )
        assert path in INDIVIDUAL_DOCUMENTS, (
            f"{path}: «{expr}» خامٌ في قالبٍ ليس وثيقةً فرديّةً مسمّاة — "
            "إمّا |mask_id وإمّا اسمٌ في INDIVIDUAL_DOCUMENTS مع log_export في مولّده"
        )

    def test_every_named_document_still_carries_the_full_number(self):
        """اسمٌ في القائمة بلا رقمٍ خامٍ استثناءٌ ميّت — يُحذف."""
        bare = {path for path, _expr, _loop in _raw_renders()}
        stale = sorted(INDIVIDUAL_DOCUMENTS - bare)
        assert not stale, f"وثائقُ مسمّاةٌ لم يعد فيها رقمٌ خام: {stale}"

    def test_the_sweep_found_the_named_documents(self):
        assert len(list(_raw_renders())) >= len(INDIVIDUAL_DOCUMENTS)


# ── ردودُ JSON ──────────────────────────────────────────────────────────

JSON_KEYS = {"nid", "national_id"}
SKIP_DIRS = {"migrations", "tests", "management"}


def _app_python_files():
    for app in apps.get_app_configs():
        app_path = Path(app.path)
        if BASE_DIR not in app_path.parents and app_path != BASE_DIR:
            continue
        for path in sorted(app_path.rglob("*.py")):
            if SKIP_DIRS & set(path.relative_to(app_path).parts):
                continue
            yield path


def _json_leaks():
    for path in _app_python_files():
        source = path.read_text(encoding="utf-8")
        if "JsonResponse" not in source:
            continue
        tree = ast.parse(source)
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            body = ast.get_source_segment(source, func) or ""
            if "JsonResponse(" not in body:
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values, strict=True):
                    if not (isinstance(key, ast.Constant) and key.value in JSON_KEYS):
                        continue
                    text = ast.get_source_segment(source, value) or ""
                    if "national_id" in text and "mask_national_id(" not in text:
                        rel = path.relative_to(BASE_DIR).as_posix()
                        yield f"{rel}:{value.lineno} في {func.name}(): {text}"


class TestJsonSearchNeverBaresTheNumber:
    def test_no_json_payload_carries_a_raw_number(self):
        leaks = list(_json_leaks())
        assert not leaks, "ردُّ JSON يحمل الرقمَ خاماً — استعمل mask_national_id:\n" + "\n".join(leaks)

    def test_the_sweep_actually_read_views(self):
        assert sum(1 for _ in _app_python_files()) > 50


# ── المصدِّرون ──────────────────────────────────────────────────────────

#: ما يدلّ على أنّ المسارَ يُخرج ملفّاً — أسماءٌ كاملةٌ لا أذيالُها: `swap_respond(`
#: ليست `_respond(`.
EXPORT_MARKERS = tuple(
    re.compile(r"(?<!\w)" + re.escape(name))
    for name in (
        "render_pdf(",
        "excel_to_response(",
        "to_response(",
        "_wb_to_response(",
        "spreadsheetml",
        "ExcelService.",
        "_render_behavior_pdf(",
        "_respond(",
        "_export_response(",
    )
)


def _callbacks(patterns, prefix=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _callbacks(entry.url_patterns, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.callback


def _source_of(callback) -> tuple[object, str]:
    target = getattr(callback, "view_class", None) or inspect.unwrap(callback)
    try:
        return inspect.getmodule(target), inspect.getsource(target)
    except (OSError, TypeError):
        return inspect.getmodule(target), ""


def _audited_helpers(module) -> set[str]:
    names = set()
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if obj.__module__ != module.__name__:
            continue
        try:
            if "log_export(" in inspect.getsource(obj):
                names.add(name)
        except (OSError, TypeError):
            continue
    return names


def _exporters() -> dict[str, tuple[object, str]]:
    """«الوحدة.الدالّة» ← (الوحدة، نصُّها) لكلّ مسارٍ يُخرج ملفّاً."""
    found: dict[str, tuple[object, str]] = {}
    for route, callback in _callbacks(get_resolver().url_patterns):
        module, source = _source_of(callback)
        if module is None or not source:
            continue
        if not Path(module.__file__).is_relative_to(BASE_DIR):
            continue
        if not any(marker.search(source) for marker in EXPORT_MARKERS):
            continue
        name = getattr(callback, "__name__", None) or route
        found.setdefault(f"{module.__name__}.{name}", (module, source))
    return found


EXPORTERS = _exporters()


def _is_audited(module, source) -> bool:
    if "log_export(" in source:
        return True
    return any(f"{name}(" in source for name in _audited_helpers(module))


class TestEveryExporterLeavesAnAuditTrail:
    @pytest.mark.parametrize("view", sorted(EXPORTERS))
    def test_the_exporter_calls_log_export(self, view):
        module, source = EXPORTERS[view]
        assert _is_audited(
            module, source
        ), f"{view}: يُخرج ملفّاً بلا log_export — كلُّ تصديرٍ يترك أثراً (core/audit_export.py)"

    def test_the_sweep_found_the_exporters(self):
        """حارسٌ يمسح صفراً يمرّ دائماً."""
        assert len(EXPORTERS) >= 25


# ── ملفّاتُ Excel: كاملٌ حيث يُطابَق عليه، مستورٌ سواه ─────────────────────

FULL_MARK = "الرقم الشخصيّ: مطابقةٌ وزاريّة — كامل"
MASKED_MARK = "الرقم الشخصيّ: مستور"

#: ملفّاتُ Excel التي تعود بالاستيراد فتُطابَق على الرقم — الكمالُ فيها بقرارٍ مسمّى.
EXCEL_FULL_NUMBER = frozenset(
    {
        # كشفُ الطلبة الكامل: أعمدتُه أعمدةُ قالب الاستيراد، و`students_import` يطابق على الرقم.
        "core.views_students.student_export_excel",
        # قالبُ الدرجات: يعود بالرفع و`_validate_student` يطابق صفَّه على الرقم.
        "staging.views.download_grade_template",
    }
)

#: ما يدلّ على أنّ الدالّةَ تبني ورقةَ Excel.
EXCEL_HINTS = ("openpyxl", "Workbook(", ".cell(", "ExcelService.", "excel_to_response(")
XLSX_EXPORT = re.compile(r'log_export\(\s*request,\s*"[^"]*xlsx"')
FULL_FLAG = re.compile(r"full_national_id\s*=\s*True")


def _number_references(node):
    """كلُّ قراءةٍ للرقم في الشجرة: `x.national_id` أو `row["…national_id"]`."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "national_id":
            yield sub
        elif (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.slice, ast.Constant)
            and isinstance(sub.slice.value, str)
            and "national_id" in sub.slice.value
        ):
            yield sub


def _inside_mask(node) -> set[int]:
    """معرّفاتُ العقد الواقعةِ داخل نداءِ `mask_national_id(...)`."""
    masked: set[int] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "mask_national_id":
            masked.update(id(sub) for sub in ast.walk(call))
    return masked


def _unmasked_references(node) -> list[int]:
    """أسطرُ قراءاتِ الرقم التي لا يلفّها سترٌ."""
    masked = _inside_mask(node)
    return sorted(ref.lineno for ref in _number_references(node) if id(ref) not in masked)


def _excel_functions():
    """«الوحدة.الدالّة» ← (النصّ، العقدة) لكلّ دالّةٍ تكتب الرقمَ في Excel، أو
    تسجّل تصديرَ xlsx وتدّعي فيه رقماً كاملاً (قالبٌ فارغٌ لا يقرأ الرقمَ لا يُسأل)."""
    found: dict[str, tuple[str, ast.AST]] = {}
    for path in _app_python_files():
        source = path.read_text(encoding="utf-8")
        if "national_id" not in source or not any(hint in source for hint in EXCEL_HINTS):
            continue
        module = ".".join(path.relative_to(BASE_DIR).with_suffix("").parts)
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            body = ast.get_source_segment(source, node) or ""
            builds_excel = any(hint in body for hint in EXCEL_HINTS)
            touches_number = any(True for _ in _number_references(node))
            claims_full = XLSX_EXPORT.search(body) and FULL_FLAG.search(body)
            if (builds_excel and touches_number) or claims_full:
                found.setdefault(f"{module}.{node.name}", (body, node))
    return found


EXCEL_FUNCTIONS = _excel_functions()


class TestExcelCarriesTheNumberOnlyWhereItIsMatched:
    @pytest.mark.parametrize("name", sorted(EXCEL_FUNCTIONS))
    def test_the_function_declares_its_classification(self, name):
        body, _node = EXCEL_FUNCTIONS[name]
        marks = (FULL_MARK in body) + (MASKED_MARK in body)
        assert marks == 1, (
            f"{name}: تصنيفٌ واحدٌ مكتوبٌ في الدالّة — «{FULL_MARK}» أو «{MASKED_MARK}» "
            f"(وُجد {marks})"
        )

    @pytest.mark.parametrize("name", sorted(EXCEL_FUNCTIONS))
    def test_a_full_number_is_named_and_a_masked_one_is_masked(self, name):
        body, node = EXCEL_FUNCTIONS[name]
        if FULL_MARK in body:
            assert (
                name in EXCEL_FULL_NUMBER
            ), f"{name}: مصنَّفٌ كاملاً وليس في EXCEL_FULL_NUMBER — الاستثناءُ يُسمّى لا يُضمَر"
            if XLSX_EXPORT.search(body):
                assert FULL_FLAG.search(body), f"{name}: كاملٌ ورايةُ التدقيق لا تقولها"
            return
        assert name not in EXCEL_FULL_NUMBER, f"{name}: مسمّى كاملاً ومصنَّفٌ مستوراً"
        leaks = _unmasked_references(node)
        assert not leaks, f"{name}: الرقمُ يُقرأ بلا mask_national_id في الأسطر {leaks}"
        assert not FULL_FLAG.search(body), f"{name}: مستورٌ ورايةُ التدقيق تدّعي الكمال"

    def test_every_named_full_excel_still_exists(self):
        stale = sorted(EXCEL_FULL_NUMBER - set(EXCEL_FUNCTIONS))
        assert not stale, f"أسماءٌ في EXCEL_FULL_NUMBER لا دالّةَ لها: {stale}"

    def test_the_sweep_found_the_excel_functions(self):
        assert len(EXCEL_FUNCTIONS) >= 9, sorted(EXCEL_FUNCTIONS)

    def test_the_scanner_sees_a_planted_leak(self):
        """ضبطٌ موجب: قراءةٌ خامٌ تُلتقط، ومستورةٌ تمرّ، والاسمُ في `.values()` ليس قراءة."""
        planted = ast.parse(
            "def f(ws, rows):\n"
            '    q = rows.values("student__national_id")\n'
            "    for st, rec in q:\n"
            "        ws.cell(1, 1, st.national_id)\n"
            '        ws.cell(1, 2, rec["student__national_id"])\n'
            "        ws.cell(1, 3, mask_national_id(st.national_id))\n"
            '        ws.cell(1, 4, mask_national_id(rec["student__national_id"]))\n'
        )
        assert _unmasked_references(planted) == [4, 5]
