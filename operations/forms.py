"""operations/forms.py — نماذج الجداول والحضور والتبادل"""

from django import forms

from .models import TeacherAbsence


class SwapRequestForm(forms.Form):
    slot_a = forms.UUIDField(label="الحصة الأولى (طالب التبادل)")
    slot_b = forms.UUIDField(label="الحصة الثانية (المُعروض للتبادل)")
    swap_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ التبادل",
    )
    reason = forms.CharField(
        max_length=500,
        required=False,
        label="سبب التبادل",
        widget=forms.TextInput(attrs={"placeholder": "سبب اختياري"}),
    )


class SwapRespondForm(forms.Form):
    ACTION_CHOICES = [("accept", "قبول"), ("reject", "رفض")]
    action = forms.ChoiceField(choices=ACTION_CHOICES, label="القرار")
    rejection_reason = forms.CharField(
        max_length=500,
        required=False,
        label="سبب الرفض",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "reject" and not cleaned.get("rejection_reason"):
            raise forms.ValidationError("يجب ذكر سبب الرفض.")
        return cleaned


class TeacherAbsenceForm(forms.Form):
    teacher_id = forms.UUIDField(label="المعلم")
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="التاريخ",
    )
    reason = forms.ChoiceField(
        choices=TeacherAbsence.REASON,
        label="السبب",
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        label="ملاحظات",
    )


class CompensatoryRequestForm(forms.Form):
    original_slot = forms.UUIDField(label="الحصة الأصلية")
    absence = forms.UUIDField(label="الغياب المرتبط")
    compensatory_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ الحصة التعويضية",
    )
    compensatory_period = forms.IntegerField(
        min_value=1,
        max_value=10,
        label="الحصة (1–10)",
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        label="ملاحظات",
    )
