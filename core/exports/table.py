"""عقدُ التصدير الجدوليّ المركزيّ (W-20261109-001): المعروضُ فقط، بنطاق الدور، مرقَّماً ومفروزاً بالجناح.

لكلّ جدولٍ **محدِّدُ قائمةٍ واحدٌ** `rows_for(user, params)` في طبقة الخدمات تستعمله الصفحةُ والتصديرُ معاً، فلا يختلف
المعروضُ عن المُصدَّر. ويطبّق المحدِّدُ نطاقَ الدور (الجناح للمشرف…) والفلترَ **كاملاً** لا صفحةَ الترقيم الحاليّة.

وما يضيفه العقدُ عند الإخراج لا عند التخزين:

* عمودُ «م»: ترقيمٌ يُحسب بعد الفرز والإخفاء، ولا يُخزَّن في صفٍّ ولا مصدر.
* الفرزُ بالجناح: `WING_KEY_OF_ORDER` (`core/dept_colors.py`) للمدير والمشرف معاً — ثابتٌ بين الأجنحة وبعدها ما بلا جناح.
* الأعمدةُ المخفيّةُ في الشاشة (`hide=a,b` في المعاملات) تُخفى في الملف؛ ولا يُخفى كلُّ شيء.

وتسجَّل الأنواعُ بـ`register_table` فتدخل السجلَّ المركزيَّ (`registry`) بنّاءَيْ Excel وPDF من المحدِّد نفسِه.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from core.dept_colors import WING_KEY_OF_ORDER

from . import registry

#: مفتاحُ الجناح في صفّ المحدِّد (`Wing.order`)؛ غيابُه أو ما ليس بين الخمسة يُرتَّب بعد الأجنحة.
WING_ORDER_KEY = "wing_order"
#: ترويسةُ عمود الترقيم.
NUMBER_LABEL = "م"
#: مفتاحُ معاملِ الأعمدة المخفيّة في الرابط: `hide=wing,section` أو متكرّراً.
HIDE_PARAM = "hide"

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

Row = Mapping[str, Any]
RowsFor = Callable[[Any, Any], Sequence[Row]]


@dataclass(frozen=True)
class Column:
    key: str
    label: str


@dataclass(frozen=True)
class TableSpec:
    #: اسمُ النوع في السجلّ المركزيّ.
    kind: str
    #: عنوانُ الملفّ ومصنَّفه.
    title: str
    columns: tuple[Column, ...]
    #: المحدِّدُ الواحد — `(user, params: QueryDict) -> صفوفٌ كاملةٌ بعد الفلتر ونطاق الدور`.
    rows_for: RowsFor
    #: وحدةُ اسم الملفّ (`generate_export_filename`).
    module: str = "table"


def hidden_keys(params: Any) -> set[str]:
    """مفاتيحُ الأعمدة المخفيّة من المعاملات — قيمةٌ مفصولةٌ بفواصل أو مكرَّرة."""
    getlist = getattr(params, "getlist", None)
    values = getlist(HIDE_PARAM) if getlist else [params.get(HIDE_PARAM, "")]
    return {
        part.strip() for value in values for part in str(value or "").split(",") if part.strip()
    }


def visible_columns(spec: TableSpec, params: Any) -> tuple[Column, ...]:
    """أعمدةُ الجدول بعد الإخفاء؛ وإخفاءُ كلِّها يُهمَل (ملفٌّ بلا أعمدةٍ لا معنى له)."""
    hidden = hidden_keys(params)
    shown = tuple(col for col in spec.columns if col.key not in hidden)
    return shown or spec.columns


def wing_sort_key(row: Row) -> int:
    """ترتيبُ الجناح بـ`WING_KEY_OF_ORDER`؛ ما بلا جناحٍ معروفٍ بعد الأخير."""
    try:
        order = int(str(row.get(WING_ORDER_KEY)))
    except (TypeError, ValueError):
        return len(WING_KEY_OF_ORDER) + 1
    return order if order in WING_KEY_OF_ORDER else len(WING_KEY_OF_ORDER) + 1


def sort_by_wing(rows: Sequence[Row]) -> list[Row]:
    """فرزٌ مستقرٌّ بالجناح: ترتيبُ المحدِّد (الاسم مثلاً) يبقى داخل الجناح الواحد."""
    return sorted(rows, key=wing_sort_key)


def table_rows(
    spec: TableSpec, user: Any, params: Any
) -> tuple[tuple[Column, ...], list[list[Any]]]:
    """`(الأعمدةُ المرئيّة، الصفوفُ مرقَّمةً)` — مصدرُ Excel وPDF معاً."""
    columns = visible_columns(spec, params)
    ordered = sort_by_wing(spec.rows_for(user, params))
    body = [[n, *(row.get(col.key, "") for col in columns)] for n, row in enumerate(ordered, 1)]
    return columns, body


def build_xlsx(spec: TableSpec, school: Any, user: Any, params: Any) -> registry.ExportResult:
    import openpyxl
    from openpyxl.styles import Alignment

    from core.excel_safety import safe_cell
    from core.export_utils import (
        add_excel_footer,
        add_excel_header,
        apply_print_footer,
        excel_table_styles,
        generate_export_filename,
        get_export_context_for,
    )

    columns, body = table_rows(spec, user, params)
    headers = [NUMBER_LABEL, *(col.label for col in columns)]
    ctx = get_export_context_for(user, spec.title)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = spec.title[:31]
    ws.sheet_view.rightToLeft = True
    start = add_excel_header(ws, ctx, len(headers))
    style = excel_table_styles()
    for col, label in enumerate(headers, 1):
        cell = safe_cell(ws, row=start, column=col, value=label)
        cell.fill = style.header_fill
        cell.font = style.header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = style.border
    for i, values in enumerate(body, 1):
        for col, val in enumerate(values, 1):
            cell = safe_cell(ws, row=start + i, column=col, value=val)
            cell.font = style.cell_font
            cell.border = style.border
            if i % 2 == 0:
                cell.fill = style.alt_fill
    for col in range(1, len(headers) + 1):
        longest = max(
            len(str(ws.cell(row=r, column=col).value or ""))
            for r in range(start, start + len(body) + 1)
        )
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = min(longest + 4, 40)
    add_excel_footer(ws, ctx, start + len(body), len(headers))
    apply_print_footer(wb, school)
    buffer = BytesIO()
    wb.save(buffer)
    return registry.ExportResult(
        buffer.getvalue(),
        XLSX_TYPE,
        generate_export_filename(spec.module, spec.kind.rsplit(".", 1)[-1], "xlsx"),
        rows=len(body),
    )


def build_pdf(spec: TableSpec, school: Any, user: Any, params: Any) -> registry.ExportResult:
    from django.template.loader import render_to_string

    from core.export_utils import (
        generate_export_filename,
        get_export_context_for,
        get_pdf_footer_html,
        get_pdf_header_html,
    )
    from core.pdf_utils import render_pdf_bytes

    columns, body = table_rows(spec, user, params)
    ctx = get_export_context_for(user, spec.title)
    html = render_to_string(
        "core/exports/table_pdf.html",
        {
            "title": spec.title,
            "headers": [NUMBER_LABEL, *(col.label for col in columns)],
            "rows": body,
            "total": len(body),
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            "for_pdf": True,
            **ctx,
        },
    )
    return registry.ExportResult(
        render_pdf_bytes(html, paper_size="A4"),
        "application/pdf",
        generate_export_filename(spec.module, spec.kind.rsplit(".", 1)[-1], "pdf"),
        rows=len(body),
    )


def register_table(spec: TableSpec, *, capability: str) -> tuple[registry.ExportKind, ...]:
    """يسجّل `<kind>_xlsx` و`<kind>_pdf` في السجلّ المركزيّ — خلفيّان افتراضاً (لا قياسَ p95 بعد)."""
    return (
        registry.register(
            f"{spec.kind}_xlsx",
            build=lambda school, user, params: build_xlsx(spec, school, user, params),
            capability=capability,
        ),
        registry.register(
            f"{spec.kind}_pdf",
            build=lambda school, user, params: build_pdf(spec, school, user, params),
            capability=capability,
        ),
    )
