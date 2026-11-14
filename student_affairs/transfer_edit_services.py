"""كتابةُ تعديل الانتقال المعلَّق (W-20261114-010) — لا تمسّ قواعدَ الاعتماد والمراجعة (`transfer_review`)."""

from typing import Any

from django.db import transaction

from core.models.audit import AuditLog

from .internal_transfer import internal_target_error
from .models import StudentTransfer
from .selectors import active_class

#: الحقولُ القابلةُ للتعديل في الانتقال المعلَّق؛ يُسجَّل في التدقيق أسماءُ ما تغيّر منها لا قيمُها.
EDITABLE_FIELDS = (
    "other_school_name",
    "to_class_group",
    "transfer_date",
    "reason",
    "notes",
)

NOT_PENDING_MESSAGE = "لا يُعدَّل إلا الانتقالُ المعلَّق (قيد الانتظار)؛ هذا الانتقال تجاوز تلك المرحلة."


def update_pending_transfer(
    transfer_id: Any, school: Any, data: dict[str, Any], actor: Any
) -> list[str]:
    """يحفظ تعديلَ انتقالٍ معلَّق ذرّيّاً ويُرجع أسماءَ الحقول التي تغيّرت.

    يُرفض (`ValueError` برسالةٍ عربيّة) إن لم يعد معلَّقاً أو كان هدفُه الداخليُّ غيرَ صالح؛ والتحقّقُ يسبق أيَّ كتابة.
    التدقيقُ يحمل أسماءَ الحقول المتغيّرة لا قيمَها ولا اسمَ الطالب.
    """
    with transaction.atomic():
        transfer = StudentTransfer.objects.select_for_update().get(pk=transfer_id, school=school)
        if transfer.status != "pending":
            raise ValueError(NOT_PENDING_MESSAGE)
        internal = transfer.direction == "internal"
        new_values: dict[str, Any] = {
            "other_school_name": school.name if internal else data["other_school_name"],
            "to_class_group": active_class(school, data["to_class_group_id"]) if internal else None,
            "transfer_date": data["transfer_date"],
            "reason": data.get("reason", ""),
            "notes": data.get("notes", ""),
        }
        changed = [name for name in EDITABLE_FIELDS if getattr(transfer, name) != new_values[name]]
        for name in changed:
            setattr(transfer, name, new_values[name])
        if internal:
            error = internal_target_error(transfer)
            if error:
                raise ValueError(error)
        if changed:
            transfer.updated_by = actor
            transfer.save(update_fields=[*changed, "updated_by", "updated_at"])
            AuditLog.log(
                user=actor,
                action="update",
                model_name="other",
                object_id=transfer.pk,
                object_repr="تعديل انتقال معلَّق",
                changes={"changed_fields": changed},
                school=school,
            )
    return changed
