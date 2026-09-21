"""staff_affairs/forms.py — نماذج إدخال شؤون الموظفين."""

from typing import Any

from django import forms

from core.validators import FileTypeValidator

from .models import (
    ABSENCE_TYPES,
    EXCEPTION_TYPES,
    LEAVE_TYPES,
    PERMIT_TYPES,
    STAFF_ATTENDANCE_STATUS,
)


class LeaveRequestForm(forms.Form):
    """طلب إجازة جديد."""

    staff_id = forms.UUIDField(error_messages={"required": "يرجى اختيار الموظف."})
    leave_type = forms.ChoiceField(choices=LEAVE_TYPES, label="نوع الإجازة")
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ البداية",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ النهاية",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=1000,
        label="السبب",
    )
    attachment = forms.FileField(
        required=False,
        label="مرفق",
        validators=[FileTypeValidator(allowed_types="document", max_size_mb=10)],
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
        if start and end:
            cleaned["days_count"] = (end - start).days + 1
        return cleaned


class LeaveReviewForm(forms.Form):
    """مراجعة طلب إجازة — موافقة أو رفض."""

    action = forms.ChoiceField(
        choices=[("approved", "موافقة"), ("rejected", "رفض")],
        label="القرار",
    )
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        max_length=500,
        required=False,
        label="سبب الرفض",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "rejected" and not cleaned.get("rejection_reason"):
            raise forms.ValidationError("يجب ذكر سبب الرفض.")
        return cleaned


class StaffAppointmentForm(forms.Form):
    """تعيينُ منتسبٍ جديد — والمرجعُ حقلٌ لا خانةَ اختيار.

    الأدوارُ والأقسامُ تُملأ من قاعدة المدرسة لا من ثوابتَ في الشيفرة، والقسمُ
    يُقبل للأدوار التدريسيّة وحدَها (يحرسه النموذجُ كذلك).
    """

    national_id = forms.CharField(max_length=20, label="الرقم الشخصي")
    full_name = forms.CharField(max_length=200, label="الاسم الكامل")
    role_name = forms.ChoiceField(label="الدور", choices=())
    department = forms.ChoiceField(label="القسم الأكاديمي", choices=(), required=False)
    employee_number = forms.CharField(max_length=32, required=False, label="الرقم الوظيفي")
    email = forms.EmailField(required=False, label="البريد الإلكتروني")
    phone = forms.CharField(max_length=20, required=False, label="الجوال")
    joined_on = forms.DateField(
        label="تاريخ الالتحاق", widget=forms.DateInput(attrs={"type": "date"})
    )
    reference = forms.CharField(max_length=200, label="مرجع قرار التعيين")
    note = forms.CharField(max_length=200, required=False, label="ملاحظة")

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models.access import ALL_STAFF_ROLES, Role
        from core.models.department import Department

        # كلُّ أدوار الكادر الرسميّة لا الموجودةَ في المدرسة وحدَها: أوّلُ ممرّضٍ
        # يُعيَّن لا يجد دورَه في القائمة لو قُرئت من القاعدة، فيتعذّر تعيينُه.
        self.fields["role_name"].choices = [("", "— اختر الدور —")] + [
            (name, label) for name, label in Role.ROLES if name in ALL_STAFF_ROLES
        ]
        self.fields["department"].choices = [("", "— بلا قسم —")] + [
            (str(d.id), d.name)
            for d in Department.objects.filter(school=school, is_active=True).order_by("sort_order")
        ]
        for field in self.fields.values():
            css = "form-control"
            field.widget.attrs.setdefault("class", css)


class StaffDepartureForm(forms.Form):
    """مغادرةُ الكادر — تاريخٌ وسببٌ ومرجع، والمرجعُ لازم."""

    on = forms.DateField(label="تاريخ المغادرة", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.ChoiceField(label="السبب", choices=())
    reference = forms.CharField(max_length=200, label="مرجع القرار")
    note = forms.CharField(max_length=200, required=False, label="ملاحظة")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models.access import DEPARTURE_REASONS

        self.fields["reason"].choices = DEPARTURE_REASONS
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class StaffPersonForm(forms.Form):
    """بياناتُ الشخص والرخصة — تُصحَّح في مكانها، وكلُّ تصحيحٍ يُختم بصاحبه."""

    full_name = forms.CharField(max_length=200, label="الاسم الكامل")
    employee_number = forms.CharField(max_length=32, required=False, label="الرقم الوظيفي")
    email = forms.EmailField(required=False, label="البريد الإلكتروني")
    phone = forms.CharField(max_length=20, required=False, label="الجوال")
    nationality = forms.CharField(max_length=100, required=False, label="الجنسية")
    service_start_date = forms.DateField(
        required=False, label="تاريخ المباشرة", widget=forms.DateInput(attrs={"type": "date"})
    )
    professional_license_number = forms.CharField(
        max_length=50, required=False, label="رقم الرخصة المهنية"
    )
    professional_license_expiry = forms.DateField(
        required=False, label="انتهاء الرخصة", widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class StaffEmploymentForm(forms.Form):
    """بياناتُ الوظيفة في هذه المدرسة — لا الدور: تغييرُه قرارُ تعيينٍ لا تصحيح."""

    job_title = forms.CharField(
        max_length=100,
        required=False,
        label="المسمّى الوظيفي (كما في اللوائح)",
        help_text="يُكتب كما ورد في كشف الكادر — لا يُجتهد فيه",
    )
    department = forms.ChoiceField(label="القسم الأكاديمي", choices=(), required=False)
    joined_at = forms.DateField(
        label="تاريخ الالتحاق", widget=forms.DateInput(attrs={"type": "date"})
    )
    appointment_reference = forms.CharField(
        max_length=200, required=False, label="مرجع قرار التعيين"
    )
    appointment_note = forms.CharField(max_length=200, required=False, label="ملاحظة")

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models.department import Department

        self.fields["department"].choices = [("", "— بلا قسم —")] + [
            (str(d.id), d.name)
            for d in Department.objects.filter(school=school, is_active=True).order_by("sort_order")
        ]
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class PermitRequestForm(forms.Form):
    """نموذج 02: طلب تأخير / استئذان / خروج مبكر — للموظّف نفسه.

    الشكلُ وحدَه هنا؛ حدودُ السياسة (4.2 و4.3 و4.4) في ``PermitService.submit``.
    """

    permit_type = forms.ChoiceField(choices=PERMIT_TYPES, label="نوع الطلب")
    date = forms.DateField(label="التاريخ")
    start_time = forms.TimeField(label="من الساعة")
    end_time = forms.TimeField(label="إلى الساعة")
    reason = forms.CharField(max_length=500, label="سبب الطلب")


class ExceptionRequestForm(forms.Form):
    """نموذج 03: طلبُ استثناء التأخير الصباحيّ أو الخروج المبكر — إلى مدير المدرسة.

    الشكلُ وحدَه هنا؛ الحدودُ (ساعاتُ الدوام، والمرفقُ) في ``ExceptionService.submit``.
    """

    exception_type = forms.ChoiceField(choices=EXCEPTION_TYPES, label="نوع الاستثناء")
    start_date = forms.DateField(label="من تاريخ")
    end_date = forms.DateField(label="إلى تاريخ")
    boundary_time = forms.TimeField(label="الساعة")
    content = forms.CharField(max_length=1000, label="محتوى الطلب")
    #: م-31: المرفقُ إلزاميّ — والخدمةُ تفحصه (النوع والحجم) وترفض غيابَه باسم النموذج.
    evidence_file = forms.FileField(required=False, label="المرفق (ما يثبت الحاجة)")
    evidence = forms.CharField(max_length=300, required=False, label="وصف المرفق")


class ExceptionDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "موافق"), ("reject", "غير موافق")])
    feedback = forms.CharField(max_length=500, required=False)


