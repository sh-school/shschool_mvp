"""behavior/forms.py — Django Forms للمخالفات السلوكية."""

from django import forms

# REQ-SH-001 (Client #001 — MTG-007): Structured disciplinary action choices.
# Keep in sync with BehaviorInfraction.DISCIPLINARY_ACTION_CHOICES.
DISCIPLINARY_ACTION_CHOICES = [
    ("", "-- اختر الإجراء --"),
    ("verbal_warning", "تنبيه شفهي"),
    ("written_pledge", "تعهد خطي"),
    ("incident_report", "محضر لإثبات المخالفة"),
    ("parent_pledge", "تعهد خطي لولي الأمر"),
    ("social_specialist_referral", "تحويل للأخصائي الاجتماعي"),
    ("parent_summons", "استدعاء ولي الأمر"),
]

_VIOLATION_DESC_MIN = 20
_VIOLATION_DESC_MAX = 2000


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
    # ── REQ-SH-001: dropdown structured action ──
    disciplinary_action_type = forms.ChoiceField(
        choices=DISCIPLINARY_ACTION_CHOICES,
        required=True,
        error_messages={"required": "يرجى اختيار الإجراء التأديبي."},
    )
    violation_description = forms.CharField(
        required=False,
        max_length=_VIOLATION_DESC_MAX,
        widget=forms.Textarea,
    )
    # legacy free-text (backward compat with quick_log_form & committee view)
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

    def clean(self):
        """Conditional validation: violation_description required iff incident_report."""
        cleaned = super().clean()
        action_type = cleaned.get("disciplinary_action_type")
        desc = (cleaned.get("violation_description") or "").strip()

        if action_type == "incident_report":
            if len(desc) < _VIOLATION_DESC_MIN:
                self.add_error(
                    "violation_description",
                    f"وصف المخالفة مطلوب ({_VIOLATION_DESC_MIN} حرف على الأقل) "
                    "عند اختيار 'محضر لإثبات المخالفة'.",
                )
            elif len(desc) > _VIOLATION_DESC_MAX:
                self.add_error(
                    "violation_description",
                    f"الحد الأقصى لوصف المخالفة هو {_VIOLATION_DESC_MAX} حرف.",
                )
        else:
            # Do not persist stray text when a different action is chosen.
            cleaned["violation_description"] = ""
        return cleaned
