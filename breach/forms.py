"""breach/forms.py — تحقّقُ نموذج تسجيل الخرق.

كان `create` يقرأ `request.POST[...]` مباشرةً فيسقط بـ500 عند غياب حقلٍ أو رقمٍ فاسد،
ويُبدِّل تاريخَ اكتشافٍ فاسداً بـ«الآن» بصمت — وهو أساسُ حساب مهلة الـ72 ساعة.
"""

from datetime import timedelta

from django import forms
from django.core.validators import MaxValueValidator
from django.utils import timezone

from core.capabilities import capability
from core.models import BreachReport, CustomUser

DISCOVERED_FORMAT = "%Y-%m-%dT%H:%M"
#: فرقُ الساعة بين جهاز المستخدم والخادم لا يُرفض به تسجيلٌ صحيح.
FUTURE_TOLERANCE_MINUTES = 5
#: سقفٌ معقولٌ لعدد المتأثرين: يمنع رقماً فاسداً (أخطاءُ الإدخال) لا يقع في مدرسة.
MAX_AFFECTED = 1_000_000

_CONTROL = {"class": "form-control"}
_AREA = {"class": "form-control resize-y"}


class BreachReportForm(forms.ModelForm):
    discovered_at = forms.DateTimeField(
        label="وقت الاكتشاف",
        input_formats=[DISCOVERED_FORMAT],
        widget=forms.DateTimeInput(
            format=DISCOVERED_FORMAT,
            attrs={**_CONTROL, "type": "datetime-local", "id": "breachDiscovered"},
        ),
        error_messages={
            "required": "وقتُ الاكتشاف مطلوب.",
            "invalid": "وقتُ الاكتشاف غيرُ صالح.",
        },
    )

    class Meta:
        model = BreachReport
        fields = [
            "title",
            "description",
            "severity",
            "data_type_affected",
            "affected_count",
            "discovered_at",
            "immediate_action",
            "containment_action",
            "assigned_to",
            "evidence_notes",
            "notification_text",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    **_CONTROL,
                    "id": "breachTitle",
                    "placeholder": "مثال: تسريب بيانات طلاب من قاعدة البيانات",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    **_AREA,
                    "id": "breachDescription",
                    "rows": 3,
                    "placeholder": "ماذا حدث؟ كيف اكتُشف؟ ما البيانات المتأثرة؟",
                }
            ),
            "severity": forms.Select(attrs={**_CONTROL, "id": "breachSeverity"}),
            "data_type_affected": forms.Select(attrs={**_CONTROL, "id": "breachDataType"}),
            "affected_count": forms.NumberInput(
                attrs={
                    **_CONTROL,
                    "id": "breachAffected",
                    "min": 0,
                    "max": MAX_AFFECTED,
                    "inputmode": "numeric",
                }
            ),
            "assigned_to": forms.Select(attrs={**_CONTROL, "id": "breachAssignee"}),
            "evidence_notes": forms.Textarea(
                attrs={
                    **_AREA,
                    "id": "breachEvidence",
                    "rows": 3,
                    "placeholder": "سجلّاتُ الوصول، لقطات، مراسلات، أيّ دليلٍ يُحفظ مع البلاغ",
                }
            ),
            "immediate_action": forms.Textarea(
                attrs={
                    **_AREA,
                    "id": "breachImmediate",
                    "rows": 2,
                    "placeholder": "عزل النظام، تغيير كلمات المرور، إغلاق الثغرة...",
                }
            ),
            "containment_action": forms.Textarea(
                attrs={**_AREA, "id": "breachContainment", "rows": 2}
            ),
            "notification_text": forms.Textarea(
                attrs={
                    **_AREA,
                    "id": "breachNotification",
                    "rows": 4,
                    "placeholder": "اتركه فارغاً ليُملأ من بيانات الخرق عند الحفظ",
                }
            ),
        }
        error_messages = {
            "title": {"required": "عنوانُ الخرق مطلوب."},
            "description": {"required": "وصفُ الخرق مطلوب."},
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        # المكلَّفُ يصله تنبيهُ الجرس برابط الصفحة: فلا يُعرض إلّا من يفتحها.
        assignees = CustomUser.objects.none()
        if school is not None:
            allowed = capability("breach.manage").expanded_roles
            assignees = CustomUser.objects.filter(
                is_active=True,
                memberships__school=school,
                memberships__is_active=True,
                memberships__role__name__in=allowed,
            ).distinct()
        self.fields["assigned_to"].queryset = assignees
        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].empty_label = "— بلا تكليف —"
        self.fields["assigned_to"].label_from_instance = lambda user: user.full_name
        # العددُ الغائبُ صفرٌ كما كان؛ والفاسدُ يبقى خطأً لا يُخفى.
        self.fields["affected_count"].required = False
        self.fields["affected_count"].error_messages["invalid"] = "عددُ المتأثرين رقمٌ صحيح."
        self.fields["affected_count"].error_messages["min_value"] = "عددُ المتأثرين لا يقلّ عن صفر."
        self.fields["affected_count"].max_value = MAX_AFFECTED
        self.fields["affected_count"].validators.append(MaxValueValidator(MAX_AFFECTED))
        self.fields["affected_count"].error_messages["max_value"] = (
            f"عددُ المتأثرين لا يزيد على {MAX_AFFECTED:,}."
        )

    def clean_discovered_at(self):
        """موعدُ NCSA = الاكتشافُ + 72 ساعة: وقتٌ في المستقبل يمدّد المهلةَ بلا وجه حقّ."""
        value = self.cleaned_data["discovered_at"]
        if value > timezone.now() + timedelta(minutes=FUTURE_TOLERANCE_MINUTES):
            raise forms.ValidationError("وقتُ الاكتشاف لا يكون في المستقبل.")
        return value

    def clean_affected_count(self):
        return self.cleaned_data.get("affected_count") or 0


