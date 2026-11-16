"""عقدُ التصدير المركزيّ للجداول (W-20261109-013): الملفُّ يخرج بما تعرضه الشاشةُ بعد الفلترة وحسب صلاحيّات الدور.

* **محدِّدٌ واحدٌ لكلّ جدول** `rows_for(user, params) -> list[dict]` تستعمله الصفحةُ والتصديرُ معاً، فلا يختلف المعروضُ عن
  المُصدَّر: يطبّق نطاقَ الدور (الجناح) والفلترَ كاملاً — لا صفحةَ الترقيم الحاليّة وحدَها.
* **الترقيمُ** (عمود «م») يُحسب عند الإخراج ولا يُخزَّن، والفرزُ بالجناح من `WING_KEY_OF_ORDER` للمدير والمشرف معاً
  (مستقرٌّ: يبقى ترتيبُ الرابط داخل الجناح الواحد).
* **الأعمدةُ المخفيّةُ** في الشاشة تُخفى في الملف (`?hide=key1,key2`) — ولا يُخفى العمودُ كلُّه.

الصفحاتُ القديمةُ تُرحَّل إلى هذا العقد في بطاقاتٍ لاحقة؛ وحارسُ `tests/test_export_contract_guard.py` يُلزم كلَّ زرّ تصديرٍ
بنوعٍ مسجَّلٍ هنا أو باستثناءٍ بسببٍ مكتوب.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from core.dept_colors import WING_KEY_OF_ORDER

from . import registry

#: عنوانُ عمود الترقيم التلقائيّ.
NUMBER_LABEL = "م"
#: مَن لا جناحَ له (أو جناحُه خارج 1..5) يأتي بعد الأجنحة.
_NO_WING_RANK = len(WING_KEY_OF_ORDER) + 1


@dataclass(frozen=True)
class Column:
    key: str
    label: str


@dataclass(frozen=True)
class TableSpec:
    """جدولٌ قابلٌ للتصدير: نوعُه ومحدِّدُ صفوفه وأعمدتُه."""

    kind: str
    title: str
    capability: str
    columns: tuple[Column, ...]
    #: `(user, params: QueryDict) -> [صفٌّ: {مفتاحُ العمود: قيمة}]` — المحدِّدُ نفسُه الذي تقرأ به الشاشة.
    rows_for: Callable[[Any, Any], list[dict[str, Any]]]
    #: مفتاحُ ترتيب الجناح في الصفّ؛ `None` = بلا فرزٍ بالجناح.
    wing_key: str | None = "wing_order"
    #: وحدةُ اسم الملفّ (`SchoolOS_<module>_list_…`).
    file_module: str = "export"


_TABLES: dict[str, TableSpec] = {}


def wing_rank(order: object) -> int:
    """رتبةُ الجناح في الفرز: ترتيبُه (1..5)، وغيرُه في الذيل."""
    try:
        n = int(str(order))
    except (TypeError, ValueError):
        return _NO_WING_RANK
    return n if n in WING_KEY_OF_ORDER else _NO_WING_RANK


def wing_sorted(rows: list[dict[str, Any]], key: str = "wing_order") -> list[dict[str, Any]]:
    """يفرز الصفوفَ بالجناح فرزاً مستقرّاً: ترتيبُ الرابط محفوظٌ داخل كلّ جناح."""
    return sorted(rows, key=lambda row: wing_rank(row.get(key)))


def visible_columns(spec: TableSpec, params: Any) -> list[Column]:
    """أعمدةُ الملفّ: ما في الجدول عدا ما أخفته الشاشةُ (`hide=`)، وإن أُخفيت كلُّها بقيت كلُّها."""
    hidden = {k.strip() for k in str(params.get("hide", "")).split(",") if k.strip()}
    shown = [c for c in spec.columns if c.key not in hidden]
    return shown or list(spec.columns)


def table_rows(spec: TableSpec, user: Any, params: Any) -> tuple[list[Column], list[list[Any]]]:
    """(الأعمدة، الصفوفُ مرقَّمةً) كما تخرج في الملفّ — الترقيمُ يُحسب هنا لا يُخزَّن."""
    columns = visible_columns(spec, params)
    rows = spec.rows_for(user, params)
    if spec.wing_key:
        rows = wing_sorted(rows, spec.wing_key)
    return columns, [[i, *(row.get(c.key, "") for c in columns)] for i, row in enumerate(rows, 1)]


def build_table_xlsx(spec: TableSpec, school: Any, user: Any, params: Any) -> registry.ExportResult:
    """Excel لجدولٍ مسجَّل — بالترويسة والتذييل الموحَّدين، وعربيّتُه يمينيّة."""
    from io import BytesIO

    import openpyxl
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    from core.excel_safety import safe_cell
    from core.export_utils import (
        add_excel_footer,
        add_excel_header,
        apply_print_footer,
        excel_table_styles,
        generate_export_filename,
        get_export_context_for,
    )

    columns, rows = table_rows(spec, user, params)
    ctx = get_export_context_for(user, spec.title)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = spec.title
    ws.sheet_view.rightToLeft = True

    headers = [NUMBER_LABEL, *(c.label for c in columns)]
    data_start = add_excel_header(ws, ctx, len(headers))
    table = excel_table_styles()
    for col, label in enumerate(headers, 1):
        cell = safe_cell(ws, row=data_start, column=col, value=label)
        cell.fill = table.header_fill
        cell.font = table.header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = table.border
    for r, values in enumerate(rows, 1):
        for col, value in enumerate(values, 1):
            cell = safe_cell(ws, row=data_start + r, column=col, value=value)
            cell.font = table.cell_font
            cell.border = table.border
            if r % 2 == 0:
                cell.fill = table.alt_fill
    for col in range(1, len(headers) + 1):
        longest = max(
            len(str(ws.cell(row=r, column=col).value or ""))
            for r in range(data_start, data_start + len(rows) + 1)
        )
        ws.column_dimensions[get_column_letter(col)].width = min(longest + 4, 40)
    add_excel_footer(ws, ctx, data_start + len(rows), len(headers))

    apply_print_footer(wb, school)
    buffer = BytesIO()
    wb.save(buffer)
    return registry.ExportResult(
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        generate_export_filename(spec.file_module, "list", "xlsx"),
        rows=len(rows),
        full_national_id=False,
    )


def register_table(spec: TableSpec) -> registry.ExportKind:
    """يسجّل الجدولَ في عقد التصدير ونوعَه في السجلّ المركزيّ — من `AppConfig.ready()`."""
    _TABLES[spec.kind] = spec
    return registry.register(spec.kind, build=partial(_build, spec), capability=spec.capability)


def _build(spec: TableSpec, school: Any, user: Any, params: Any) -> registry.ExportResult:
    return build_table_xlsx(spec, school, user, params)


def tables() -> dict[str, TableSpec]:
    """نسخةٌ من الجداول المسجَّلة (للحرّاس والاختبار)."""
    return dict(_TABLES)
