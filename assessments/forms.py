"""assessments/forms.py — Django Forms لعمليات التقييم."""

from decimal import Decimal

from django import forms

from .models import Assessment


class CreateAssessmentForm(forms.Form):
    """نموذج إنشاء تقييم جديد في باقة."""

    title = forms.CharField(
        max_length=200,
        error_messages={"required": "عنوان التقييم مطلوب"},
    )
    assessment_type = forms.ChoiceField(
        choices=Assessment.ASSESSMENT_TYPE,
        initial="exam",
    )
    date = forms.DateField(required=False)
    max_grade = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        initial=Decimal("100"),
        min_value=Decimal("1"),
    )
    weight_in_package = forms.DecimalField(
        max_digits=6,
        decimal_places=2,
        initial=Decimal("100"),
        min_value=Decimal("0"),
    )
    description = forms.CharField(required=False, max_length=1000, widget=forms.Textarea)
