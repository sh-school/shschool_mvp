"""عقدُ التصدير المركزيّ: المعروضُ فقط حسب الدور — W-20261109-012.

كلُّ جدولٍ يُصدَّر يملك **محدِّدَ قائمةٍ واحداً** `rows_for(user, params)` في طبقة خدماته، تستعمله الصفحةُ والتصديرُ معاً،
فيطبّق نطاقَ الدور (جناحُ المشرف) والفلترَ كاملاً — لا صفحةَ الترقيم الحاليّة وحدَها (رفض المالكُ تصديرَ «الكلّ» بدل
«المعروض بعد الفلترة»، الطلب 1413). وهذا الملفّ يحمل ما يشترك فيه كلُّ نوعٍ:

* **الترقيم**: عمودُ «م» يُحسب عند الإخراج (`numbered`) ولا يُخزَّن في الصفّ.
* **الفرزُ بالجناح**: بترتيب `WING_KEY_OF_ORDER` (`core/dept_colors.py`) للمدير والمشرف معاً، والاسمُ فاصلٌ داخل الجناح.
* **الأعمدةُ المخفيّة**: ما أُخفي في الشاشة (`?hide=key,key`) يُخفى في الملف.
* **بنّاءُ Excel عامّ** (`table_xlsx`) بالترويسة والتذييل الموحَّدَين.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from core.dept_colors import WING_KEY_OF_ORDER
from core.exports.registry import ExportResult

#: رأسُ عمود الترقيم — يُحسب عند الإخراج.
NUMBER_HEADER = "م"

#: معاملُ الرابط الذي يحمل أعمدةَ الشاشة المخفيّة (مفاتيحُ مفصولةٌ بفواصل).
HIDE_PARAM = "hide"

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Column:
    #: مفتاحُ الحقل في صفّ `rows_for` وهو نفسُه ما تخفيه الشاشة.
    key: str
    label: str


def hidden_columns(params: Any) -> frozenset[str]:
    """مفاتيحُ الأعمدة المخفيّة في الشاشة من `?hide=`."""
    raw = params.get(HIDE_PARAM) or ""
    return frozenset(part.strip() for part in str(raw).split(",") if part.strip())


def visible_columns(columns: Sequence[Column], params: Any) -> list[Column]:
    """الأعمدةُ المعروضةُ وحدَها بترتيبها."""
    hidden = hidden_columns(params)
    return [c for c in columns if c.key not in hidden]


def numbered(rows: Sequence[Any]) -> Iterator[tuple[int, Any]]:
    """`(م، الصفّ)` يبدأ من 1 — محسوبٌ عند الإخراج فلا يُخزَّن."""
    return enumerate(rows, 1)


def wing_rank(order: object) -> int:
    """موضعُ الجناح في `WING_KEY_OF_ORDER`؛ ومن لا جناحَ له (أو خارج الخمسة) يذهب إلى الذيل."""
    try:
        n = int(str(order))
    except (TypeError, ValueError):
        return len(WING_KEY_OF_ORDER) + 1
    keys = list(WING_KEY_OF_ORDER)
    return keys.index(n) if n in WING_KEY_OF_ORDER else len(keys) + 1


def sort_by_wing(rows: list[dict[str, Any]], key: str = "wing_order") -> list[dict[str, Any]]:
    """فرزٌ مستقرٌّ بالجناح: يحفظ ترتيبَ الدخول (الاسمَ) داخل كلّ جناح."""
    return sorted(rows, key=lambda row: wing_rank(row.get(key)))


def table_xlsx(
    user: Any,
    school: Any,
    title: str,
    columns: Sequence[Column],
    rows: Sequence[dict[str, Any]],
    *,
    filename: str,
) -> ExportResult:
    """مصنَّفٌ بالأعمدة المعروضة وحدَها وعمودِ «م» أوّلاً، بترويسة المدرسة وتذييلها الموحَّدَين."""
    import openpyxl
    from openpyxl.styles import Alignment

    from core.excel_safety import safe_cell
    from core.export_utils import (
        add_excel_footer,
        add_excel_header,
        apply_print_footer,
        autofit_columns,
        excel_table_styles,
        get_export_context_for,
    )

    ctx = get_export_context_for(user, title)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.sheet_view.rightToLeft = True

    headers = [NUMBER_HEADER, *(c.label for c in columns)]
    data_start = add_excel_header(ws, ctx, len(headers))
    style = excel_table_styles()
    for col, header in enumerate(headers, 1):
        cell = safe_cell(ws, row=data_start, column=col, value=header)
        cell.fill = style.header_fill
        cell.font = style.header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = style.border
    for i, row in numbered(rows):
        values = [i, *(row.get(c.key, "") for c in columns)]
        for col, value in enumerate(values, 1):
            cell = safe_cell(ws, row=data_start + i, column=col, value=value)
            cell.font = style.cell_font
            cell.border = style.border
            if i % 2 == 0:
                cell.fill = style.alt_fill
    autofit_columns(ws, data_start)
    add_excel_footer(ws, ctx, data_start + len(rows), len(headers))
    apply_print_footer(wb, school)
    buffer = BytesIO()
    wb.save(buffer)
    return ExportResult(
        buffer.getvalue(), XLSX_TYPE, filename, rows=len(rows), full_national_id=False
    )
