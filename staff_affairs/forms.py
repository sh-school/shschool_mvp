"""staff_affairs/forms.py — نماذج إدخال شؤون الموظفين."""

from django import forms

from .models import LEAVE_TYPES


class LeaveRequestForm(forms.Form):
    """طلب إجازة جديد."""
    staff_id = forms.UUIDField(error_messages={"required": "يرجى اختيار الموظف."})
    leave_type = forms.ChoiceField(choices=LEAVE_TYPES, label="نوع الإجازة")
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="تاريخ البداية",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="تاريخ النهاية",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=1000, label="السبب",
    )
    attachment = forms.FileField(required=False, label="مرفق")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
        if start and end:
            cleaned["days_count"] = (end - start).days + 1
        return cleaned


class LeaveReviewForm(forms.Form):
    """مراجعة طلب إجازة — موافقة أو رفض."""
    action = forms.ChoiceField(
        choices=[("approved", "موافقة"), ("rejected", "رفض")],
        label="القرار",
    )
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        max_length=500, required=False, label="سبب الرفض",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "rejected" and not cleaned.get("rejection_reason"):
            raise forms.ValidationError("يجب ذكر سبب الرفض.")
        return cleaned
