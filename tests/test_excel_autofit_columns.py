"""عرضُ أعمدة إكسل يتبع أطولَ قيمةٍ لا رقماً ثابتاً (قاعدةُ الأعمدة المرنة، W-20261013-025)."""

from openpyxl import Workbook

from core.export_utils import autofit_columns


def test_the_serial_column_stays_narrow_and_the_long_name_gets_room():
    ws = Workbook().active
    ws.append(["م", "اسم الطالب"])
    ws.append([1, "عبدالرحمن محمد سلطان الكواري الدوسري"])
    ws.append([2, "علي"])
    autofit_columns(ws, 1)
    assert ws.column_dimensions["A"].width <= 8, "التسلسلُ بقدر محتواه"
    assert ws.column_dimensions["B"].width > 35, "الاسمُ كاملٌ في خليّته"


def test_the_width_has_a_sane_cap():
    ws = Workbook().active
    ws.append(["ملاحظات"])
    ws.append(["ك" * 500])
    autofit_columns(ws, 1, max_width=60)
    assert ws.column_dimensions["A"].width == 60
