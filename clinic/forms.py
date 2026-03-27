"""clinic/forms.py — نماذج العيادة المدرسية"""
from django import forms

from .models import HealthRecord


class HealthRecordForm(forms.Form):
    blood_type = forms.ChoiceField(
        choices=[("", "— اختر فصيلة الدم —")] + HealthRecord.BLOOD_TYPES,
        required=False,
        label="فصيلة الدم",
    )
    emergency_contact_name = forms.CharField(
        max_length=200,
        required=False,
        label="اسم جهة الاتصال الطارئ",
    )
    emergency_contact_phone = forms.CharField(
        max_length=20,
        required=False,
        label="جوال جهة الاتصال الطارئ",
    )
    allergies = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="الحساسية",
    )
    chronic_diseases = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="الأمراض المزمنة",
    )
    medications = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="الأدوية",
    )


class ClinicVisitForm(forms.Form):
    student_id = forms.UUIDField(label="الطالب")
    reason = forms.CharField(
        max_length=500,
        label="سبب الزيارة",
        widget=forms.TextInput(attrs={"placeholder": "وصف موجز لسبب المراجعة"}),
    )
    symptoms = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="الأعراض",
    )
    temperature = forms.DecimalField(
        max_digits=4,
        decimal_places=1,
        required=False,
        label="درجة الحرارة",
        min_value=30,
        max_value=45,
    )
    treatment = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="العلاج المُقدَّم",
    )
    is_sent_home = forms.BooleanField(
        required=False,
        label="تم إرسال الطالب للمنزل",
    )
