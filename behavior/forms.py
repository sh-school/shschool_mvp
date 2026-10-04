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

#: الإجراءاتُ التي يملك دورٌ بعينه اختيارَها عند تسجيل المخالفة (W-20261001-022). دورٌ غيرُ مذكور هنا
#: يرى القائمةَ كاملةً كما كان. والمشرفُ الإداريّ — بطاقتُه «رصد المخالفات وتحويلها للأخصائي الاجتماعي»
#: وسياسةُ السلوك (08_conduct_policy_2026.md) تُسند التعهّدَ الخطّيّ لمنسّق شؤون الطلبة والاستدعاءَ للجنة —
#: لا يفرض جزاءً: تنبيهٌ شفهيّ (يُشعَر وليُّ الأمر بتسجيل المخالفة تلقائياً) وتحويلٌ للأخصائيّ.
ROLE_ACTION_LIMITS: dict[str, frozenset[str]] = {
    "admin_supervisor": frozenset({"verbal_warning", "social_specialist_referral"}),
}

NOT_YOUR_ACTION = (
    "هذا الإجراء التأديبي ليس من صلاحية دورك — يمكنك التنبيه الشفهي أو التحويل للأخصائي الاجتماعي."
)


def action_choices_for(role: str | None) -> list[tuple[str, str]]:
    """قائمةُ الإجراءات المتاحة لهذا الدور — الخادمُ والقالبُ يقرآن منها معاً."""
    allowed = ROLE_ACTION_LIMITS.get(role or "")
    if allowed is None:
        return list(DISCIPLINARY_ACTION_CHOICES)
    return [
        (value, label)
        for value, label in DISCIPLINARY_ACTION_CHOICES
        if not value or value in allowed
    ]


_VIOLATION_DESC_MIN = 20
_VIOLATION_DESC_MAX = 2000


class InfractionForm(forms.Form):
    """نموذج تسجيل مخالفة سلوكية. نظام النقاط ملغى — لا يُعرض ولا يُطلب."""

    _MAX_DESC_LEN = 2000
    _VALID_LEVELS = {1, 2, 3, 4}

    student_id = forms.UUIDField(
        error_messages={"required": "يرجى اختيار الطالب."},
    )
    violation_category = forms.UUIDField(required=False)
    description = forms.CharField(
        max_length=_MAX_DESC_LEN,
        required=False,
        error_messages={
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

    def __init__(self, *args, role: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["disciplinary_action_type"]
        field.choices = action_choices_for(role)
        if role in ROLE_ACTION_LIMITS:
            field.error_messages["invalid_choice"] = NOT_YOUR_ACTION

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
