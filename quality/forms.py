"""quality/forms.py — نماذج الجودة والإجراءات"""

from django import forms

from .models import QualityProcedure


class ProcedureStatusUpdateForm(forms.Form):
    status = forms.ChoiceField(
        choices=QualityProcedure.STATUS,
        label="الحالة",
    )
    evidence_type = forms.ChoiceField(
        choices=QualityProcedure.EVIDENCE_TYPE,
        required=False,
        label="نوع الدليل",
    )
    evidence_source_file = forms.CharField(
        max_length=500,
        required=False,
        label="مصدر الدليل",
    )
    comments = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="ملاحظات",
    )
    follow_up = forms.ChoiceField(
        choices=QualityProcedure.FOLLOW_UP_CHOICES,
        required=False,
        label="المتابعة",
    )
    deadline = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="الموعد النهائي",
    )
    file = forms.FileField(required=False, label="ملف الدليل")
    evidence_title = forms.CharField(
        max_length=200,
        required=False,
        label="عنوان الدليل",
    )


class ProcedureEvidenceForm(forms.Form):
    title = forms.CharField(max_length=200, label="عنوان الدليل")
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="وصف الدليل",
    )
    file = forms.FileField(required=False, label="ملف")


class ProcedureReviewForm(forms.Form):
    evidence_request_status = forms.ChoiceField(
        choices=QualityProcedure.EVIDENCE_REQUEST_STATUS,
        label="حالة طلب الدليل",
    )
    evidence_request_note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        label="ملاحظة طلب الدليل",
    )
    quality_rating = forms.ChoiceField(
        choices=QualityProcedure.QUALITY_RATING,
        required=False,
        label="التقييم النوعي",
    )
    status = forms.ChoiceField(
        choices=QualityProcedure.STATUS,
        label="الحالة الجديدة",
    )
    new_status = forms.ChoiceField(
        choices=QualityProcedure.STATUS,
        required=False,
        label="الحالة",
    )
