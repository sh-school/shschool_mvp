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


#: أعمدةُ التقرير السلوكيّ اليوميّ بترتيبها في Excel وPDF — بلا رقمٍ شخصيٍّ ولا وليّ أمر ولا نصّ وصف.
DAILY_BEHAVIOR_COLUMNS = (
    ("م", 6),
    ("الطالب", 28),
    ("الشعبة", 10),
    ("المخالفة", 34),
    ("الدرجة", 20),
    ("الخطوة", 22),
    ("الراصد", 22),
)


def _daily_behavior_cells(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """صفوفُ التصدير من الصفوف المعروضة نفسِها — فيتطابق الملفّان مع الشاشة عدداً وترتيباً."""
    return [
        (n, r["student"], r["class_label"], r["violation"], r["level"], r["step"], r["reporter"])
        for n, r in enumerate(rows, start=1)
    ]


def daily_behavior_workbook(school: Any, rows: list[dict[str, Any]], day: Any) -> Any:
    """مصنَّفُ Excel للتقرير السلوكيّ اليوميّ (الراصدُ والخطوةُ والدرجةُ بلا نصّ الوصف)."""
    from .services import AcademicReportsExcel

    return AcademicReportsExcel._build(
        "السلوك اليومي",
        f"التقرير السلوكي اليومي — {day:%Y-%m-%d}",
        list(DAILY_BEHAVIOR_COLUMNS),
        _daily_behavior_cells(rows),
        school,
    )


def daily_behavior_pdf_bytes(
    user: Any, rows: list[dict[str, Any]], day: Any, filters_label: str = ""
) -> bytes:
    """PDF التقرير السلوكيّ اليوميّ بالقالب `behavior/daily_report_pdf.html`."""
    from core.export_utils import get_export_context_for, get_pdf_footer_html, get_pdf_header_html
    from core.pdf_utils import render_pdf_bytes

    ctx = get_export_context_for(user, "التقرير السلوكي اليومي")
    html = render_to_string(
        "behavior/daily_report_pdf.html",
        {
            "rows": _daily_behavior_cells(rows),
            "columns": [name for name, _width in DAILY_BEHAVIOR_COLUMNS],
            "day": day,
            "filters_label": filters_label,
            "pdf_header": get_pdf_header_html(ctx),
            "pdf_footer": get_pdf_footer_html(ctx),
            "for_pdf": True,
            **ctx,
        },
    )
    return render_pdf_bytes(html, paper_size="A4")
