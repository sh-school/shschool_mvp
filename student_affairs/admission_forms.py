"""نموذجُ إدخال طلب الالتحاق (W-20261001-033): النصُّ الحرفيّ لنموذج 07 بحقوله."""

import re

from django import forms

from core.models.academic import ClassGroup

from .admission_models import AdmissionApplication

_NATIONAL_ID = re.compile(r"^\d{5,20}$")


class AdmissionApplicationForm(forms.Form):
    student_name = forms.CharField(max_length=200, label="اسم الطالب")
    student_national_id = forms.CharField(
        max_length=20, required=False, label="الرقم الشخصي للطالب"
    )
    birth_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="تاريخ الميلاد"
    )
    nationality = forms.CharField(max_length=100, required=False, label="الجنسية")
    current_school = forms.CharField(max_length=200, required=False, label="المدرسة الحالية")
    grade = forms.ChoiceField(choices=ClassGroup.GRADES, label="الصف المطلوب")
    health_status = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}), label="الحالة الصحية"
    )
    living_with = forms.ChoiceField(
        choices=[("", "—")] + AdmissionApplication.LIVING_WITH_CHOICES,
        required=False,
        label="يعيش مع",
    )
    transport = forms.ChoiceField(
        choices=[("", "—")] + AdmissionApplication.TRANSPORT_CHOICES,
        required=False,
        label="وسيلة النقل",
    )
    housing_area = forms.CharField(max_length=100, required=False, label="المنطقة")
    housing_street = forms.CharField(max_length=100, required=False, label="الشارع")
    housing_house = forms.CharField(max_length=50, required=False, label="رقم المنزل")
    applicant_name = forms.CharField(max_length=200, label="اسم مقدِّم الطلب")
    applicant_national_id = forms.CharField(
        max_length=20, required=False, label="الرقم الشخصي لمقدِّم الطلب"
    )
    applicant_relationship = forms.CharField(max_length=50, label="صلة القرابة")
    applicant_phone = forms.CharField(max_length=20, label="هاتف مقدِّم الطلب")
    declaration_accepted = forms.BooleanField(
        label="أُقرّ بصحة البيانات والمستندات المقدَّمة",
        error_messages={"required": "إقرارُ مقدِّم الطلب شرطٌ لتسجيل الطلب."},
    )

    def _clean_id(self, key: str) -> str:
        value = self.cleaned_data.get(key, "").strip()
        if value and not _NATIONAL_ID.match(value):
            raise forms.ValidationError("الرقم الشخصي أرقامٌ فقط (من 5 إلى 20 رقماً).")
        return value

    def clean_student_national_id(self):
        return self._clean_id("student_national_id")

    def clean_applicant_national_id(self):
        return self._clean_id("applicant_national_id")
