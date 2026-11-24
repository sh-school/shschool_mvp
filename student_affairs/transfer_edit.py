"""نموذجُ تعديل الانتقال المعلَّق (W-20261114-010).

القراءةُ في `transfer_edit_selectors.py` والكتابةُ في `transfer_edit_services.py`؛ لا تعديلَ للطالب ولا للاتجاه بعد الإنشاء.
"""

from typing import Any

from django import forms

from .forms import TransferForm
from .models import StudentTransfer

# رسائلُ التحقّق العربيّة من نموذج الإنشاء نفسِه فلا تتكرّر ولا تتفاوت (W-20261124-003).
_CREATE = TransferForm.base_fields
REASON_REQUIRED_MESSAGE = "سبب الانتقال مطلوب في الانتقال الصادر."


class TransferEditForm(forms.Form):
    """حقولُ تعديل الانتقال المعلَّق؛ الاتجاهُ والطالبُ ثابتان فلا حقلَ لهما."""

    other_school_name = forms.CharField(
        max_length=200,
        required=False,
        label="المدرسة الأخرى",
        error_messages=dict(_CREATE["other_school_name"].error_messages),
    )
    to_class_group_id = forms.UUIDField(
        required=False,
        label="الشعبة المنقول إليها",
        error_messages=dict(_CREATE["to_class_group_id"].error_messages),
    )
    transfer_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ الانتقال",
        error_messages=dict(_CREATE["transfer_date"].error_messages),
    )
    reason = forms.CharField(
        max_length=1000,
        required=False,
        label="السبب",
        error_messages=dict(_CREATE["reason"].error_messages),
    )
    notes = forms.CharField(required=False, label="ملاحظات")

    def __init__(self, *args: Any, direction: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.direction = direction

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if self.direction == "internal":
            if not cleaned.get("to_class_group_id") and "to_class_group_id" not in self.errors:
                self.add_error("to_class_group_id", "اختر الشعبة المنقول إليها.")
        elif not cleaned.get("other_school_name") and "other_school_name" not in self.errors:
            self.add_error("other_school_name", "اسم المدرسة الأخرى مطلوب.")
        # سببُ الصادر إلزاميّ كما في الإنشاء.
        if self.direction == "out" and not (cleaned.get("reason") or "").strip():
            self.add_error("reason", REASON_REQUIRED_MESSAGE)
        return cleaned


def initial_for(transfer: StudentTransfer) -> dict[str, Any]:
    """القيمُ الحاليّة للانتقال لتعبئة نموذج التعديل."""
    return {
        "other_school_name": transfer.other_school_name,
        "to_class_group_id": transfer.to_class_group_id,
        "transfer_date": transfer.transfer_date,
        "reason": transfer.reason,
        "notes": transfer.notes,
    }
