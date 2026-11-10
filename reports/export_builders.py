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


def _behavior_statistics_sections(data: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """أقسامُ إحصاء السلوك (عنوان، سطور) بترتيب الشاشة — لـPDF وExcel معاً؛ مجموعُ كلّ قسمٍ إجماليُّ المدّة."""
    from django.utils.formats import date_format

    monthly = [
        {"label": date_format(row["month"], "F Y"), "count": row["count"]}
        for row in data["monthly"]
    ]
    return [
        ("التوزيع بالدرجة", data["degree_rows"]),
        ("أكثر البنود", data["category_rows"]),
        ("التوزيع بالإجراء التأديبي", data["action_rows"]),
        ("التوزيع بخطوة الإجراء التصاعدي", data["step_rows"]),
        ("التوزيع بالجناح", data["wing_rows"]),
        ("التوزيع بالصف والشعبة", data["class_rows"]),
        ("التوزيع الشهري للعام", monthly),
    ]


def build_behavior_statistics_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """إحصاءُ السلوك PDF — الأرقامُ نفسُها من `behavior_statistics_data` (المصدر الواحد مع الشاشة وExcel)."""
    from behavior.services import behavior_statistics_data
    from core.export_utils import get_export_context_for, get_pdf_footer_html, get_pdf_header_html
    from core.pdf_utils import render_pdf_bytes

    data = behavior_statistics_data(school, user, params)
    ctx = get_export_context_for(user, "إحصاءات السلوك")
    html = render_to_string(
        "behavior/statistics_pdf.html",
        {
            **data,
            "sections": _behavior_statistics_sections(data),
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            "for_pdf": True,
            **ctx,
        },
    )
    return ExportResult(
        render_pdf_bytes(html, paper_size="A4"),
        "application/pdf",
        f"إحصاءات_سلوك_{data['period_label']}.pdf",
        rows=data["total"],
        full_national_id=False,
    )


# إحصاءُ السلوك PDF: خلفيٌّ بقدرة الإحصاء ونطاقها (W-20261107-014). يُسجَّل هنا عند أوّل استيرادٍ للبنّائين
# (تستورده `BehaviorConfig.ready()`) وExcel على عقد الجداول (`behavior.export_tables`).
def _register_behavior_statistics_exports() -> None:
    from core.exports import registry

    if registry.get("behavior.statistics_pdf") is None:
        registry.register(
            "behavior.statistics_pdf",
            build=build_behavior_statistics_pdf,
            capability="behavior.statistics",
        )


_register_behavior_statistics_exports()
