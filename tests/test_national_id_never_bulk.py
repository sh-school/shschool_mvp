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

والقائمةُ المسمّاة تُراجَع كأيّ شيفرة: اسمٌ يُضاف إليها قرارٌ يُسأل عنه.
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
