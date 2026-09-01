"""استماراتُ خطّة النصاب — واحدةٌ لكلّ حقيقةٍ إداريّة، لا واحدةٌ للخطّة كلّها.

النصابُ قرارٌ، والتخفيضُ قرارٌ آخر، والتوزيعُ حسب المرحلة تفصيلٌ إداريّ،
والمؤهّلُ مستندٌ من ملفّ الموظّف. لكلٍّ منها منبعُه ومرجعُه، وغداً صلاحيّتُه
ومدقّقُه. فاستمارةٌ واحدةٌ ضخمةٌ تجمعها تُخفي هذا الاختلافَ وتُصعّب فصلَ
الصلاحيات لاحقاً.

والتزامنُ محروسٌ هنا لا في الـview: كلُّ استمارةٍ تحمل الطابعَ الذي رآه
المُدخِل، فإن كتب غيرُه قبله رُفض التعديلُ بدل أن يُطمَس.
"""

from django import forms

from .models import (
    LEVEL_TYPES,
    PROVENANCE_KINDS,
    QUALIFICATION_STATUSES,
    SOURCES,
    TeacherSubjectQualification,
    TeacherWorkloadAllocation,
    TeacherWorkloadPlan,
)

_TEXT = {"class": "form-input"}
_SELECT = {"class": "form-select"}


class StaleWriteError(Exception):
    """كُتب فوق نسخةٍ رآها المُدخِلُ ثمّ تغيّرت."""


