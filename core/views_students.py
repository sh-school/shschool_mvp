"""
core/views_students.py
══════════════════════════════════════════════════════════════════════
استيراد / تصدير بيانات الطلاب — Excel
══════════════════════════════════════════════════════════════════════

يشمل:
  - student_import_export  : صفحة إدارة الاستيراد والتصدير (GET/POST)
  - student_export_excel   : تنزيل ملف Excel بكل بيانات الطلاب
  - student_import_template: تنزيل قالب Excel فارغ للاستيراد
"""

from __future__ import annotations

import logging
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core import brand
from core.academic_calendar import academic_year_for_school, default_academic_year
from core.capabilities import capability_required
from core.export_utils import (
    add_excel_title_rows,
    brand_cell,
    excel_table_styles,
    xl_fill,
    xl_font,
)
from core.services import (  # noqa: F401 — أسماءٌ كانت هنا وتستوردها الاختبارات
    _IMPORT_GRADE_NORMALIZE,
    _parse_import_row,
    _split_class_notation,
    count_active_students,
    import_result_context,
    process_student_import,
)

logger = logging.getLogger(__name__)

# الأعمدة الثابتة لملف الاستيراد/التصدير
EXPORT_COLUMNS = [
    ("الرقم الشخصي", 18),
    ("الاسم الكامل", 30),
    ("الصف", 10),
    ("الشعبة", 10),
    ("الجوال", 18),
    ("البريد الإلكتروني", 28),
]

# أعمدة القالب — تُضاف عمود ولي الأمر
TEMPLATE_COLUMNS = [
    ("الرقم الشخصي", 18),
    ("الاسم الكامل", 30),
    ("الصف (G7-G12)", 12),
    ("الشعبة (أ/ب/ج...)", 12),
    ("الجوال", 18),
    ("البريد الإلكتروني", 28),
    ("الرقم الشخصي ولي الأمر", 20),
    ("اسم ولي الأمر", 28),
    ("جوال ولي الأمر", 18),
    ("بريد ولي الأمر", 28),
    ("صلة القرابة (father/mother/guardian)", 30),
]

# ══════════════════════════════════════════════════════════════════════
# مساعدات Excel
# ══════════════════════════════════════════════════════════════════════


def _make_styles():
    """يُعيد قاموس ستايلات openpyxl مشتركة."""
    import openpyxl  # noqa: F401 — imported for side-effects check

    shared = excel_table_styles()
    return {
        "header_font": shared.header_font,
        "header_fill": shared.header_fill,
        "header_align": shared.header_align,
        "data_align": shared.data_align,
        "thin_border": shared.border,
        "alt_fill": shared.alt_fill,
        "note_font": xl_font(brand.TEXT_MUTED, size=9, italic=True),
        "note_fill": xl_fill(brand.STATUS_WARNING_BG),
    }


def _add_header_row(ws, styles, row_num, columns):
    """يرسم صف الرأس باللون الكستنائي."""
    for col_idx, (header, width) in enumerate(columns, start=1):
        cell = ws.cell(row=row_num, column=col_idx, value=header)
        cell.font = styles["header_font"]
        cell.fill = styles["header_fill"]
        cell.alignment = styles["header_align"]
        cell.border = styles["thin_border"]
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[row_num].height = 26


def _style_data_row(ws, styles, row_num, num_cols, is_alt=False):
    """يطبق ستايل على صف بيانات."""
    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=row_num, column=col_idx)
        cell.border = styles["thin_border"]
        cell.alignment = styles["data_align"]
        brand_cell(cell)
        if is_alt:
            cell.fill = styles["alt_fill"]
    ws.row_dimensions[row_num].height = 20


