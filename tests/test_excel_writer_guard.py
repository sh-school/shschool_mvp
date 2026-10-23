"""حارسُ الكاتب المركزيّ لـExcel (W-20261021-004، CWE-1236).

كلُّ نصٍّ يدخل خليّةَ openpyxl يمرّ بـ``core.excel_safety`` (``safe_cell`` /
``safe_set`` / ``safe_append``). يفحص هذا الحارسُ الشيفرةَ غيرَ الاختباريّة بـAST
ويرفض خارجَ ``core/excel_safety.py``:

* ``ws.cell(..., value=...)`` أو ``ws.cell(r, c, v)`` (القراءةُ والتنسيقُ بلا قيمة مسموحان)،
* ``ws.append(...)``،
* ``ws[...] = ...``،
* ``cell.value = ...`` لخليّةٍ مأخوذةٍ من ورقة.

الورقةُ تُعرف بالأسماء الشائعة (ws/ws1/ws2/sheet/worksheet) أو بمتغيّرٍ أُسند من
``wb.active`` أو ``create_sheet`` أو ``wb[...]`` — فلا يخطئ بقوائم Python العاديّة.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAFE_MODULE = "core/excel_safety.py"
SHEET_NAMES = {"ws", "ws1", "ws2", "sheet", "worksheet"}
SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".claude",
    "tests",
    "migrations",
    "staticfiles",
    "docs",
    "build",
    "dist",
}

# مولّدٌ خارج نطاق W-20261021-004 لم يُرحَّل بعد: «بانتظار ترحيل». كلُّ مدخلٍ يُسمّى بسببه،
# ويُحذف حين يُرحَّل (والاختبارُ الأخير يفشل إن بقي مدخلٌ لم يعد مخالفاً).
PENDING_MIGRATION: dict[str, str] = {
    "staff_affairs/attendance/daily.py": (
        "ws.append لكشف الحضور اليوميّ (أسماء موظفين) — خارج الملفّات المسموحة في البطاقة"
    ),
}
# استثناءاتٌ مبرَّرة دائمة (فارغة عمداً؛ أضف اسماً مع السبب إن وُجد استثناءٌ حقيقيّ).
JUSTIFIED: dict[str, str] = {}


def _is_sheet_expr(node: ast.AST, sheets: set[str]) -> bool:
    return isinstance(node, ast.Name) and node.id in sheets


def _collect_sheets(tree: ast.AST) -> set[str]:
    sheets = set(SHEET_NAMES)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        v = node.value
        sheet_source = (
            isinstance(v, ast.Attribute)
            and v.attr == "active"
            or isinstance(v, ast.Call)
            and isinstance(v.func, ast.Attribute)
            and v.func.attr == "create_sheet"
            or isinstance(v, ast.Subscript)
            and isinstance(v.value, ast.Name)
            and v.value.id in {"wb", "workbook"}
        )
        if sheet_source:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    sheets.add(t.id)
    return sheets


def _is_cell_call(node: ast.AST, sheets: set[str]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "cell"
        and _is_sheet_expr(node.func.value, sheets)
    ) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "safe_cell"
    )


def violations_in(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    sheets = _collect_sheets(tree)
    # متغيّراتٌ تحمل خليّةً (من ws.cell(...) أو safe_cell(...) أو ws[...]).
    cell_vars: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and (
            _is_cell_call(node.value, sheets)
            or (isinstance(node.value, ast.Subscript) and _is_sheet_expr(node.value.value, sheets))
        ):
            cell_vars.update(t.id for t in node.targets if isinstance(t, ast.Name))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _is_sheet_expr(node.func.value, sheets)
        ):
            if node.func.attr == "cell" and (
                any(k.arg == "value" for k in node.keywords) or len(node.args) >= 3
            ):
                found.append((node.lineno, "ws.cell(..., value) — استعمل safe_cell"))
            elif node.func.attr == "append":
                found.append((node.lineno, "ws.append — استعمل safe_append"))
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Subscript) and _is_sheet_expr(t.value, sheets):
                found.append((node.lineno, "ws[...] = — استعمل safe_cell"))
            elif isinstance(t, ast.Attribute) and t.attr == "value":
                base = t.value
                if (isinstance(base, ast.Name) and base.id in cell_vars) or _is_cell_call(
                    base, sheets
                ):
                    found.append((node.lineno, "cell.value = — استعمل safe_set"))
    return found


def _python_files():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if SKIP_DIRS & set(rel.parts[:-1]):
            continue
        yield rel.as_posix(), path


def _scan() -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for rel, path in _python_files():
        if rel == SAFE_MODULE:
            continue
        text = path.read_text(encoding="utf-8")
        if "openpyxl" not in text and "Workbook" not in text and "safe_cell" not in text:
            continue
        hits = violations_in(text)
        if hits:
            out[rel] = hits
    return out


def test_no_direct_cell_writes_outside_the_central_writer():
    offenders = {
        rel: hits
        for rel, hits in _scan().items()
        if rel not in PENDING_MIGRATION and rel not in JUSTIFIED
    }
    assert not offenders, (
        "كتابةٌ مباشرةٌ في خلايا openpyxl خارج core.excel_safety (CWE-1236) — "
        f"استعمل safe_cell/safe_set/safe_append: {offenders}"
    )


def test_pending_and_justified_entries_are_still_real_violations():
    scanned = _scan()
    stale = [rel for rel in (*PENDING_MIGRATION, *JUSTIFIED) if rel not in scanned]
    assert not stale, f"مدخلاتٌ لم تعد مخالفةً — احذفها من القائمة: {stale}"


class TestDetector:
    @pytest.mark.parametrize(
        "code",
        [
            "ws = wb.active\nws.cell(row=1, column=1, value=x)",
            "ws.cell(1, 1, x)",
            "ws.append([1, 2])",
            "ws['A1'] = x",
            "s = wb.create_sheet('a')\ns.append([x])",
            "c = ws.cell(row=1, column=1)\nc.value = x",
            "ws.cell(row=1, column=1).value = x",
        ],
    )
    def test_flags_direct_writes(self, code):
        assert violations_in(code)

    @pytest.mark.parametrize(
        "code",
        [
            "rows = []\nrows.append([1])",
            "data = []\ndata.append(x)",
            "ws.cell(row=1, column=1).font = f",
            "safe_cell(ws, 1, 1, x)",
            "obj.value = 3",
            "ws.cell(row=1, column=1)",
        ],
    )
    def test_ignores_python_lists_formatting_and_safe_calls(self, code):
        assert not violations_in(code)
