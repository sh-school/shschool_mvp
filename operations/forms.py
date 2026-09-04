"""operations/forms.py — نماذج الجداول والحضور والتبادل"""

from django import forms

from core.models.access import EXEMPTABLE_ROLES

from .models import ScheduleSlot, SubjectClassAssignment, TeacherAbsence, TeacherExemption


class TeacherExemptionForm(forms.Form):
    """مدخلاتُ التفريغ — تُفحص قبل أن تبلغ الخدمة.

    كان العرضُ يقرأ `request.POST["teacher"]` و`int(request.POST["day_of_week"])`
    مباشرةً: مفتاحٌ ناقصٌ أو رقمٌ غيرُ صالحٍ = صفحةُ خطأٍ لا رسالة. والمعلّمُ
    يُقيَّد بمدرسة المُدخِل في `clean_teacher` — فكان أيُّ UUID يُقبل، ومديرُ
    مدرسةٍ يُفرّغ معلّمَ مدرسةٍ أخرى بتغيير رقمٍ في الطلب.

    و«المعلّم» قد يكون مجموعةً: `coordinators` تعني منسّقي المواد جميعاً —
    اجتماعُهم الأسبوعيُّ تفريغٌ واحدٌ لا اثنا عشرَ إدخالاً. والأيّامُ تُختار
    عدّةً معاً: الحصّةُ الأولى الأحدَ والثلاثاءَ تفريغان بطلبٍ واحد.
    """

    #: المجموعاتُ المقبولةُ مكانَ معرّف المعلّم — والقيمةُ ليست UUID عمداً.
    GROUPS = {"coordinators": ("coordinator",)}

    teacher = forms.CharField(max_length=40, label="المعلم/المنسق")
    exemption_type = forms.ChoiceField(
        choices=TeacherExemption.EXEMPTION_TYPE, initial="full_day", label="نوع التفريغ"
    )
    day_of_week = forms.TypedMultipleChoiceField(
        choices=ScheduleSlot.DAYS, coerce=int, label="الأيام"
    )
    #: حصصٌ عدّةٌ كالأيّام: الأولى والسابعةُ تفريغان بطلبٍ واحد. وفي «يوم كامل»
    #: تُهمَل، فالقائمةُ تصير `[None]` — حصّةً واحدةً بلا رقم.
    period_number = forms.TypedMultipleChoiceField(
        choices=[(p, f"الحصة {p}") for p in ScheduleSlot.PERIODS],
        coerce=int,
        required=False,
        label="الحصص",
    )
    reason = forms.CharField(max_length=200, label="السبب")
    source = forms.ChoiceField(
        choices=TeacherExemption._meta.get_field("source").choices,
        initial="school",
        label="جهة القرار",
    )

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

    def clean_teacher(self):
        """يُرجع قائمةَ المعلّمين المقصودين — واحداً بمعرّفه أو مجموعةً بدورها."""
        import uuid

        from core.models import CustomUser

        raw = self.cleaned_data["teacher"].strip()
        roles = self.GROUPS.get(raw)
        if roles:
            teachers = list(
                CustomUser.objects.filter(
                    memberships__school=self.school,
                    memberships__is_active=True,
                    memberships__role__name__in=roles,
                )
                .distinct()
                .order_by("full_name")
            )
            if not teachers:
                raise forms.ValidationError("لا منسّقين في مدرستك.")
            return teachers
        try:
            pk = uuid.UUID(raw)
        except ValueError as exc:
            raise forms.ValidationError("اختر معلّماً أو مجموعة.") from exc
        # الشرطان في `filter()` واحدةٍ ليقعا على العضويّة نفسها: عضويّةٌ
        # مدرِّسةٌ في مدرسةٍ أخرى لا تُجيز تفريغَ صاحبها هنا.
        teacher = (
            CustomUser.objects.filter(
                pk=pk,
                memberships__school=self.school,
                memberships__is_active=True,
                memberships__role__name__in=EXEMPTABLE_ROLES,
            )
            .distinct()
            .first()
        )
        if teacher is None:
            raise forms.ValidationError("المعلّم المختار ليس من كادر الجدولة في مدرستك.")
        return [teacher]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("exemption_type") == "specific_period" and not cleaned.get("period_number"):
            self.add_error("period_number", "حدّد الحصص لتفريغ حصصٍ بعينها.")
        if cleaned.get("exemption_type") == "full_day":
            cleaned["period_number"] = [None]
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


class SubjectClassAssignmentForm(forms.ModelForm):
    """توزيعُ مادّةٍ على شعبةٍ بمعلّمٍ وعددِ حصص — وقودُ المولّد الوحيد.

    كان بلا شاشةٍ في المنصّة، وبابُه الوحيدُ لوحةُ Django التي لا يبلغها مديرُ
    المدرسة. والقوائمُ مقيّدةٌ بالمدرسة والعام: شعبةٌ من مدرسةٍ أخرى لا تظهر
    ولا تُقبل.
    """

    class Meta:
        model = SubjectClassAssignment
        fields = [
            "class_group",
            "subject",
            "teacher",
            "weekly_periods",
            "requires_lab",
            "parallel_group",
        ]
        labels = {
            "class_group": "الشعبة",
            "subject": "المادة",
            "teacher": "المعلم",
            "weekly_periods": "الحصص/أسبوع",
            "requires_lab": "معمل",
            "parallel_group": "مجموعة التوازي",
        }
        widgets = {
            "class_group": forms.Select(attrs={"class": "form-control", "required": True}),
            "subject": forms.Select(attrs={"class": "form-control", "required": True}),
            "teacher": forms.Select(attrs={"class": "form-control"}),
            "weekly_periods": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 35}
            ),
            "requires_lab": forms.CheckboxInput(),
            "parallel_group": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اختياري"}
            ),
        }

    def __init__(self, *args, school, year, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import ClassGroup, CustomUser

        from .models import Subject

        self.school, self.year = school, year
        self.fields["class_group"].queryset = ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True
        ).in_school_order()
        self.fields["subject"].queryset = Subject.objects.filter(school=school).order_by("name_ar")
        self.fields["teacher"].queryset = CustomUser.objects.teachers(school).order_by("full_name")
        self.fields["teacher"].required = False
        self.fields["teacher"].empty_label = "— بلا معلّم بعد —"

    def clean(self):
        cleaned = super().clean()
        cg, subj = cleaned.get("class_group"), cleaned.get("subject")
        if cg and subj:
            clash = SubjectClassAssignment.objects.filter(
                school=self.school, academic_year=self.year, class_group=cg, subject=subj
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    f"يوجد توزيعٌ لمادّة {subj.name_ar} في شعبة {cg} هذا العام — عدّله بدل إضافة آخر."
                )
        return cleaned
