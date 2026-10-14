"""ورقةُ الاتصال المطبوعة لمتابعة الغياب (W-20261013-017).

`render_contact_sheet(user, date)` ترجع بايتات PDF لغائبي اليوم ضمن نطاق صاحب الطلب، مجموعةً بالصفّ:

- القدرةُ `operations.absence_followup_print` شرطٌ هنا قبل أيّ قراءة، والنطاقُ يحصره `followup_rows`
  (الجناحُ والقسم) فلا يظهر خارجَه أحد.
- رقمُ الوليّ وحدَه بلا اسمه ولا اسم الأمّ (D-431م)، وتوقيعٌ واحدٌ هو مشرف الجناح (D-385م).
- من استُلمت إجازتُه المرضيّة (آخرُ إجراءٍ حالتُه `sick_leave`) يُوسَم.
- كلُّ توليدٍ سطرُ `AuditLog` بنوع الوثيقة وعدد الصفوف فقط — لا اسمَ ولا رقمَ ولا طالب.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string

from core.capabilities import has_capability
from core.export_utils import get_export_context_for
from core.models import AuditLog
from core.pdf_utils import render_pdf_bytes

PRINT = "operations.absence_followup_print"
TEMPLATE = "operations/absence_followup/print.html"
KIND = "operations.absence_followup_contact_sheet"


def _shown_rows(rows: list[dict], params: Any) -> list[dict]:
    """يطبّق تصفيةَ الشاشة وفرزَها (قائمةٌ بيضاء في الخدمة) — بلا `params` يبقى الكلُّ كما كان."""
    from operations.services.absence_followup import apply_view

    params = params or {}
    return apply_view(
        rows,
        grade=params.get("grade", ""),
        wing=params.get("wing", ""),
        followup=params.get("followup", ""),
        sort=params.get("sort", ""),
    )


def _groups(rows: list[dict]) -> list[dict]:
    """الصفوفُ مجموعةً بالصفّ بترتيب الاسم، وكلُّ سطرٍ بما يُطبع وحدَه."""
    by_class: dict[str, list[dict]] = {}
    grade_of: dict[str, str] = {}
    for row in rows:
        group = row.get("class_group")
        title = str(group) if group else "بلا صفّ"
        grade_of.setdefault(title, getattr(group, "grade", "") or "")
        action = row.get("action")
        by_class.setdefault(title, []).append(
            {
                "name": row["student"].full_name,
                "phone": " — ".join(row.get("phones") or []),
                "sick_leave": bool(action and action.status == "sick_leave"),
                "outcome": row["contact"].get_outcome_display() if row.get("contact") else "",
                "feedback": row.get("feedback") or "",
            }
        )
    out = []
    for title in sorted(by_class):
        items = sorted(by_class[title], key=lambda r: r["name"])
        for i, item in enumerate(items, 1):
            item["number"] = i
        out.append(
            {
                "title": title,
                "grade": grade_of.get(title, ""),
                "rows": items,
                "leave_count": sum(1 for r in items if r["sick_leave"]),
            }
        )
    return out


def render_contact_sheet(user: Any, date: dt.date, params: Any = None) -> bytes:
    """PDF ورقة الاتصال ليوم `date` بما تعرضه الشاشةُ بعد التصفية. بلا قدرة الطباعة = `PermissionDenied`."""
    if not has_capability(user, PRINT):
        raise PermissionDenied("لا صلاحيةَ لطباعة ورقة الاتصال.")
    from operations.services.absence_followup import followup_rows

    groups = _groups(_shown_rows(followup_rows(user, date), params))
    ctx = get_export_context_for(user, "ورقة الاتصال لمتابعة الغياب")
    ctx.update(
        {
            "school": user.get_school(),
            "groups": groups,
            "day": date,
            "signatory": "",
        }
    )
    pdf = render_pdf_bytes(render_to_string(TEMPLATE, ctx))
    AuditLog.log(
        user=user,
        action="export",
        model_name="other",
        object_id="",
        object_repr=KIND,
        changes={
            "kind": KIND,
            "rows": sum(len(g["rows"]) for g in groups),
            "full_national_id": False,
        },
        school=ctx["school"],
    )
    return pdf


def build_followup_pdf(school: Any, user: Any, params: Any) -> Any:
    """بنّاءُ سجلّ التصدير لكشف المتابعة PDF (`operations.absence_followup_pdf`): بلا `request`، والنطاقُ من `followup_rows`."""
    from django.utils.formats import date_format

    from core.export_utils import generate_export_filename
    from core.exports.registry import ExportResult
    from core.pdf_utils import render_pdf_bytes
    from operations.models import AbsenceActionLog, AbsenceContactLog
    from operations.services.absence_followup import followup_rows
    from wings.register import footer_lines

    if not has_capability(user, PRINT):
        raise PermissionDenied("لا صلاحيةَ لطباعة كشف المتابعة.")
    try:
        day = dt.date.fromisoformat(params.get("date") or "")
    except ValueError:
        day = dt.date.today()
    rows = _shown_rows(followup_rows(user, day), params)
    ctx = get_export_context_for(user, f"متابعة الغياب — {date_format(day, 'd/m/Y')}")
    ctx.update(
        school=school,
        footer=footer_lines(school),
        rows=rows,
        day=day,
        orient="landscape",
        outcomes=dict(AbsenceContactLog.OUTCOMES),
        statuses=dict(AbsenceActionLog.STATUSES),
        can_feedback=has_capability(user, "operations.absence_followup_feedback"),
        can_followup=has_capability(user, "operations.absence_followup_followup"),
    )
    pdf = render_pdf_bytes(render_to_string("operations/absence_followup_print.html", ctx))
    return ExportResult(
        content=pdf,
        content_type="application/pdf",
        filename=generate_export_filename("operations", "absence-followup", "pdf"),
        rows=len(rows),
    )


def followup_sheet_response(
    request: Any,
    day: dt.date,
    rows: list[dict],
    wing_bound: bool,
    can_feedback: bool,
    can_followup: bool = False,
):
    """كشفُ المتابعة: `?format=pdf` مهمّةُ تصديرٍ عبر السجلّ المركزيّ، وإلّا معاينةٌ داخل المنصّة بإطارٍ (`embed=1` هو الوثيقةُ نفسُها)."""
    from urllib.parse import urlencode

    from django.shortcuts import render
    from django.urls import reverse
    from django.utils.formats import date_format

    from core.export_utils import get_export_context
    from core.exports.services import respond_export
    from operations.models import AbsenceActionLog, AbsenceContactLog
    from wings.register import footer_lines

    if request.GET.get("format") == "pdf":
        return respond_export(request, "operations.absence_followup_pdf")
    title = f"متابعة الغياب — {date_format(day, 'd/m/Y')}"
    # مفاتيحُ التصفية والفرز تُحمَل إلى التنزيل والرجوع فيبقى المطبوعُ على ما عُرض.
    shown = {k: request.GET[k] for k in ("grade", "wing", "followup", "sort") if request.GET.get(k)}
    if request.GET.get("embed") != "1":
        return render(
            request,
            "operations/absence_followup/viewer.html",
            {
                "report_title": title,
                "subtitle": f"{request.school.name} · {date_format(day, 'l')}",
                "rows": rows,
                "can_feedback": can_feedback,
                "can_followup": can_followup,
                "pdf_url": f"{request.path}?{urlencode({'date': day.isoformat(), 'format': 'pdf', **shown})}",
                "back_url": f"{reverse('daily_report')}?{urlencode({'date': day.isoformat(), **shown})}",
            },
        )
    ctx = get_export_context(request, title)
    ctx.update(
        school=request.school,
        footer=footer_lines(request.school),
        rows=rows,
        day=day,
        wing_bound=wing_bound,
        orient="landscape",
        outcomes=dict(AbsenceContactLog.OUTCOMES),
        statuses=dict(AbsenceActionLog.STATUSES),
        can_feedback=can_feedback,
        can_followup=can_followup,
        for_screen=True,
    )
    return render(request, "operations/absence_followup_print.html", ctx)
