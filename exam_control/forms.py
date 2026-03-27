"""exam_control/forms.py — نماذج لجان الاختبارات"""
from django.conf import settings
from django import forms

from .models import ExamSession, ExamStaffAssignment, ExamIncident


class ExamSessionForm(forms.Form):
    name = forms.CharField(max_length=200, label="اسم دورة الاختبار")
    session_type = forms.ChoiceField(
        choices=ExamSession.SESSION_TYPES,
        initial="final",
        label="نوع الاختبار",
    )
    academic_year = forms.CharField(
        max_length=9,
        initial=getattr(settings, "CURRENT_ACADEMIC_YEAR", ""),
        label="العام الدراسي",
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="تاريخ البدء",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
        label="تاريخ الانتهاء",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البدء.")
        return cleaned


class StaffAssignmentForm(forms.Form):
    staff_id = forms.UUIDField(label="الموظف")
    role = forms.ChoiceField(
        choices=ExamStaffAssignment.ROLES,
        initial="supervisor",
        label="الدور",
    )
    room_id = forms.UUIDField(required=False, label="القاعة")


class RoomForm(forms.Form):
    name = forms.CharField(max_length=100, label="اسم القاعة")
    students_count = forms.IntegerField(min_value=0, initial=0, label="عدد الطلاب")


class IncidentForm(forms.Form):
    student_id = forms.UUIDField(required=False, label="الطالب")
    room_id = forms.UUIDField(required=False, label="القاعة")
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label="وصف الحادثة",
    )
    incident_type = forms.ChoiceField(
        choices=ExamIncident.TYPES,
        initial="other",
        label="نوع الحادثة",
    )
    severity = forms.ChoiceField(
        choices=ExamIncident.SEVERITY,
        initial=1,
        label="الخطورة",
    )
    injuries = forms.CharField(max_length=500, required=False, label="الإصابات")
    action_taken = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        label="الإجراء المتخذ",
    )
    recommendations = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
        label="التوصيات",
    )
