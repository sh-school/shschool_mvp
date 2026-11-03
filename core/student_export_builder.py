"""بنّاءُ «كشف الطلاب الكامل» Excel لسجلّ التصدير المركزيّ (`core.exports.registry`) — W-20261021-011.

دالّةٌ نقيّةٌ بلا `request`: تعمل في عاملِ Celery. الرقمُ الشخصيُّ كاملٌ عمداً (مطابقةٌ وزاريّة — قرار المالك 2026-09-14)،
فيُدقَّق بالرايةِ `full_national_id=True` في سطر العامل. أدواتُ الورقة (`_make_styles`…) من `core.views_students` كما كانت.
"""

from __future__ import annotations

import io
from typing import Any

from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.excel_safety import safe_cell
from core.export_utils import add_excel_title_rows, apply_print_footer, autofit_columns
from core.exports.registry import ExportResult
from core.ministry import ministry_line, ministry_name
from core.models import Membership, Role, StudentEnrollment

from .views_students import EXPORT_COLUMNS, _add_header_row, _make_styles, _style_data_row


def build_students_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    """الرقم الشخصيّ: مطابقةٌ وزاريّة — كامل. أعمدتُه أعمدةُ قالب الاستيراد نفسُها و`students_import` يطابق عليه."""
    year = academic_year_for_school(school)

    student_role = Role.objects.filter(name="student").first()
    if not student_role:
        raise ValueError("دور الطالب غير موجود")

    # جلب الطلاب مع تسجيلاتهم دفعةً واحدة (N+1 safe)
    memberships = (
        Membership.objects.filter(school=school, role=student_role, is_active=True)
        .select_related("user")
        .order_by("user__full_name")
    )

    student_ids = [m.user_id for m in memberships]
    enrollments_qs = StudentEnrollment.objects.filter(
        student_id__in=student_ids, is_active=True
    ).select_related("class_group")
    enrollment_map = {enr.student_id: enr for enr in enrollments_qs}

    # ── بناء Workbook ───────────────────────────────────────────────
    import openpyxl
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "الطلاب"
    ws.sheet_view.rightToLeft = True

    styles = _make_styles()
    today_str = timezone.now().strftime("%Y/%m/%d")

    num_cols = len(EXPORT_COLUMNS)
    col_letter = get_column_letter(num_cols)

    # ── صفوف الرأس الثلاثة ──────────────────────────────────────────
    add_excel_title_rows(
        ws,
        num_cols,
        school.name,
        f"كشف الطلاب الكامل  —  السنة الدراسية {year}",
        ministry_line(ministry_name(), today_str, sep="  |  "),
    )

    # ── صف رأس الأعمدة (الصف 4) ────────────────────────────────────
    _add_header_row(ws, styles, 4, EXPORT_COLUMNS)

    # ── البيانات (تبدأ من الصف 5) ───────────────────────────────────
    for idx, mem in enumerate(memberships, start=1):
        row_num = idx + 4
        st = mem.user
        enr = enrollment_map.get(st.id)
        grade_display = ""
        section_display = ""
        if enr:
            grade_digits = "".join(c for c in enr.class_group.grade if c.isdigit())
            grade_display = grade_digits.zfill(2) if grade_digits else enr.class_group.grade
            section_display = enr.class_group.section

        safe_cell(ws, row=row_num, column=1, value=st.national_id or "")
        safe_cell(ws, row=row_num, column=2, value=st.full_name)
        safe_cell(ws, row=row_num, column=3, value=grade_display)
        safe_cell(ws, row=row_num, column=4, value=section_display)
        safe_cell(ws, row=row_num, column=5, value=st.get_phone_decrypted() or "")
        safe_cell(ws, row=row_num, column=6, value=st.email or "")

        _style_data_row(ws, styles, row_num, num_cols, idx % 2 == 0)

    num_data_rows = len(memberships)

    # ── تجميد + فلاتر ────────────────────────────────────────────────
    autofit_columns(ws, 4)  # تجميد + فلاتر: العرضُ من أطول قيمةٍ لا رقماً ثابتاً
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{col_letter}4"

    # ── إعداد الطباعة A4 ─────────────────────────────────────────────
    ws.page_setup.paperSize = 9
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = 0.4
    ws.page_margins.right = 0.4
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5
    ws.page_margins.header = 0.2
    ws.page_margins.footer = 0.2
    ws.print_title_rows = "1:4"
    ws.print_area = f"A1:{col_letter}{num_data_rows + 4}"
    ws.oddFooter.center.text = "&P / &N"
    ws.oddFooter.right.text = "&D"

    apply_print_footer(wb, school)
    buf = io.BytesIO()
    wb.save(buf)
    return ExportResult(
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"طلاب_{school.name}_{year}_{today_str.replace('/', '-')}.xlsx",
        rows=num_data_rows,
        full_national_id=True,
    )
