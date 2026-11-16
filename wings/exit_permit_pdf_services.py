"""استمارةُ ورقة الخروج PDF للحارس — نصُّها كلُّه من `exit_permit_form` (W-20261005-010، W-20261116-003).

لا تُطبع ورقةٌ بلا طريقة موافقة (`is_printable`). وكلُّ طباعةٍ سطرُ `AuditLog` بالمعرّف المقنَّع، بلا اسمٍ ولا رقم.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from core.audit_repr import masked_repr
from core.export_utils import generate_export_filename, get_export_context_for
from core.models import AuditLog
from core.pdf_utils import render_pdf_bytes

from . import exit_permit_form as form
from .exit_permit_services import PermitDeniedError, is_printable, low_periods, own_permit

TEMPLATE = "wings/pdf/exit_permit.html"
KIND = "wings.exit_permit_form"


def guardian_rows(permit: Any) -> list[tuple[str, Any]]:
    """سطورُ موافقة الوليّ: الطريقةُ وحدَها للحضور، ومعها بياناتُ الاتّصال للهاتف (الموظفُ والوقتُ تلقائيّان)."""
    labels = form.FIELD_LABELS
    if permit.guardian_method == "phone":
        phone = permit.call_phone + (
            "" if permit.call_phone_registered else f" {form.UNREGISTERED_PHONE}"
        )
        caller = " — ".join(x for x in (permit.caller_name, permit.caller_relation) if x)
        return [
            (labels["guardian"], form.GUARDIAN_PHONE),
            (labels["call_phone"], phone),
            (labels["caller"], caller),
            (labels["issued_by"], permit.requested_by.full_name if permit.requested_by else "—"),
            (labels["issued_at"], permit.created_at),
        ]
    present = permit.guardian_method == "present" or permit.guardian_present
    return [
        (
            labels["guardian"],
            form.GUARDIAN_PRESENT_YES if present else form.GUARDIAN_PRESENT_NO,
        )
    ]


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
        *guardian_rows(permit),
    ]
    warning = (
        (form.LOW_PERIODS_WARNING % form.MIN_PERIODS_FOR_ATTENDANCE) if low_periods(permit) else ""
    )
    return {
        "title": form.FORM_TITLE,
        "subtitle": form.FORM_SUBTITLE,
        "rows": rows,
        "instructions": form.INSTRUCTIONS,
        "delivery_line": form.DELIVERY_LINE,
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


def permit_pdf(user: Any, school: Any, permit_id: Any) -> tuple[bytes, str]:
    """(بايتات الاستمارة، اسمُ الملفّ) لورقةٍ مكتملةِ الموافقة في نطاق المستخدم؛ وغيرُ ذلك `PermitDeniedError`."""
    permit = own_permit(user, school, permit_id)
    if not is_printable(permit):
        raise PermitDeniedError
    filename = generate_export_filename("wings", f"exit-permit-{permit.sequence}", "pdf")
    return render_permit(user, permit), filename
