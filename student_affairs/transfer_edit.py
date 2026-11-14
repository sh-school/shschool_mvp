"""نموذجُ تعديل الانتقال المعلَّق (W-20261114-010).

القراءةُ في `transfer_edit_selectors.py` والكتابةُ في `transfer_edit_services.py`؛ لا تعديلَ للطالب ولا للاتجاه بعد الإنشاء.
"""

from typing import Any

from django import forms

from .models import StudentTransfer


class TransferEditForm(forms.Form):
    """حقولُ تعديل الانتقال المعلَّق؛ الاتجاهُ والطالبُ ثابتان فلا حقلَ لهما."""

    other_school_name = forms.CharField(max_length=200, required=False, label="المدرسة الأخرى")
    from_grade = forms.CharField(max_length=3, required=False, label="الصف (من)")
    to_grade = forms.CharField(max_length=3, required=False, label="الصف (إلى)")
    to_class_group_id = forms.UUIDField(required=False, label="الشعبة المنقول إليها")
    transfer_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="تاريخ الانتقال"
    )
    reason = forms.CharField(max_length=1000, required=False, label="السبب")
    notes = forms.CharField(required=False, label="ملاحظات")

    def __init__(self, *args: Any, direction: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.direction = direction

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if self.direction == "internal":
            if not cleaned.get("to_class_group_id"):
                self.add_error("to_class_group_id", "اختر الشعبة المنقول إليها.")
        elif not cleaned.get("other_school_name"):
            self.add_error("other_school_name", "اسم المدرسة الأخرى مطلوب.")
        return cleaned


def initial_for(transfer: StudentTransfer) -> dict[str, Any]:
    """القيمُ الحاليّة للانتقال لتعبئة نموذج التعديل."""
    return {
        "other_school_name": transfer.other_school_name,
        "from_grade": transfer.from_grade,
        "to_grade": transfer.to_grade,
        "to_class_group_id": transfer.to_class_group_id,
        "transfer_date": transfer.transfer_date,
        "reason": transfer.reason,
        "notes": transfer.notes,
    }
