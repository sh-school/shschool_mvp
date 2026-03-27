"""behavior/forms.py — Django Forms للمخالفات السلوكية."""

from django import forms


class InfractionForm(forms.Form):
    """نموذج تسجيل مخالفة سلوكية."""

    _MAX_POINTS = 100
    _MAX_DESC_LEN = 2000
    _VALID_LEVELS = {1, 2, 3, 4}

    student_id = forms.UUIDField(
        error_messages={"required": "يرجى اختيار الطالب."},
    )
    violation_category = forms.UUIDField(required=False)
    description = forms.CharField(
        max_length=_MAX_DESC_LEN,
        error_messages={
            "required": "يرجى كتابة وصف المخالفة.",
            "max_length": f"الوصف لا يتجاوز {_MAX_DESC_LEN} حرف.",
        },
    )
    action_taken = forms.CharField(required=False, max_length=1000)
    level = forms.IntegerField(initial=1, min_value=1, max_value=4)
    points_deducted = forms.IntegerField(
        initial=0,
        min_value=0,
        max_value=_MAX_POINTS,
        error_messages={"max_value": f"نقاط الخصم يجب أن تكون بين 0 و {_MAX_POINTS}."},
    )

    def clean_level(self):
        level = self.cleaned_data["level"]
        if level not in self._VALID_LEVELS:
            raise forms.ValidationError("درجة المخالفة يجب أن تكون بين 1 و 4.")
        return level