class AssignmentForm(forms.Form):
    """تكليفُ موظّفٍ بأعباء وظيفة المكلِّف (م-43 من النظام الوظيفيّ)."""

    assignee = forms.UUIDField(error_messages={"required": "اختر من تكلّفه."})
    start_date = forms.DateField(label="من تاريخ")
    end_date = forms.DateField(label="إلى تاريخ")
    reason = forms.CharField(max_length=300, label="سبب التكليف")
    reference = forms.CharField(max_length=200, required=False, label="مرجع القرار")


class AttendanceExemptionForm(forms.Form):
    """إعفاءُ موظّفٍ أو أكثر من الرصد اليوميّ — بلا سببٍ (بيانةٌ صحّيّةٌ محتملة)."""

    staff = forms.MultipleChoiceField(
        choices=[], error_messages={"required": "اختر موظّفاً واحداً على الأقلّ."}
    )
    start_date = forms.DateField(label="من تاريخ")
    end_date = forms.DateField(label="إلى تاريخ", required=False)
    reference = forms.CharField(max_length=200, required=False, label="مرجع القرار")

    def __init__(self, *args: Any, candidates: Any = (), **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["staff"].choices = [(str(c.pk), c.full_name) for c in candidates]


class PermitReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "اعتماد"), ("reject", "رفض")])
    rejection_reason = forms.CharField(max_length=300, required=False)
    written_approval = forms.CharField(max_length=300, required=False)


class AttendanceMarkForm(forms.Form):
    staff_id = forms.UUIDField()
    date = forms.DateField()
    status = forms.ChoiceField(choices=STAFF_ATTENDANCE_STATUS)
    check_in = forms.TimeField(required=False)
    check_out = forms.TimeField(required=False)
    absence_type = forms.ChoiceField(choices=[("", ""), *ABSENCE_TYPES], required=False)
    accepted_excuse = forms.CharField(max_length=300, required=False)
