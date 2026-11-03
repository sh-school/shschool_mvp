"""سطرُ «آخر تحديث للبيانات» في ترويسة كلّ ملفّ Excel (W-20261021-009)."""

from datetime import UTC, datetime

import openpyxl

from core.export_utils import DATA_AS_OF_LABEL, add_excel_title_rows, with_data_as_of


def _third_row(**kw) -> str:
    ws = openpyxl.Workbook().active
    add_excel_title_rows(ws, 6, "مدرسةٌ", "تقرير", "الوزارة | 2026/11/03", **kw)
    return str(ws.cell(row=3, column=1).value)


def test_every_title_block_carries_the_data_as_of_line():
    third = _third_row()
    assert third.startswith("الوزارة | 2026/11/03") and f"{DATA_AS_OF_LABEL}:" in third


def test_explicit_as_of_is_used_and_not_duplicated():
    when = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    line = with_data_as_of("x", when)
    assert line.endswith("12:30") or line.endswith(
        "09:30"
    )  # بحسب منطقة الإعدادات؛ المهمّ وجودُ الوقت المُمرَّر
    assert with_data_as_of(line, when) == line  # لا تكرار إن حمله السطر


def test_third_row_stays_a_single_merged_row():
    ws = openpyxl.Workbook().active
    add_excel_title_rows(ws, 6, "م", "ت", "ث")
    assert any(str(r) == "A3:F3" for r in ws.merged_cells.ranges)
