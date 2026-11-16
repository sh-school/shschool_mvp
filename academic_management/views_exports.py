"""تصديرُ التقارير الأكاديميّة الأربعة Excel وPDF على عقد التصدير المركزيّ (W-20261109-007).

الرابطُ يحمل المعاملاتِ كلَّها كما على الشاشة؛ والقدرةُ يفحصها `respond_export` من السجلّ (`academic.reports_school`).
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse

from core.exports.services import respond_export

from .export_tables import ACADEMIC_TABLES, pdf_kind


@login_required
def report_xlsx(request: HttpRequest, report: str) -> HttpResponse:
    table = ACADEMIC_TABLES.get(report)
    if table is None:
        raise Http404
    return respond_export(request, table.kind, params=request.GET.copy())


@login_required
def report_pdf(request: HttpRequest, report: str) -> HttpResponse:
    if report not in ACADEMIC_TABLES:
        raise Http404
    return respond_export(request, pdf_kind(report), params=request.GET.copy())
