"""بنّاءُ «كشف درجات المادّة» Excel لسجلّ التصدير المركزيّ (`core.exports.registry`) — W-20261021-011.

دالّةٌ نقيّةٌ بلا `request`: تعمل في عاملِ Celery. الرقمُ الشخصيُّ مستورٌ (كشفُ فصلٍ جماعيّ لا يعود بالرفع؛ رفعُ الدرجات
له قالبُه في `staging`). تُسجَّل من `AssessmentsConfig.ready()`.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from core import brand
from core.excel_safety import safe_cell
from core.export_utils import apply_print_footer, excel_table_styles, xl_font
from core.exports.registry import ExportResult
from core.models import StudentEnrollment
from core.privacy import mask_national_id

from .models import AssessmentPackage, StudentSubjectResult, SubjectClassSetup
from .services import GradeService


def build_gradebook_xlsx(school: Any, user: Any, params: Any) -> ExportResult:
    setup = SubjectClassSetup.objects.get(id=params["setup_id"], school=school)
    if (
        not user.is_admin() and setup.teacher != user
    ):  # كما في الـview؛ القدرةُ وحدَها يفحصها العاملُ ثانيةً
        raise PermissionDenied
    semester = params.get("semester", "S1")

    enrollments = (
        StudentEnrollment.objects.filter(class_group=setup.class_group, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    packages = (
        AssessmentPackage.objects.filter(setup=setup, semester=semester, is_active=True)
        .prefetch_related("assessments")
        .order_by("package_type")
    )

    # ── بناء الـ Workbook ──────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = "كشف الدرجات"
    ws.sheet_view.rightToLeft = True

    # ألوان
    table = excel_table_styles()
    HEADER_FILL = table.header_fill
    HEADER_FONT = table.header_font
    ALT_FILL = table.alt_fill
    THIN_BORDER = table.border
    CENTER = table.data_align
    RIGHT_ALIGN = Alignment(horizontal="right", vertical="center")

    pkg_labels = {
        "P1": "الباقة 1",
        "P2": "الباقة 2",
        "P3": "الباقة 3",
        "P4": "الباقة 4",
    }
    sem_labels = {"S1": "الفصل الأول (40)", "S2": "الفصل الثاني (60)"}

    # ── السطر 1: عنوان ─────────────────────────────────────
    title = (
        f"كشف درجات | {setup.subject.name_ar} | "
        f"{setup.class_group} | {sem_labels.get(semester, semester)} | "
        f"{setup.academic_year}"
    )
    ws.merge_cells("A1:H1")
    safe_cell(ws, 1, 1, title)
    ws["A1"].font = xl_font(brand.MAROON, size=13, bold=True)
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 28

    # ── السطر 2: رؤوس الأعمدة ──────────────────────────────
    pkg_list = list(packages)
    headers = (
        ["م", "اسم الطالب", "الرقم الشخصي"]
        + [pkg_labels.get(p.package_type, p.package_type) for p in pkg_list]
        + ["مجموع الفصل", "الحالة"]
    )

    for col_idx, header in enumerate(headers, start=1):
        cell = safe_cell(ws, row=2, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = THIN_BORDER

    ws.row_dimensions[2].height = 22

    # ── Pre-fetch semester results + package scores to avoid N+1 queries ──
    student_ids = [enr.student_id for enr in enrollments]
    sem_results_map = {
        r.student_id: r
        for r in StudentSubjectResult.objects.filter(
            student_id__in=student_ids, setup=setup, semester=semester
        )
    }
    batch_scores = GradeService.calc_package_scores_batch(student_ids, pkg_list)

    # ── البيانات ────────────────────────────────────────────
    for row_idx, enr in enumerate(enrollments, start=1):
        student = enr.student
        excel_row = row_idx + 2
        fill = ALT_FILL if row_idx % 2 == 0 else None

        pkg_scores = {
            p.package_type: batch_scores.get((student.id, p.package_type)) for p in pkg_list
        }

        sem_result = sem_results_map.get(student.id)
        if sem_result:
            total = float(sem_result.total) if sem_result.total is not None else ""
            status = (
                "ناجح ✓"
                if (sem_result.total or 0) >= (sem_result.semester_max * Decimal("0.5"))
                else "راسب ✗"
            )
        else:
            total, status = "", "—"

        # الرقم الشخصيّ: مستور — سجلُّ درجاتِ فصلٍ كشفٌ جماعيّ لا يعود بالرفع
        # (رفعُ الدرجات له قالبُه في `staging`).
        row_data = (
            [row_idx, student.full_name, mask_national_id(student.national_id)]
            + [float(pkg_scores.get(p.package_type) or 0) for p in pkg_list]
            + [total, status]
        )

        for col_idx, value in enumerate(row_data, start=1):
            cell = safe_cell(ws, row=excel_row, column=col_idx, value=value)
            cell.border = THIN_BORDER
            cell.font = table.cell_font
            cell.alignment = CENTER if col_idx != 2 else RIGHT_ALIGN
            if fill:
                cell.fill = fill

    # ── عرض الأعمدة ────────────────────────────────────────
    col_widths = [5, 30, 18] + [12] * len(pkg_list) + [14, 10]
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # ── تجميد الصفوف الأولى ────────────────────────────────
    ws.freeze_panes = "A3"

    apply_print_footer(wb, school)  # رؤيةُ الوزارة في ذيل الطباعة (قرار المالك 2026-09-27)
    buf = io.BytesIO()
    wb.save(buf)
    filename = f"gradebook_{setup.subject.name_ar}_{setup.class_group}_{semester}.xlsx".replace(
        " ", "_"
    ).replace("/", "-")
    return ExportResult(
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename,
        rows=len(enrollments),
        full_national_id=False,
        object_id=str(setup.pk),
    )