class BreachEditForm(BreachReportForm):
    """تعديلُ خرقٍ مسجَّل. وقتُ الاكتشاف لا يُعدَّل: عليه مهلةُ الـ72 ساعة المعتمَدة قانونيّاً.

    ونصُّ الإشعار يُقفل بعد «تم الإشعار» — هو سجلُّ ما أُرسل فعلاً.
    """

    regenerate_notice = forms.BooleanField(
        required=False,
        label="أعد توليد نصّ الإشعار من بيانات الخرق المحدَّثة",
        widget=forms.CheckboxInput(attrs={"id": "breachRegenerate"}),
    )

    class Meta(BreachReportForm.Meta):
        fields = [f for f in BreachReportForm.Meta.fields if f != "discovered_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("discovered_at", None)
        if self.instance.status == "notified":
            self.fields["notification_text"].disabled = True
            self.fields["regenerate_notice"].disabled = True


class NcsaNoticeForm(forms.Form):
    """تسجيلُ إشعار NCSA الأوّل: مكتملاً، أو مبدئيّاً بأسباب النقص وموعد الاستكمال (دليل NCSA v2.0)."""

    is_initial = forms.BooleanField(
        required=False,
        label="الإشعارُ مبدئيّ (معلوماتُه ناقصة وسأستكمله لاحقاً)",
        widget=forms.CheckboxInput(attrs={"id": "ncsaInitial"}),
    )
    missing_reasons = forms.CharField(
        required=False,
        label="أسبابُ نقص المعلومات",
        widget=forms.Textarea(attrs={**_AREA, "id": "ncsaMissing", "rows": 2}),
    )
    completion_due_at = forms.DateTimeField(
        required=False,
        label="موعدُ الاستكمال",
        input_formats=[DISCOVERED_FORMAT],
        widget=forms.DateTimeInput(
            format=DISCOVERED_FORMAT,
            attrs={**_CONTROL, "type": "datetime-local", "id": "ncsaDue"},
        ),
        error_messages={"invalid": "موعدُ الاستكمال غيرُ صالح."},
    )

    def clean(self):
        data = super().clean()
        if data.get("is_initial"):
            if not (data.get("missing_reasons") or "").strip():
                self.add_error("missing_reasons", "اذكر أسبابَ نقص المعلومات.")
            due = data.get("completion_due_at")
            if due is None:
                self.add_error("completion_due_at", "حدّد موعدَ الاستكمال.")
            elif due <= timezone.now():
                self.add_error("completion_due_at", "موعدُ الاستكمال يكون في المستقبل.")
        return data


class IndividualsNotifiedForm(forms.Form):
    """تسجيلُ إخطار الأفراد الفعليّ: القناةُ إلزاميّة (مواصفة 0104)."""

    channel = forms.ChoiceField(
        choices=BreachReport.INDIVIDUALS_CHANNELS,
        label="قناةُ الإخطار",
        widget=forms.Select(attrs={**_CONTROL, "id": "indChannel"}),
        error_messages={
            "required": "اختر قناةَ إخطار الأفراد.",
            "invalid_choice": "اختر قناةَ إخطار الأفراد.",
        },
    )


class IndividualsAssessmentForm(forms.Form):
    """تقديرُ لزوم إخطار الأفراد المتأثّرين (م.14): واجبٌ بموعد، أو غيرُ لازمٍ بسبب."""

    required = forms.TypedChoiceField(
        label="هل يجب إخطارُ الأفراد المتأثّرين؟",
        choices=[("1", "نعم — يجب إخطارُهم"), ("0", "لا — غيرُ لازم")],
        coerce=lambda v: v == "1",
        widget=forms.RadioSelect(attrs={"class": "choice-list"}),
        error_messages={"required": "اختر لزومَ الإخطار."},
    )
    deadline = forms.DateTimeField(
        required=False,
        label="موعدُ إخطار الأفراد (يُترك فارغاً ليساوي موعدَ إشعار NCSA)",
        input_formats=[DISCOVERED_FORMAT],
        widget=forms.DateTimeInput(
            format=DISCOVERED_FORMAT,
            attrs={**_CONTROL, "type": "datetime-local", "id": "indDeadline"},
        ),
        error_messages={"invalid": "موعدُ الإخطار غيرُ صالح."},
    )
    note = forms.CharField(
        required=False,
        label="أساسُ التقدير أو سببُ عدم اللزوم",
        widget=forms.Textarea(attrs={**_AREA, "id": "indNote", "rows": 2}),
    )

    def __init__(self, *args, breach=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.breach = breach

    def clean(self):
        data = super().clean()
        required = data.get("required")
        if required is False and not (data.get("note") or "").strip():
            self.add_error("note", "اذكر سببَ عدم لزوم الإخطار.")
        deadline = data.get("deadline")
        if (
            required
            and deadline
            and self.breach is not None
            and deadline <= self.breach.discovered_at
        ):
            self.add_error("deadline", "موعدُ الإخطار يلي وقتَ الاكتشاف.")
        return data
