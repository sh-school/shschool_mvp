"""التقرير السلوكي اليومي: صفحةٌ بتاريخ يوم، ومرشِّحا الجناح والصفّ، وتصديرُ PDF وExcel (W-20261107-004).

القدرةُ القائمةُ `behavior.statistics` بنطاقها لا قدرةٌ جديدة، والنطاقُ في `behavior.selectors.daily_infractions`.
والملفّان يُبنيان من الصفوف المعروضة نفسِها فيتطابقان مع الشاشة عدداً وترتيباً، ويكتب كلٌّ منهما سطرَ تدقيقٍ بلا نصّ الوصف.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.utils import timezone

from behavior.selectors import daily_infractions
from core.audit_export import log_export
from core.capabilities import capability_required
from core.export_utils import excel_to_response, generate_export_filename
from core.pdf_utils import content_disposition


def _requested_day(request) -> dt.date:
    """اليومُ من `?date=` — والافتراضُ اليومُ، وقيمةٌ غيرُ صالحة تعود إليه لا خطأً."""
    try:
        return dt.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        return timezone.localdate()


def _report(request):
    day = _requested_day(request)
    data = daily_infractions(
        request,
        request.school,
        day,
        wing_id=request.GET.get("wing", "").strip(),
        grade=request.GET.get("grade", "").strip(),
    )
    return day, data


def _filters_label(data) -> str:
    """وصفُ المرشِّحين المطبَّقين لترويسة PDF (اسمُ الجناح والصفّ لا معرّفاتُهما)."""
    parts = [w.name for w in data["wings"] if str(w.pk) == data["wing_id"]]
    parts += [label for code, label in data["grades"] if code == data["grade"]]
    return " · ".join(parts)


@login_required
@capability_required("behavior.statistics")
def daily_report(request):
    from django.shortcuts import render

    day, data = _report(request)
    count = len(data["rows"])
    query = urlencode(
        {"date": day.isoformat(), "wing": data["wing_id"], "grade": data["grade"]},
    )
    return render(
        request,
        "behavior/daily_report.html",
        {
            "rows": data["rows"],
            "subtitle": f"{day:%Y-%m-%d} · يوم الحصّة إن وُجدت وإلا يوم التسجيل",
            "count_label": f"{count} مخالفة",
            "day_value": day.isoformat(),
            "wing_value": data["wing_id"],
            "grade_value": data["grade"],
            "wing_choices": [(str(w.pk), w.name) for w in data["wings"]],
            "grade_choices": data["grades"],
            "export_query": query,
        },
    )


def _audit(request, kind: str, day: dt.date, count: int) -> None:
    """سطرُ التدقيق: نوعُ الملفّ ويومُه وعددُ صفوفه — لا وصفَ مخالفةٍ ولا رقماً شخصيّاً."""
    log_export(
        request,
        kind,
        rows=count,
        full_national_id=False,
        object_repr=f"التقرير السلوكي اليومي {day:%Y-%m-%d}",
    )


@login_required
@capability_required("behavior.statistics")
def daily_report_xlsx(request):
    from reports.export_builders import daily_behavior_workbook

    day, data = _report(request)
    wb = daily_behavior_workbook(request.school, data["rows"], day)
    _audit(request, "behavior.daily_xlsx", day, len(data["rows"]))
    return excel_to_response(
        wb, generate_export_filename("behavior", "daily", "xlsx"), school=request.school
    )


@login_required
@capability_required("behavior.statistics")
def daily_report_pdf(request):
    from django.http import HttpResponse

    from reports.export_builders import daily_behavior_pdf_bytes

    day, data = _report(request)
    content = daily_behavior_pdf_bytes(request.user, data["rows"], day, _filters_label(data))
    _audit(request, "behavior.daily_pdf", day, len(data["rows"]))
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition(
        generate_export_filename("behavior", "daily", "pdf"), True
    )
    return response
