"""
student_affairs/forms.py — نماذج إدخال شؤون الطلاب
يتبع نمط المشروع: forms.Form (ليس ModelForm)
"""

import re

from django import forms

from core.models.academic import ClassGroup

from .models import StudentActivity, StudentTransfer

# ═════════════════════════════════════════════════════════════════════
# إضافة طالب جديد
# ═════════════════════════════════════════════════════════════════════


class StudentAddForm(forms.Form):
    """نموذج إضافة طالب جديد — يُنشئ 4 سجلات (User + Profile + Membership + Enrollment)."""

    national_id = forms.CharField(
        max_length=20, label="الرقم الوطني",
        error_messages={"required": "الرقم الوطني مطلوب."},
    )
    full_name = forms.CharField(
        max_length=200, label="الاسم الكامل",
        error_messages={"required": "اسم الطالب مطلوب."},
    )
    gender = forms.ChoiceField(
        choices=[("M", "ذكر"), ("F", "أنثى")],
        label="الجنس",
    )
    birth_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False, label="تاريخ الميلاد",
    )
    phone = forms.CharField(max_length=20, required=False, label="الجوال")
    email = forms.EmailField(required=False, label="البريد الإلكتروني")
    grade = forms.ChoiceField(choices=ClassGroup.GRADES, label="الصف")
    section = forms.CharField(max_length=10, label="الشعبة")

    def clean_national_id(self):
        nid = self.cleaned_data["national_id"].strip()
        if not re.match(r"^\d{5,20}$", nid):
            raise forms.ValidationError("الرقم الوطني يجب أن يكون أرقاماً فقط (5-20 رقم).")
        return nid

    def clean_full_name(self):
        name = self.cleaned_data["full_name"].strip()
        if len(name) < 4:
            raise forms.ValidationError("الاسم قصير جداً.")
        return name


# ═════════════════════════════════════════════════════════════════════
# إضافة ولي أمر جديد + ربطه بطالب
# ═════════════════════════════════════════════════════════════════════


class ParentAddForm(forms.Form):
    """نموذج إضافة ولي أمر جديد وربطه بطالب في نفس الوقت."""

    national_id = forms.CharField(
        max_length=20, label="الرقم الوطني",
        error_messages={"required": "الرقم الوطني مطلوب."},
    )
    full_name = forms.CharField(
        max_length=200, label="الاسم الكامل",
        error_messages={"required": "اسم ولي الأمر مطلوب."},
    )
    phone = forms.CharField(max_length=20, required=False, label="الجوال")
    email = forms.EmailField(required=False, label="البريد الإلكتروني")
    relationship = forms.ChoiceField(
        choices=[("father", "الأب"), ("mother", "الأم"), ("guardian", "الوصي"), ("other", "أخرى")],
        label="صلة القرابة",
    )
    student_id = forms.UUIDField(
        label="الطالب",
        error_messages={"required": "يرجى اختيار الطالب."},
    )

    def clean_national_id(self):
        nid = self.cleaned_data["national_id"].strip()
        if not re.match(r"^\d{5,20}$", nid):
            raise forms.ValidationError("الرقم الوطني يجب أن يكون أرقاماً فقط (5-20 رقم).")
        return nid

    def clean_full_name(self):
        name = self.cleaned_data["full_name"].strip()
        if len(name) < 4:
            raise forms.ValidationError("الاسم قصير جداً.")
        return name


# ═════════════════════════════════════════════════════════════════════
# تعديل بيانات طالب
# ═════════════════════════════════════════════════════════════════════


class StudentEditForm(forms.Form):
    """تعديل بيانات طالب موجود."""

    full_name = forms.CharField(max_length=200, label="الاسم الكامل")
    phone = forms.CharField(max_length=20, required=False, label="الجوال")
    email = forms.EmailField(required=False, label="البريد الإلكتروني")
    grade = forms.ChoiceField(choices=ClassGroup.GRADES, label="الصف")
    section = forms.CharField(max_length=10, label="الشعبة")
    birth_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False, label="تاريخ الميلاد",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False, label="ملاحظات",
    )


# ═════════════════════════════════════════════════════════════════════
# طلب انتقال
# ═════════════════════════════════════════════════════════════════════


class TransferForm(forms.Form):
    """تسجيل طلب انتقال طالب — وارد أو صادر."""

    student_id = forms.UUIDField(
        error_messages={"required": "يرجى اختيار الطالب."},
    )
    direction = forms.ChoiceField(
        choices=StudentTransfer.DIRECTION_CHOICES,
        label="اتجاه الانتقال",
    )
    other_school_name = forms.CharField(
        max_length=200, label="المدرسة الأخرى",
        error_messages={"required": "اسم المدرسة الأخرى مطلوب."},
    )
    from_grade = forms.CharField(max_length=3, required=False, label="الصف (من)")
    to_grade = forms.CharField(max_length=3, required=False, label="الصف (إلى)")
    transfer_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ الانتقال",
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=1000, required=False, label="السبب",
    )


class TransferReviewForm(forms.Form):
    """مراجعة طلب انتقال — موافقة أو رفض."""

    action = forms.ChoiceField(
        choices=[("approved", "موافقة"), ("rejected", "رفض"), ("completed", "مكتمل")],
        label="القرار",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        max_length=500, required=False, label="ملاحظات",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == "rejected" and not cleaned.get("notes"):
            raise forms.ValidationError("يجب ذكر سبب الرفض.")
        return cleaned


# ═════════════════════════════════════════════════════════════════════
# تسجيل نشاط / إنجاز
# ═════════════════════════════════════════════════════════════════════


class ActivityForm(forms.Form):
    """تسجيل نشاط أو إنجاز طلابي."""

    student_id = forms.UUIDField(
        error_messages={"required": "يرجى اختيار الطالب."},
    )
    activity_type = forms.ChoiceField(
        choices=StudentActivity.TYPE_CHOICES,
        label="نوع النشاط",
    )
    title = forms.CharField(
        max_length=200, label="العنوان",
        error_messages={"required": "عنوان النشاط مطلوب."},
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000, required=False, label="الوصف",
    )
    scope = forms.ChoiceField(
        choices=StudentActivity.SCOPE_CHOICES,
        label="النطاق",
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="التاريخ",
    )
    attachment = forms.FileField(required=False, label="مرفق")
