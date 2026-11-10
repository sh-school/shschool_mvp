"""كشفُ درجات المادّة على عقد التصدير المركزيّ (W-20261109-007): Excel وPDF من المحدِّد نفسِه.

طلبةُ الشعبة (قيدُهم النشط) بدرجات باقات الفصل المختار ومجموعِه وحالتِه؛ والعمودُ «م» وفرزُ الجناح والأعمدةُ المخفيّة من العقد.
الرقمُ الشخصيّ غيرُ موجودٍ في الملفّ (كشفٌ جماعيّ لا يعود بالرفع؛ رفعُ الدرجات له قالبُه في `staging`).
"""

from __future__ import annotations

from decimal import Decimal
from functools import partial
from typing import Any

from django.core.exceptions import PermissionDenied

from core.exports import registry
from core.exports.contract import Column, TableSpec, register_table

from .models import AssessmentPackage, StudentSubjectResult, SubjectClassSetup
from .services import GradeService

_PACKAGES = (
    ("P1", "الباقة 1"),
    ("P2", "الباقة 2"),
    ("P3", "الباقة 3"),
    ("P4", "الباقة 4"),
    ("AW", "الأعمال المستمرة"),
)


def gradebook_rows(user: Any, params: Any) -> list[dict[str, Any]]:
    """صفوفُ كشف الدرجات: المشرفُ العامُّ (مدير/مطوّر) أو معلّمُ الإعداد وحدَه — كما تفعل الشاشة."""
    setup = SubjectClassSetup.objects.select_related("class_group__wing").get(
        id=params["setup_id"], school=user.get_school()
    )
    if not user.is_admin() and setup.teacher != user:
        raise PermissionDenied
    semester = params.get("semester", "S1")
    enrollments = (
        setup.class_group.enrollments.filter(is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )
    packages = list(
        AssessmentPackage.objects.filter(setup=setup, semester=semester, is_active=True)
        .prefetch_related("assessments")
        .order_by("package_type")
    )
    student_ids = [enr.student_id for enr in enrollments]
    results = {
        r.student_id: r
        for r in StudentSubjectResult.objects.filter(
            student_id__in=student_ids, setup=setup, semester=semester
        )
    }
    scores = GradeService.calc_package_scores_batch(student_ids, packages)
    wing_order = getattr(setup.class_group.wing, "order", None)
    rows = []
    for enr in enrollments:
        result = results.get(enr.student_id)
        passed = bool(result) and (result.total or 0) >= result.semester_max * Decimal("0.5")
        row: dict[str, Any] = {
            "student": enr.student.full_name,
            "total": float(result.total) if result and result.total is not None else "",
            "status": ("ناجح ✓" if passed else "راسب ✗") if result else "—",
            "wing_order": wing_order,
        }
        for pkg in packages:
            row[f"pkg_{pkg.package_type}"] = float(
                scores.get((enr.student_id, pkg.package_type)) or 0
            )
        rows.append(row)
    return rows


GRADEBOOK_TABLE = TableSpec(
    kind="assessments.gradebook_xlsx",
    title="كشف الدرجات",
    capability="assessments.view_results",
    columns=(
        Column("student", "اسم الطالب"),
        *(Column(f"pkg_{key}", label) for key, label in _PACKAGES),
        Column("total", "مجموع الفصل"),
        Column("status", "الحالة"),
    ),
    rows_for=gradebook_rows,
    file_module="gradebook",
)
GRADEBOOK_PDF = "assessments.gradebook_pdf"


def register_assessment_tables() -> None:
    """يسجّل كشفَ الدرجات (Excel وPDF) في السجلّ المركزيّ — من `AssessmentsConfig.ready()`."""
    from student_affairs.export_builders import build_table_pdf

    register_table(GRADEBOOK_TABLE)
    registry.register(
        GRADEBOOK_PDF,
        build=partial(
            build_table_pdf,
            GRADEBOOK_TABLE,
            ("طلاب", "كشف درجات المادّة", "لا طلاب في هذه الشعبة"),
        ),
        capability=GRADEBOOK_TABLE.capability,
    )
