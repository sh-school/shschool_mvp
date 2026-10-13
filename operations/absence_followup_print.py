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


def _groups(rows: list[dict]) -> list[dict]:
    """الصفوفُ مجموعةً بالصفّ بترتيب الاسم، وكلُّ سطرٍ بما يُطبع وحدَه."""
    by_class: dict[str, list[dict]] = {}
    for row in rows:
        group = row.get("class_group")
        title = str(group) if group else "بلا صفّ"
        action = row.get("action")
        by_class.setdefault(title, []).append(
            {
                "name": row["student"].full_name,
                "phone": " — ".join(row.get("phones") or []),
                "sick_leave": bool(action and action.status == "sick_leave"),
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
                "rows": items,
                "leave_count": sum(1 for r in items if r["sick_leave"]),
            }
        )
    return out


def render_contact_sheet(user: Any, date: dt.date) -> bytes:
    """PDF ورقة الاتصال ليوم `date`. بلا قدرة الطباعة = `PermissionDenied`."""
    if not has_capability(user, PRINT):
        raise PermissionDenied("لا صلاحيةَ لطباعة ورقة الاتصال.")
    from operations.services.absence_followup import followup_rows

    groups = _groups(followup_rows(user, date))
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
