"""operations/forms.py — نماذج الجداول والحضور والتبادل"""

from django import forms

from .models import ScheduleSlot, TeacherAbsence, TeacherExemption


class TeacherExemptionForm(forms.Form):
    """مدخلاتُ التفريغ — تُفحص قبل أن تبلغ الخدمة.

    كان العرضُ يقرأ `request.POST["teacher"]` و`int(request.POST["day_of_week"])`
    مباشرةً: مفتاحٌ ناقصٌ أو رقمٌ غيرُ صالحٍ = صفحةُ خطأٍ لا رسالة. والمعلّمُ
    يُقيَّد بمدرسة المُدخِل في `clean_teacher` — فكان أيُّ UUID يُقبل، ومديرُ
    مدرسةٍ يُفرّغ معلّمَ مدرسةٍ أخرى بتغيير رقمٍ في الطلب.
    """

    teacher = forms.UUIDField(label="المعلم/المنسق")
    exemption_type = forms.ChoiceField(
        choices=TeacherExemption.EXEMPTION_TYPE, initial="full_day", label="نوع التفريغ"
    )
    day_of_week = forms.TypedChoiceField(choices=ScheduleSlot.DAYS, coerce=int, label="اليوم")
    period_number = forms.TypedChoiceField(
        choices=[(p, f"الحصة {p}") for p in ScheduleSlot.PERIODS],
        coerce=int,
        required=False,
        empty_value=None,
        label="رقم الحصة",
    )
    reason = forms.CharField(max_length=200, label="السبب")
    source = forms.ChoiceField(
        choices=TeacherExemption._meta.get_field("source").choices,
        initial="school",
        label="جهة القرار",
    )
    source_reference = forms.CharField(max_length=200, label="مرجع القرار")

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

    def clean_teacher(self):
        from core.models import CustomUser

        teacher = (
            CustomUser.objects.in_school(self.school)
            .filter(pk=self.cleaned_data["teacher"])
            .first()
        )
        if teacher is None:
            raise forms.ValidationError("المعلّم المختار ليس من منسوبي مدرستك.")
        return teacher

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("exemption_type") == "specific_period" and not cleaned.get(
            "period_number"
        ):
            self.add_error("period_number", "حدّد رقم الحصة لتفريغ حصةٍ بعينها.")
        if cleaned.get("exemption_type") == "full_day":
            cleaned["period_number"] = None
        return cleaned


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
