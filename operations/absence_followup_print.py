"""تصديرُ كشف متابعة الغياب: PDF وExcel بما تعرضه الشاشةُ بعد الترشيح حرفياً (W-20261020-005).

- القدرةُ `operations.absence_followup_print` شرطٌ قبل أيّ قراءة، والنطاقُ يحصره `followup_rows`
  (الجناحُ والقسم) فلا يظهر خارجَه أحد.
- رقمُ الوليّ وحدَه بلا اسمه ولا اسم الأمّ (D-431م).
- ورقةُ الاتصال المستقلّة أُلغيت (قرار المالك): رابطُها القديم يحوَّل إلى صفحة العرض.
- التدقيقُ في العرض: العددُ لا الأسماء.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string

from core.capabilities import has_capability
from core.export_utils import get_export_context_for
from core.pdf_utils import render_pdf_bytes

PRINT = "operations.absence_followup_print"


def shown_rows_of(rows: list[dict], params: Any) -> list[dict]:
    """يطبّق تصفيةَ الشاشة وفرزَها (قائمةٌ بيضاء في الخدمة) — بلا `params` يبقى الكلُّ كما كان."""
    from operations.services.absence_followup import apply_view

    params = params or {}
    return apply_view(
        rows,
        grade=params.get("grade", ""),
        wing=params.get("wing", ""),
        search=(params.get("q") or "")[:60],
        followup=params.get("followup", ""),
        sort=params.get("sort", ""),
    )


def by_wing(rows: list[dict]) -> list[dict]:
    """يجمّع الصفوفَ بترتيب الجناح (كالعقد المركزيّ) فالصفّ فالشعبة فالاسم، وكلُّ صفٍّ يحمل `wing_title` لعنوان المجموعة."""

    def key(row: dict) -> tuple:
        group = row.get("class_group")
        wing = getattr(group, "wing", None)
        return (
            (wing.order or 98) if wing else 99,
            getattr(group, "grade", ""),
            getattr(group, "section", ""),
            row["student"].full_name,
        )

    ordered = sorted(rows, key=key)
    for row in ordered:
        wing = getattr(row.get("class_group"), "wing", None)
        row["wing_title"] = wing.name if wing else "خارج الأجنحة"
    return ordered


def action_text(row: dict) -> str:
    action = row.get("action")
    if not action:
        return ""
    return action.get_action_kind_display() + (f" — {action.note}" if action.note else "")


def followed_text(row: dict) -> str:
    if not row.get("followed_at"):
        return ""
    return f"{row['followed_at']:%d/%m/%Y %H:%M} · {row.get('followed_by', '')}"


def build_followup_xlsx(school: Any, user: Any, params: Any) -> Any:
    """Excel مباشر على عقد الجداول: أعمدةُ الصفحة المعروضة وصفوفُها بعد الترشيح، مرقَّمةً ومفروزةً بالجناح."""
    from core.exports.contract import build_table_xlsx
    from operations.export_tables import table_for

    if not has_capability(user, PRINT):
        raise PermissionDenied("لا صلاحيةَ لتصدير كشف المتابعة.")
    page, _ = sheet_options(params)
    return build_table_xlsx(table_for(user, page), school, user, params)


#: الافتراضيّ: أفقيٌّ في التواصل (أعمدةٌ كثيرة) وعموديٌّ في الإجراءات (قرارُ المالك 2026-10-17).
DEFAULT_ORIENT = {
    "contact": "landscape",
    "actions": "landscape",
}  # D-449م: «الإجراءات» أفقيّة كالقوائم
PAGES = tuple(DEFAULT_ORIENT)


def sheet_options(params: Any) -> tuple[str, str]:
    """(الصفحة، الاتّجاه) من الاستعلام بقائمةٍ بيضاء — قيمةٌ غريبةٌ ترجع إلى الافتراضيّ."""
    page = params.get("page") if params.get("page") in PAGES else "contact"
    orient = params.get("orient")
    return page, orient if orient in ("portrait", "landscape") else DEFAULT_ORIENT[page]


def build_followup_pdf(school: Any, user: Any, params: Any) -> Any:
    """PDF كشف الصفحة المطلوبة (`page`) بالاتّجاه المطلوب (`orient`): القدرةُ أوّلاً والنطاقُ من `followup_rows`."""
    from django.utils.formats import date_format

    from core.export_utils import generate_export_filename
    from core.exports.registry import ExportResult
    from operations.export_tables import day_of, shown_rows
    from operations.models import AbsenceActionLog, AbsenceContactLog
    from wings.register import footer_lines

    if not has_capability(user, PRINT):
        raise PermissionDenied("لا صلاحيةَ لطباعة كشف المتابعة.")
    day = day_of(params)
    page, orient = sheet_options(params)
    # المحدِّدُ نفسُه الذي تقرأ به الشاشةُ وExcel: نطاقُ الدور والترشيحُ كاملاً وفرزُ الجناح.
    rows = shown_rows(user, params)
    name = "التواصل مع أولياء الأمور" if page == "contact" else "متابعة إجراءات الغياب"
    ctx = get_export_context_for(user, f"{name} — {date_format(day, 'd/m/Y')}")
    ctx.update(
        school=school,
        footer=footer_lines(school),
        rows=rows,
        day=day,
        page=page,
        orient=orient,
        outcomes=dict(AbsenceContactLog.OUTCOMES),
        statuses=dict(AbsenceActionLog.STATUSES),
        can_feedback=has_capability(user, "operations.absence_followup_feedback"),
        issuer=user.full_name,
        issued_at=dt.datetime.now(),
    )
    pdf = render_pdf_bytes(render_to_string("operations/absence_followup_print.html", ctx))
    return ExportResult(
        content=pdf,
        content_type="application/pdf",
        filename=generate_export_filename("operations", f"absence-{page}", "pdf"),
        rows=len(rows),
    )


def followup_viewer_response(request: Any, day: dt.date) -> Any:
    """صفحةُ المنصّة بإطار PDF: رجوعٌ وتحميلٌ وقائمةُ «عمودي / أفقي» — بلا زرّ مشاركة (قرار المالك 2026-10-17)."""
    from urllib.parse import urlencode

    from django.shortcuts import render
    from django.urls import reverse
    from django.utils.formats import date_format

    page, orient = sheet_options(request.GET)
    shown = {
        k: request.GET[k] for k in ("grade", "wing", "followup", "sort", "q") if request.GET.get(k)
    }
    base = {"date": day.isoformat(), "page": page, "orient": orient, **shown}
    name = "التواصل مع أولياء الأمور" if page == "contact" else "متابعة إجراءات الغياب"
    back = "daily_report" if page == "contact" else "absence_actions"
    return render(
        request,
        "operations/absence_followup/viewer.html",
        {
            "report_title": f"{name} — {date_format(day, 'd/m/Y')}",
            "subtitle": f"{request.school.name} · {date_format(day, 'l')}",
            "orient": orient,
            "keep": {k: v for k, v in base.items() if k != "orient"},
            "frame_url": f"{reverse('absence_followup_pdf')}?{urlencode(base)}",
            "pdf_url": f"{reverse('absence_followup_pdf')}?{urlencode({**base, 'download': 1})}",
            "back_url": f"{reverse(back)}?{urlencode({'date': day.isoformat(), **shown})}",
        },
    )
