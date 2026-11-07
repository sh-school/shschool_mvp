"""تقرير السلوك اليوميّ: صفحةٌ بتاريخ يومٍ ومرشّحَي الجناح والصفّ وتصديرُ PDF وExcel (W-20261107-010).

القدرةُ القائمةُ `behavior.statistics` بنطاقها (المعلّمُ لطلبته، والمقيَّدُ بجناحه لجناحه، والقيادةُ للمدرسة) بلا قدرةٍ جديدة.
والتصديرُ بنّاءاتٌ في سجلّ التصدير المركزيّ (`reports/export_builders.py`) يبنيها العاملُ من المعاملات نفسِها.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required
from core.exports.services import respond_export
from core.models import ClassGroup
from wings.scope import student_scope_for

from .selectors import daily_filters, daily_infractions, daily_wing_options

#: امتدادُ الملفّ في الرابط ← نوعُه في سجلّ التصدير (`behavior/apps.py`).
EXPORT_KINDS = {"pdf": "behavior.daily_pdf", "xlsx": "behavior.daily_xlsx"}


def _query(day, wing_id, grade) -> str:
    """استعلامُ المرشّحات كما يُمرَّر للتصدير — اليومُ صريحٌ كي لا يتبدّل إن عبر العاملُ منتصفَ الليل."""
    pairs = {"date": day.isoformat(), "wing": str(wing_id) if wing_id else "", "grade": grade}
    return urlencode({k: v for k, v in pairs.items() if v})


@login_required
@capability_required("behavior.statistics")
def daily_report(request):
    scope = student_scope_for(request)
    school = request.school
    year = academic_year_for_school(school)
    day, wing_id, grade = daily_filters(request.GET, scope)
    rows = daily_infractions(
        school, request.user, day, scope=scope, year=year, wing_id=wing_id, grade=grade
    )
    return render(
        request,
        "behavior/daily_report.html",
        {
            "day": day,
            "rows": rows,
            "wing_id": str(wing_id) if wing_id else "",
            "grade": grade,
            "wings": list(daily_wing_options(school, scope, year)),
            "grades": ClassGroup.GRADES,
            "export_query": _query(day, wing_id, grade),
        },
    )


@login_required
@capability_required("behavior.statistics")
def daily_export(request, fmt):
    kind = EXPORT_KINDS.get(fmt)
    if kind is None:
        raise Http404
    day, wing_id, grade = daily_filters(request.GET, student_scope_for(request))
    params = request.GET.copy()
    params["date"] = day.isoformat()
    return respond_export(request, kind, params=params)
