"""مسحُ الشيفرة لحرّاس التصدير المركزيّ (VI-30ب) — AST لا نصّ، فلا يخدعه تعليقٌ ولا سلسلة.

* `log_export_kinds()`: أنواعُ `log_export(request, "kind", …)` الحرفيّة (الموضعُ الثاني أو `kind=`)، والبادئاتُ للأنواع
  الديناميكيّة (f-string) — ما يُسجِّل خروجَ ملفٍّ من المنصّة.
* `heavy_calls_in_views()`: (ملفّ، دالّة) تنادي `render_pdf`/`render_pdf_bytes`/`Workbook` مباشرةً في ملفّاتِ عرضٍ — أي
  مُصدِّراً ثقيلاً في مسار الطلب. (نداءٌ عبر دالّةٍ مساعدةٍ لا يُلتقط — حدُّ المسح، والحارسُ سقّاطةٌ لا برهان.)
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SKIP_PARTS = {"tests", "migrations", "node_modules", ".venv", "venv", "staticfiles", ".claude"}
HEAVY = {"render_pdf", "render_pdf_bytes", "Workbook"}


def _py_files():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if _SKIP_PARTS & set(rel.parts):
            continue
        yield path, rel.as_posix()


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def log_export_kinds() -> tuple[dict[str, str], dict[str, str]]:
    """({kind حرفيّ: ملفٌّ}، {بادئةُ kind ديناميكيّ: ملفٌّ})."""
    literal: dict[str, str] = {}
    prefixes: dict[str, str] = {}
    for path, rel in _py_files():
        if rel == "core/audit_export.py":
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _call_name(node) == "log_export"):
                continue
            arg = node.args[1] if len(node.args) > 1 else None
            for keyword in node.keywords:
                if keyword.arg == "kind":
                    arg = keyword.value
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                literal[arg.value] = rel
            elif isinstance(arg, ast.JoinedStr) and arg.values:
                first = arg.values[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    prefixes[first.value] = rel
    return literal, prefixes


def heavy_calls_in_views() -> set[str]:
    """{"ملفّ::دالّة"} لكلّ دالّةٍ في ملفّ عرضٍ تنادي مُصدِّراً ثقيلاً مباشرةً."""
    found: set[str] = set()
    for path, rel in _py_files():
        if "views" not in Path(rel).name and "/views/" not in rel:
            continue
        tree = _parse(path)
        if tree is None:
            continue
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and _call_name(node) in HEAVY:
                    found.add(f"{rel}::{func.name}")
                    break
    return found
