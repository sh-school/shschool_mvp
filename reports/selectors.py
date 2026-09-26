"""قراءاتُ التقارير التي يشترك فيها العرضُ وبنّاءُ التصدير — بلا `request` فتعمل في العامل كما في الطلب."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from core.models import StudentEnrollment

from .services import ReportDataService


def paper_size(params: Any) -> str:
    """مقاسُ الورق من معاملات الرابط: A4 أو A3 وما سواهما A4."""
    paper = params.get("paper", "A4").upper()
    return paper if paper in {"A3", "A4"} else "A4"


def set_final_status(ctx: dict) -> None:
    """يضيف `final_status` و`status_tone` إلى السياق.

    كان يضع لوناً سداسيّاً (`status_color`) يُكتب في `style=` الشهادة — وأحدُها
    أخضرُ لا رمزَ له في الهويّة. والنغمةُ اسمٌ تقرؤه الشهادةُ صنفاً
    (`cert-status is-success`) يأخذ ألوانَه من `brand_color`.
    """
    if ctx["failed"] == 0 and ctx["passed"] > 0:
        ctx.update(final_status="ناجح", status_tone="success")
    elif ctx["failed"] > 0:
        ctx.update(final_status="راسب", status_tone="danger")
    else:
        ctx.update(final_status="غير مكتمل", status_tone="warning")


def class_certificates_context(school: Any, class_grp: Any, year: str, paper: str) -> dict:
    """سياقُ «شهادات الفصل»: تقريرُ كلّ طالبٍ مقيَّدٍ فعّالٍ مرتَّباً بالاسم — يُعرض معاينةً أو يُحوَّل PDF."""
    enrollments = (
        StudentEnrollment.objects.filter(class_group=class_grp, is_active=True)
        .select_related("student")
        .order_by("student__full_name")
    )

    students_ctx = []
    for enr in enrollments:
        ctx = ReportDataService.get_student_report(enr.student, school, year)
        set_final_status(ctx)
        students_ctx.append(ctx)

    return {
        "students_ctx": students_ctx,
        "class_group": class_grp,
        "school": school,
        "year": year,
        "print_date": timezone.now().date(),
        "paper_size": paper,
    }
