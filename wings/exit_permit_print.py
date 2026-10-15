"""استمارةُ إذن الخروج PDF للحارس — نصُّها كلُّه من `exit_permit_form` (W-20261005-010).

لا يُطبع إلا إذنٌ **معتمَد** (حضورُ الوليّ مسجَّل). وكلُّ طباعةٍ سطرُ `AuditLog` بالمعرّف المقنَّع، بلا اسمٍ ولا رقم.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from core.audit_repr import masked_repr
from core.export_utils import get_export_context_for
from core.models import AuditLog
from core.pdf_utils import render_pdf_bytes

from . import exit_permit_form as form
from .exit_permit import low_periods

TEMPLATE = "wings/pdf/exit_permit.html"
KIND = "wings.exit_permit_form"


def form_context(permit: Any) -> dict:
    """الحقولُ بعناوينها مرتّبةً — القالبُ يعرضها كما هي ولا يحمل نصّاً."""
    reasons = dict(form.REASONS)
    labels = form.FIELD_LABELS
    rows = [
        (labels["sequence"], permit.sequence),
        (labels["student"], permit.student.full_name),
        (labels["class_group"], str(permit.class_group)),
        (labels["reason"], reasons.get(permit.reason, permit.reason)),
        (labels["note"], permit.note or "—"),
        (labels["exit_at"], permit.exit_at),
        (labels["periods"], permit.completed_periods),
        (
            labels["guardian"],
            form.GUARDIAN_PRESENT_YES if permit.guardian_present else form.GUARDIAN_PRESENT_NO,
        ),
        (labels["approved_by"], permit.approved_by.full_name if permit.approved_by else "—"),
    ]
    warning = (
        (form.LOW_PERIODS_WARNING % form.MIN_PERIODS_FOR_ATTENDANCE) if low_periods(permit) else ""
    )
    return {
        "title": form.FORM_TITLE,
        "subtitle": form.FORM_SUBTITLE,
        "rows": rows,
        "instructions": form.INSTRUCTIONS,
        "signatories": form.SIGNATORIES,
        "warning": warning,
    }


def render_permit(user: Any, permit: Any) -> bytes:
    ctx = get_export_context_for(user, form.FORM_TITLE)
    ctx.update(form_context(permit))
    ctx["school"] = permit.school
    pdf = render_pdf_bytes(render_to_string(TEMPLATE, ctx))
    AuditLog.log(
        user=user,
        action="export",
        model_name="other",
        object_id=permit.pk,
        object_repr=f"{KIND} {masked_repr(permit)}",
        changes={"kind": KIND, "full_national_id": False},
        school=permit.school,
    )
    return pdf
