"""
core/export_utils.py — أدوات تصدير موحّدة لكل المنصة
أسماء ملفات + هيدر + فوتر + توقيع المُصدِّر
"""

import uuid
from pathlib import Path
from typing import NamedTuple

from django.conf import settings
from django.utils import timezone

from core import brand
from core.academic_calendar import academic_year_for_school


def generate_export_filename(module: str, report_type: str, ext: str) -> str:
    """
    اسم ملف موحّد: SchoolOS_{module}_{type}_{YYYYMMDD}_{HHMMSS}_{6hex}.{ext}
    مثال: SchoolOS_students_list_20260403_143022_a7f3b2.xlsx
    """
    now = timezone.localtime()
    short_id = uuid.uuid4().hex[:6]
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    return f"SchoolOS_{module}_{report_type}_{date_str}_{time_str}_{short_id}.{ext}"


def get_export_context(request, title: str) -> dict:
    """
    context موحّد لجميع التصديرات (Excel + PDF):
    - school_name, school_logo_path
    - exported_by (الاسم), exporter_role (الدور)
    - export_date, export_time, export_datetime
    - title, academic_year
    """
    user = request.user
    school = user.get_school()
    now = timezone.localtime()

    ROLE_AR = {
        "principal": "مدير المدرسة",
        "vice_admin": "نائب المدير الإداري",
        "vice_academic": "نائب المدير الأكاديمي",
        "coordinator": "المنسق",
        "teacher": "المعلم",
        "social_worker": "الأخصائي الاجتماعي",
        "psychologist": "الأخصائي النفسي",
        "admin": "الإداري",
        "platform_developer": "مطور المنصة",
        "nurse": "الممرض",
        "librarian": "أمين المكتبة",
    }

    role_en = user.get_role() or "—"
    logo_path = str(Path(settings.BASE_DIR) / "static" / "brand" / "logoMaroon.png")

    return {
        "school_name": school.name if school else "المدرسة",
        "school_logo_path": str(Path(settings.BASE_DIR) / "static" / "brand" / "logowhite.png"),
        "logo_path": logo_path,
        "exported_by": user.full_name,
        "exporter_role": role_en,
        "exporter_role_ar": ROLE_AR.get(role_en, role_en),
        "export_date": now.strftime("%d/%m/%Y"),
        "export_time": now.strftime("%H:%M"),
        "export_datetime": now.strftime("%d/%m/%Y %H:%M"),
        "title": title,
        "academic_year": academic_year_for_school(school),
        "ministry": "وزارة التربية والتعليم والتعليم العالي — دولة قطر",
    }


#: خطُّ الهويّة في كلّ ملفّ Excel — خطُّ المنصّة نفسُه. وكانت المولّداتُ على
#: ثلاثة: Tajawal في شؤون الطلبة، وArial في التقارير وتصدير الطلبة، وخطُّ Excel
#: الافتراضيّ في كشف الدرجات. ومن لا يملك Tajawal يرى بديلَ Excel العربيّ.
EXCEL_FONT = "Tajawal"


def xl_fill(colour: str):
    """حشوٌ صمتٌ بلونٍ من `core.brand`."""
    from openpyxl.styles import PatternFill

    value = brand.excel(colour)
    return PatternFill(start_color=value, end_color=value, fill_type="solid")


def xl_font(
    colour: str = brand.TEXT_PRIMARY, size: float = 10, bold: bool = False, italic: bool = False
):
    """خطُّ الهويّة بلونٍ من `core.brand` — لا خطَّ ولا لونَ يُكتب في مولّد."""
    from openpyxl.styles import Font

    return Font(name=EXCEL_FONT, size=size, bold=bold, italic=italic, color=brand.excel(colour))


class ExcelTableStyles(NamedTuple):
    header_fill: object
    header_font: object
    header_align: object
    cell_font: object
    data_align: object
    border: object
    alt_fill: object


def excel_table_styles() -> ExcelTableStyles:
    """ترويسةُ الجدول وصفوفُه في كلّ تصديرات Excel — نمطٌ واحدٌ للمنصّة كلِّها.

    كانت ستُّ نسخٍ في أربعة ملفّات، تتّفق على العنّابيّ وتختلف في كلّ ما سواه:
    ثلاثةُ خطوط، وشبكةٌ بلا لونٍ أو `DDDDDD` أو `CCCCCC`، وصفٌّ متناوبٌ بلونين،
    وترويسةٌ كحليّةٌ في تصدير الدرجات. فصار الجدولُ واحداً أيّاً كان مصدرُه.
    """
    from openpyxl.styles import Alignment, Border, Side

    side = Side(style="thin", color=brand.excel(brand.BORDER))
    return ExcelTableStyles(
        header_fill=xl_fill(brand.MAROON),
        header_font=xl_font(brand.ON_FILL, size=11, bold=True),
        header_align=Alignment(horizontal="center", vertical="center", wrap_text=True),
        cell_font=xl_font(),
        data_align=Alignment(horizontal="center", vertical="center", wrap_text=True),
        border=Border(left=side, right=side, top=side, bottom=side),
        alt_fill=xl_fill(brand.MAROON_BG),
    )


def brand_cell(cell) -> None:
    """خانةٌ بلا خطٍّ صريحٍ تأخذ خطَّ الهويّة — وما لُوِّن قبلها يبقى لونُه وعرضُه."""
    from openpyxl.styles import Font

    f = cell.font
    if f.name == EXCEL_FONT:
        return
    color = f.color if (f.color is not None and f.color.rgb not in (None, "FF000000")) else None
    cell.font = Font(
        name=EXCEL_FONT,
        size=f.sz if f.name not in (None, "Calibri") else 10,
        bold=f.b,
        italic=f.i,
        color=color or brand.excel(brand.TEXT_PRIMARY),
    )