class ConcurrencyGuardMixin:
    """يحمل الطابعَ الذي رآه المُدخِل، ويرفض الكتابةَ فوق ما تغيّر بعده.

    والرفضُ مقصود: آخرُ من يضغط «حفظ» ليس أحقَّ بالحقيقة من زميلٍ سبقه،
    والطمسُ الصامتُ يُضيّع قراراً إداريّاً بلا أثر.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # يُضاف هنا لا كخاصّيّةِ صنف: الـmixin ليس `Form`، فلا يمرّ حقلُه على
        # `DeclarativeFieldsMetaclass` ولا يصل إلى `self.fields`.
        self.fields["seen_at"] = forms.CharField(widget=forms.HiddenInput, required=False)
        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["seen_at"].initial = self.instance.updated_at.isoformat()

    def clean_seen_at(self):
        seen = (self.cleaned_data.get("seen_at") or "").strip()
        if not seen or not (self.instance and self.instance.pk):
            return seen
        current = self.instance.__class__.objects.get(pk=self.instance.pk).updated_at.isoformat()
        if seen != current:
            raise forms.ValidationError(
                "عُدِّلت الخطّةُ من مكانٍ آخر بعد أن فتحتَها. "
                "أعِد تحميلَ الصفحةَ لترى ما تغيّر قبل أن تكتب فوقه."
            )
        return seen


class PlanHeadForm(ConcurrencyGuardMixin, forms.ModelForm):
    """النصابُ الأساسيُّ ومن أين جاء — ولا رقمَ بلا منبع."""

    class Meta:
        model = TeacherWorkloadPlan
        fields = [
            "required_weekly_periods",
            "required_source_kind",
            "required_source_reference",
            "required_policy_key",
        ]
        labels = {
            "required_weekly_periods": "النصاب الأسبوعي",
            "required_source_kind": "منبع الرقم",
            "required_source_reference": "المرجع",
            "required_policy_key": "رمز السياسة",
        }
        widgets = {
            "required_weekly_periods": forms.NumberInput(attrs={**_TEXT, "min": 0, "max": 40}),
            "required_source_kind": forms.Select(attrs=_SELECT, choices=PROVENANCE_KINDS),
            "required_source_reference": forms.TextInput(
                attrs={**_TEXT, "placeholder": "رقم التعميم أو المحضر"}
            ),
            "required_policy_key": forms.TextInput(attrs=_TEXT),
        }

    def clean(self):
        data = super().clean()
        probe = TeacherWorkloadPlan(
            required_weekly_periods=data.get("required_weekly_periods") or 0,
            required_source_kind=data.get("required_source_kind") or "",
            required_source_reference=data.get("required_source_reference") or "",
            required_policy_key=data.get("required_policy_key") or "",
            required_source_plan_id=self.instance.required_source_plan_id,
        )
        gaps = [g for g in probe.provenance_gaps() if "النصاب" in g]
        if gaps:
            raise forms.ValidationError(gaps)
        return data


class ReductionForm(ConcurrencyGuardMixin, forms.ModelForm):
    """التخفيضُ قرارٌ مستقلٌّ عن النصاب — وله سببُه وجهتُه ومرجعُه."""

    class Meta:
        model = TeacherWorkloadPlan
        fields = [
            "reduction_periods",
            "reduction_reason",
            "reduction_source",
            "reduction_source_reference",
        ]
        labels = {
            "reduction_periods": "حصص التخفيض",
            "reduction_reason": "السبب",
            "reduction_source": "الجهة",
            "reduction_source_reference": "المرجع",
        }
        widgets = {
            "reduction_periods": forms.NumberInput(attrs={**_TEXT, "min": 0, "max": 40}),
            "reduction_reason": forms.TextInput(
                attrs={**_TEXT, "placeholder": "منسّق مادّة، تفرّغ إداريّ…"}
            ),
            "reduction_source": forms.Select(attrs=_SELECT, choices=[("", "—"), *SOURCES]),
            "reduction_source_reference": forms.TextInput(attrs=_TEXT),
        }

    def clean(self):
        data = super().clean()
        periods = data.get("reduction_periods") or 0
        if periods > self.instance.required_weekly_periods:
            raise forms.ValidationError(
                f"التخفيضُ {periods} يتجاوز النصابَ {self.instance.required_weekly_periods}."
            )
        probe = TeacherWorkloadPlan(
            required_weekly_periods=self.instance.required_weekly_periods,
            required_source_kind=self.instance.required_source_kind,
            required_source_reference=self.instance.required_source_reference,
            required_policy_key=self.instance.required_policy_key,
            required_source_plan_id=self.instance.required_source_plan_id,
            reduction_periods=periods,
            reduction_reason=data.get("reduction_reason") or "",
            reduction_source=data.get("reduction_source") or "",
            reduction_source_reference=data.get("reduction_source_reference") or "",
        )
        gaps = [g for g in probe.provenance_gaps() if "التخفيض" in g]
        if gaps:
            raise forms.ValidationError(gaps)
        return data


class AllocationForm(forms.ModelForm):
    """توزيعُ الهدف التدريسيّ على المراحل — ولا تخفيضَ هنا."""

    class Meta:
        model = TeacherWorkloadAllocation
        fields = ["level_type", "target_periods", "notes"]
        labels = {
            "level_type": "المرحلة",
            "target_periods": "الحصص المستهدفة",
            "notes": "ملاحظات",
        }
        widgets = {
            "level_type": forms.Select(attrs=_SELECT, choices=LEVEL_TYPES),
            "target_periods": forms.NumberInput(attrs={**_TEXT, "min": 0, "max": 40}),
            "notes": forms.TextInput(attrs=_TEXT),
        }

    def __init__(self, *args, plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        if plan is not None:
            self.instance.workload_plan = plan


class QualificationForm(forms.ModelForm):
    """ما يستطيع المعلّمُ تدريسَه — بمرجعٍ من ملفّه، لا باستنتاجٍ من الجدول."""

    class Meta:
        model = TeacherSubjectQualification
        fields = [
            "subject",
            "level_type",
            "qualification_status",
            "is_primary",
            "source",
            "source_reference",
            "valid_from",
            "valid_to",
        ]
        labels = {
            "subject": "المادّة",
            "level_type": "المرحلة",
            "qualification_status": "الحالة",
            "is_primary": "تخصّصه الأساسي",
            "source": "الجهة",
            "source_reference": "المرجع",
            "valid_from": "سارٍ من",
            "valid_to": "سارٍ حتى",
        }
        widgets = {
            "subject": forms.Select(attrs=_SELECT),
            "level_type": forms.Select(attrs=_SELECT, choices=[("", "كلّ المراحل"), *LEVEL_TYPES]),
            "qualification_status": forms.Select(
                attrs=_SELECT, choices=QUALIFICATION_STATUSES
            ),
            "source": forms.Select(attrs=_SELECT, choices=SOURCES),
            "source_reference": forms.TextInput(attrs=_TEXT),
            "valid_from": forms.DateInput(attrs={**_TEXT, "type": "date"}),
            "valid_to": forms.DateInput(attrs={**_TEXT, "type": "date"}),
        }

    def __init__(self, *args, school=None, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            from operations.models import Subject

            self.fields["subject"].queryset = Subject.objects.filter(school=school)
            self.instance.school = school
        if teacher is not None:
            self.instance.teacher = teacher
