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

from .selectors import class_certificates_context, paper_size


def build_class_certificates_pdf(school: Any, user: Any, params: Any) -> ExportResult:
    """شهادةٌ لكلّ طالبٍ في الفصل على صفحةٍ — كان 2.9ث متزامناً (قياس 2026-09-26).

    الرقمُ الشخصيُّ مستورٌ في القالب (كشفٌ جماعيّ: ملفٌّ واحدٌ لفصلٍ كامل)، والشهادةُ الفرديّةُ وحدَها تحمله كاملاً.
    """
    from core.pdf_utils import render_pdf_bytes

    if not user.is_admin():  # كما في الـview؛ القدرةُ وحدَها يفحصها العاملُ ثانيةً
        raise PermissionDenied
    class_grp = ClassGroup.objects.get(id=params["class_id"], school=school)
    year = params.get("year") or academic_year_for_school(user.get_school())
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