def add_excel_title_rows(ws, num_cols: int, first: str, second: str, third: str) -> None:
    """الصفوفُ الثلاثةُ الأولى في كلّ ملفّ Excel — ترويسةٌ واحدةٌ للمنصّة.

    ١ عنّابيٌّ بنصٍّ أبيضَ كبير وشعارِ المدرسة، ٢ عنّابيٌّ فاتحٌ بنصٍّ أبيض،
    ٣ عنّابيٌّ خفيفٌ بنصٍّ خافت. وكانت نسختان منها بتصميمين: هذه في شؤون
    الطلبة، وأخرى فاتحةٌ بخطٍّ عنّابيّ في التقارير وتصدير الطلبة — ثلاثَ مرّات.
    """
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment

    center = Alignment(horizontal="center", vertical="center")
    rows = (
        (first, xl_fill(brand.MAROON), xl_font(brand.ON_FILL, size=14, bold=True), 40),
        (second, xl_fill(brand.MAROON_LIGHT), xl_font(brand.ON_FILL, size=11, bold=True), 28),
        (third, xl_fill(brand.MAROON_BG), xl_font(brand.TEXT_MUTED, size=9), 22),
    )
    for row, (value, fill, font, height) in enumerate(rows, start=1):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
        cell = ws.cell(row=row, column=1, value=value)
        cell.fill = fill
        cell.font = font
        cell.alignment = center
        ws.row_dimensions[row].height = height

    logo = Path(settings.BASE_DIR) / "static" / "brand" / "logowhite.png"
    if logo.exists():
        try:
            img = XLImage(str(logo))
            img.width = 36
            img.height = 36
            ws.add_image(img, "A1")
        except (OSError, ValueError):
            pass


def add_excel_header(ws, context: dict, num_cols: int):
    """
    هيدر Excel احترافي موحّد:
    صف 1: [شعار] اسم المدرسة — الوزارة (merged)
    صف 2: عنوان التقرير — العام الدراسي (merged)
    صف 3: صدر بواسطة: الاسم — الدور — التاريخ (merged)
    صف 4: (فارغ)
    صف 5: بداية headers البيانات
    يُعيد رقم أول صف للبيانات (5)
    """
    add_excel_title_rows(
        ws,
        num_cols,
        f"{context['school_name']}  —  {context['ministry']}",
        f"{context['title']}  —  العام الدراسي {context['academic_year']}",
        f"صدر بواسطة: {context['exported_by']} — {context['exporter_role']}  |  {context['export_datetime']}",
    )
    ws.row_dimensions[4].height = 8
    return 5  # أول صف للبيانات


def add_excel_footer(ws, context: dict, row: int, num_cols: int):
    """
    فوتر Excel: توقيع المُصدِّر + معلومات المدرسة
    """
    from openpyxl.styles import Alignment, Border, Side

    thin_top = Border(top=Side(style="medium", color=brand.excel(brand.MAROON)))
    footer_font = xl_font(brand.TEXT_MUTED, size=9)
    sig_font = xl_font(brand.TEXT_SECONDARY, size=9, bold=True)

    # صف فارغ
    row += 1

    # توقيع المُصدِّر
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
    cell = ws.cell(
        row=row,
        column=1,
        value=f"صدر بواسطة: {context['exported_by']}  —  {context['exporter_role']}",
    )
    cell.font = sig_font
    cell.alignment = Alignment(horizontal="right")
    cell.border = thin_top

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
    cell = ws.cell(row=row, column=1, value=f"التاريخ: {context['export_datetime']}")
    cell.font = footer_font
    cell.alignment = Alignment(horizontal="right")

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=num_cols)
    cell = ws.cell(
        row=row, column=1, value=f"{context['school_name']}  —  وثيقة رسمية  —  SchoolOS"
    )
    cell.font = footer_font
    cell.alignment = Alignment(horizontal="center")

    return row


def get_pdf_header_html(context: dict) -> str:
    """
    HTML هيدر PDF موحّد — يُدرج في أعلى كل template PDF
    """
    return f"""
    <div style="text-align:center;border-bottom:3px solid {brand.MAROON};padding-bottom:12px;margin-bottom:20px">
      <h1 style="color:{brand.MAROON};font-size:16pt;margin:0">{context["school_name"]}</h1>
      <p style="font-size:9pt;color:#666;margin:2px 0 0">{context["ministry"]}</p>
      <p style="font-size:11pt;font-weight:700;color:#333;margin:8px 0 0">{context["title"]}</p>
      <p style="font-size:8pt;color:#999;margin:4px 0 0">العام الدراسي {context["academic_year"]}</p>
    </div>
    """


def get_pdf_footer_html(context: dict) -> str:
    """
    HTML فوتر PDF — توقيع المُصدِّر في أسفل كل صفحة
    """
    return f"""
    <div style="text-align:center;font-size:8pt;color:#999;border-top:1px solid #ddd;padding-top:8px;margin-top:30px">
      <p style="margin:0"><strong style="color:#333">صدر بواسطة:</strong> {context["exported_by"]} — {context["exporter_role"]}</p>
      <p style="margin:2px 0 0">التاريخ: {context["export_datetime"]}</p>
      <p style="margin:2px 0 0">{context["school_name"]} — وثيقة رسمية — SchoolOS</p>
    </div>
    """


def excel_to_response(wb, filename: str):
    """تحويل workbook إلى HttpResponse للتحميل"""
    from io import BytesIO

    from django.http import HttpResponse

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
