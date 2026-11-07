"""بنّاءُ «شهادات الفصل» PDF لسجلّ التصدير المركزيّ (`core.exports.registry`).

دالّةٌ نقيّةٌ بلا `request`: تعمل في عاملِ Celery (`core.export.run_job`) — الفصلُ من `class_id` المحفوظ مع الاستعلام،
والقالبُ `for_pdf` بلا `{% static %}` (العاملُ لا يملك manifest الويب: Sentry SCHOOLOS-PRODUCTION-2X). وتُسجَّل من `ReportsConfig.ready()`.

يُنشئ المهمّةَ زرُّ «تحميل» في عارض التقارير (`download=1`)؛ أمّا الإطارُ المضمَّنُ في العارض والمعاينةُ (`preview=1`) فيبقيان في الـview
(`reports.views.class_certificates_pdf`) إلى أن يُصمَّم عرضٌ يقرأ المهمّة.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string

from core.academic_calendar import academic_year_for_school
from core.exports.registry import ExportResult
from core.models import ClassGroup

from .selectors import class_certificates_context, paper_size, teacher_can_access_class


def build_class_certificates_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """شهادةٌ لكلّ طالبٍ في الفصل على صفحةٍ — كان 2.9ث متزامناً (قياس 2026-09-26).

    الرقمُ الشخصيُّ مستورٌ في القالب (كشفٌ جماعيّ: ملفٌّ واحدٌ لفصلٍ كامل)، والشهادةُ الفرديّةُ وحدَها تحمله كاملاً.
    """
    from core.pdf_utils import render_pdf_bytes

    if not user.is_admin():  # كما في الـview؛ القدرةُ وحدَها يفحصها العاملُ ثانيةً
        raise PermissionDenied
    class_grp = ClassGroup.objects.get(id=params["class_id"], school=school)
    year = params.get("year") or academic_year_for_school(school)
    paper = paper_size(params)

    page_ctx = class_certificates_context(school, class_grp, year, paper)
    html = render_to_string("reports/class_certificates.html", {**page_ctx, "for_pdf": True})
    return ExportResult(
        render_pdf_bytes(html, paper_size=paper),
        "application/pdf",
        f"شهادات_{class_grp.grade.removeprefix('G')}_{class_grp.section}_{year}.pdf",
        rows=len(page_ctx["students_ctx"]),
        full_national_id=False,
        object_id=str(class_grp.pk),
    )


def build_class_results_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    """كشف نتائج الفصل Excel — خلفيّ (W-20261027-029). الرقمُ الشخصيُّ مستور (كشفٌ جماعيّ)."""
    from .services import ExcelService

    if not (
        user.is_admin() or user.is_teacher()
    ):  # كما في الـview؛ القدرةُ وحدَها يفحصها العاملُ ثانيةً
        raise PermissionDenied
    class_grp = ClassGroup.objects.get(id=params["class_id"], school=school)
    year = params.get("year") or academic_year_for_school(school)
    # [SEC-04] المعلّم لا يصدّر إلا فصوله — يُعاد الفحصُ هنا لأنّ الصلاحيّةَ قد تتغيّر بين الطلب والتنفيذ.
    if not teacher_can_access_class(user, school, class_grp, year):
        raise PermissionDenied
    resp = ExcelService.class_results_excel(
        class_grp, school, year, paper=paper_size(params).lower()
    )
    return ExportResult(
        resp.content,
        resp["Content-Type"],
        f"نتائج_{class_grp.grade.removeprefix('G')}_{class_grp.section}_{year}.xlsx",
        rows=class_grp.enrollments.filter(is_active=True).count(),
        full_national_id=False,
        object_id=str(class_grp.pk),
    )


def build_attendance_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    """كشف الغياب Excel لفصلٍ — خلفيّ (W-20261021-011). الرقمُ الشخصيُّ مستور (كشفٌ جماعيّ)."""
    from .services import ExcelService

    if not user.is_admin():  # كما في الـview؛ القدرةُ وحدَها يفحصها العاملُ ثانيةً
        raise PermissionDenied
    class_grp = ClassGroup.objects.get(id=params["class_id"], school=school)
    year = params.get("year") or academic_year_for_school(school)
    resp = ExcelService.attendance_excel(class_grp, school, year, paper=paper_size(params).lower())
    return ExportResult(
        resp.content,
        resp["Content-Type"],
        f"غياب_{class_grp.grade.removeprefix('G')}_{class_grp.section}_{year}.xlsx",
        rows=class_grp.enrollments.filter(is_active=True).count(),
        full_national_id=False,
        object_id=str(class_grp.pk),
    )


def build_behavior_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    """كشف المخالفات السلوكيّة Excel للمدرسة — خلفيّ (W-20261021-011). الرقمُ الشخصيُّ مستور."""
    from .services import ExcelService

    if not user.is_admin():
        raise PermissionDenied
    year = params.get("year") or academic_year_for_school(school)
    resp = ExcelService.behavior_excel(school, year, paper=paper_size(params).lower())
    return ExportResult(
        resp.content,
        resp["Content-Type"],
        f"مخالفات_سلوكية_{year}.xlsx",
        full_national_id=False,
    )


#: أعمدةُ التقرير السلوكيّ اليوميّ (ترتيبُها ترتيبُ الشاشة وPDF وExcel) — لا وصفَ ولا رقمَ شخصيّاً ولا وليَّ أمر.
BEHAVIOR_DAILY_COLUMNS = (
    ("student", "الطالب"),
    ("class_label", "الشعبة"),
    ("violation", "المخالفة"),
    ("level", "الدرجة"),
    ("step", "الخطوة"),
    ("reporter", "الراصد"),
)


def build_behavior_daily_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """التقرير السلوكيّ اليوميّ PDF — الصفوفُ نفسُها بترتيبها من `daily_report` (المصدر الواحد مع الشاشة وExcel)."""
    from behavior.selectors import daily_report
    from core.export_utils import get_export_context_for, get_pdf_footer_html, get_pdf_header_html
    from core.pdf_utils import render_pdf_bytes

    data = daily_report(school, user, params)
    ctx = get_export_context_for(user, "تقرير السلوك اليومي")
    html = render_to_string(
        "behavior/daily_report_pdf.html",
        {
            **data,
            "columns": BEHAVIOR_DAILY_COLUMNS,
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            "for_pdf": True,
            **ctx,
        },
    )
    return ExportResult(
        render_pdf_bytes(html, paper_size="A4"),
        "application/pdf",
        f"سلوك_يومي_{data['day']:%Y-%m-%d}.pdf",
        rows=len(data["rows"]),
        full_national_id=False,
    )


def build_behavior_daily_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    """التقرير السلوكيّ اليوميّ Excel — عددًا وترتيبًا كالشاشة؛ الرقمُ الشخصيُّ لا يدخل الملفّ."""
    from io import BytesIO

    import openpyxl
    from openpyxl.styles import Alignment

    from behavior.selectors import daily_report
    from core.excel_safety import safe_cell
    from core.export_utils import (
        add_excel_footer,
        add_excel_header,
        apply_print_footer,
        excel_table_styles,
        get_export_context_for,
    )

    data = daily_report(school, user, params)
    rows = data["rows"]
    ctx = get_export_context_for(user, "تقرير السلوك اليومي")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "السلوك اليومي"
    ws.sheet_view.rightToLeft = True

    headers = ["#", *(label for _key, label in BEHAVIOR_DAILY_COLUMNS)]
    data_start = add_excel_header(ws, ctx, len(headers))
    table = excel_table_styles()
    for col, header in enumerate(headers, 1):
        cell = safe_cell(ws, row=data_start, column=col, value=header)
        cell.fill = table.header_fill
        cell.font = table.header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = table.border

    for i, row in enumerate(rows, 1):
        values = [i, *(row[key] for key, _label in BEHAVIOR_DAILY_COLUMNS)]
        for col, val in enumerate(values, 1):
            cell = safe_cell(ws, row=data_start + i, column=col, value=val)
            cell.font = table.cell_font
            cell.border = table.border
            if i % 2 == 0:
                cell.fill = table.alt_fill

    for col_idx in range(1, len(headers) + 1):
        longest = max(
            len(str(ws.cell(row=r, column=col_idx).value or ""))
            for r in range(data_start, data_start + len(rows) + 1)
        )
        ws.column_dimensions[chr(64 + col_idx)].width = min(longest + 4, 40)

    add_excel_footer(ws, ctx, data_start + len(rows), len(headers))
    apply_print_footer(wb, school)
    buffer = BytesIO()
    wb.save(buffer)
    return ExportResult(
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"سلوك_يومي_{data['day']:%Y-%m-%d}.xlsx",
        rows=len(rows),
        full_national_id=False,
    )