def _setup_workbook(sheet_title, school_name, report_title):
    """ينشئ Workbook بهوية المنصة (4 صفوف رأس)."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.sheet_view.rightToLeft = True

    styles = _make_styles()
    today_str = timezone.now().strftime("%Y/%m/%d")

    year = default_academic_year()

    # دعم get_column_letter ديناميكياً

    # الأعمدة ستُحدَّد لاحقاً — نمرر None مؤقتاً
    return wb, ws, styles, year, today_str


def _finalize_workbook(
    wb, ws, styles, num_cols, school_name, report_title, year, today_str, num_data_rows
):
    """يضيف الرأس الاحترافي، يُجمّد، ويُعدّ الطباعة."""
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    col_letter = get_column_letter(num_cols)

    # ── الصفوف الثلاثة الأولى للرأس ──────────────────────────────────
    ws.insert_rows(1, 3)

    add_excel_title_rows(
        ws,
        num_cols,
        school_name,
        f"{report_title}  —  السنة الدراسية {year}",
        f"وزارة التربية والتعليم والتعليم العالي — دولة قطر  |  {today_str}",
    )

    # الصف 4 هو الرأس (تم تعبئته قبل insert_rows → أصبح الصف 7 مؤقتاً، لذا نعيد الترتيب)
    # ملاحظة: لتجنب إعادة الترتيب، نضيف الرأس بعد insert_rows مباشرة

    # تجميد بعد الرأس
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{col_letter}4"

    # إعداد طباعة A4
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


def _wb_to_response(wb, filename):
    """يحوّل Workbook إلى HttpResponse جاهز للتنزيل."""
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ══════════════════════════════════════════════════════════════════════
# Views
# ══════════════════════════════════════════════════════════════════════


@login_required
@capability_required("students.import_export")
def student_import_export(request):
    """
    GET  → صفحة الاستيراد/التصدير
    POST → معالجة ملف الاستيراد
    """

    school = request.user.get_school()
    year = academic_year_for_school(school)

    ctx = {
        "school": school,
        "year": year,
        "subtitle": f"إدارة بيانات الطلاب عبر ملفات Excel — {year}",
        "total_students": count_active_students(school),
        "import_result": None,
    }

    if request.method != "POST":
        return render(request, "core/student_import_export.html", ctx)

    # ── POST: استيراد الملف ──────────────────────────────────────────
    uploaded_file = request.FILES.get("student_file")
    if not uploaded_file:
        ctx["import_error"] = "لم يتم اختيار ملف."
        return render(request, "core/student_import_export.html", ctx)

    if not uploaded_file.name.endswith((".xlsx", ".xls")):
        ctx["import_error"] = "يُقبل ملف Excel فقط (.xlsx أو .xls)."
        return render(request, "core/student_import_export.html", ctx)

    try:
        result = process_student_import(uploaded_file, school, year)
        ctx["import_result"] = result
        ctx.update(import_result_context(request.user, school, result))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.exception("فشل استيراد الطلاب")
        ctx["import_error"] = f"خطأ في قراءة الملف: {exc}"

    return render(request, "core/student_import_export.html", ctx)


@login_required
@capability_required("students.import_export")
def student_export_excel(request):
    """
    GET → تنزيل ملف Excel بكل بيانات الطلاب في المدرسة.
    الأعمدة: الرقم الشخصي | الاسم | الصف | الشعبة | الجوال | البريد

    الرقم الشخصيّ: مطابقةٌ وزاريّة — كامل. أعمدتُه أعمدةُ قالب الاستيراد
    نفسُها (`EXPORT_COLUMNS` رأسُ `TEMPLATE_COLUMNS`)، و`students_import` يطابق
    الصفَّ على الرقم (`_upsert_user`) — فرقمٌ مستورٌ يقطع الدورةَ. والثمنُ
    تدقيقٌ برايةِ «رقمٌ كامل» (قرار المالك 2026-09-14).
    """

    from core.models import Membership, Role, StudentEnrollment

    school = request.user.get_school()
    year = academic_year_for_school(school)

    if not school:
        return HttpResponse("المدرسة غير محددة", status=400)

    student_role = Role.objects.filter(name="student").first()
    if not student_role:
        return HttpResponse("دور الطالب غير موجود", status=400)

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
        f"وزارة التربية والتعليم والتعليم العالي — دولة قطر  |  {today_str}",
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

        ws.cell(row=row_num, column=1, value=st.national_id or "")
        ws.cell(row=row_num, column=2, value=st.full_name)
        ws.cell(row=row_num, column=3, value=grade_display)
        ws.cell(row=row_num, column=4, value=section_display)
        ws.cell(row=row_num, column=5, value=st.get_phone_decrypted() or "")
        ws.cell(row=row_num, column=6, value=st.email or "")

        _style_data_row(ws, styles, row_num, num_cols, idx % 2 == 0)

    num_data_rows = len(memberships)

    # ── تجميد + فلاتر ────────────────────────────────────────────────
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

    from core.audit_export import log_export

    log_export(
        request,
        "core.students_xlsx",
        rows=num_data_rows,
        full_national_id=True,
        object_repr=f"كشف الطلاب الكامل Excel — {year}",
    )
    filename = f"طلاب_{school.name}_{year}_{today_str.replace('/', '-')}.xlsx"
    return _wb_to_response(wb, filename)


@login_required
@capability_required("students.import_export")
def student_import_template(request):
    """
    GET → تنزيل قالب Excel فارغ مع تعليمات الاستيراد.
    """
    import openpyxl
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "استيراد الطلاب"
    ws.sheet_view.rightToLeft = True

    styles = _make_styles()
    today_str = timezone.now().strftime("%Y/%m/%d")

    num_cols = len(TEMPLATE_COLUMNS)
    col_letter = get_column_letter(num_cols)

    # ── صف 1: تعليمات ──────────────────────────────────────────────
    ws.merge_cells(f"A1:{col_letter}1")
    c = ws["A1"]
    c.value = (
        "تعليمات: لا تحذف هذا الصف — ابدأ البيانات من الصف الثالث — "
        "الحقول الإلزامية: الرقم الشخصي + الاسم الكامل — "
        "الصفوف المقبولة: G7 G8 G9 G10 G11 G12 — "
        "كلمة المرور الافتراضية = الرقم الشخصي"
    )
    c.font = styles["note_font"]
    c.fill = styles["note_fill"]
    c.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 40

    # ── صف 2: رأس الأعمدة ──────────────────────────────────────────
    _add_header_row(ws, styles, 2, TEMPLATE_COLUMNS)

    # ── صفوف نموذجية (مثال) ─────────────────────────────────────────
    examples = [
        (
            "12345678",
            "محمد أحمد العلي",
            "G9",
            "أ",
            "+97455000001",
            "student@example.com",
            "87654321",
            "أحمد محمد العلي",
            "+97455000002",
            "parent@example.com",
            "father",
        ),
        (
            "12345679",
            "علي محمد السيد",
            "G10",
            "ب",
            "+97455000003",
            "",
            "87654322",
            "محمد سيد الأمين",
            "+97455000004",
            "",
            "father",
        ),
    ]
    for idx, row_data in enumerate(examples, start=3):
        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=idx, column=col_idx, value=val)
            cell.border = styles["thin_border"]
            cell.alignment = styles["data_align"]
            # تمييز لوني خفيف للأمثلة
            cell.fill = xl_fill(brand.STATUS_INFO_BG)
            cell.font = xl_font(brand.STATUS_INFO_FG, italic=True)
        ws.row_dimensions[idx].height = 20

    # ── تجميد الصف 2 ────────────────────────────────────────────────
    ws.freeze_panes = "A3"

    # ── إعداد طباعة ─────────────────────────────────────────────────
    ws.page_setup.paperSize = 9
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = 0.4
    ws.page_margins.right = 0.4
    ws.page_margins.top = 0.4
    ws.page_margins.bottom = 0.4

    from core.audit_export import log_export

    # قالبٌ فارغٌ بأمثلةٍ مصطنعة — لا بياناتٍ فيه، ويُدقَّق كأيّ ملفٍّ يخرج.
    log_export(request, "core.students_import_template_xlsx", rows=0)
    return _wb_to_response(wb, "قالب_استيراد_الطلاب.xlsx")
