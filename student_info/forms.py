"""استمارةُ الملاحظة — والجهةُ ليست حقلاً حرّاً."""

from django import forms
from django.utils import timezone

from student_info.access import writable_categories
from student_info.models import NOTE_CATEGORIES, StudentNote


class StudentNoteForm(forms.ModelForm):
    class Meta:
        model = StudentNote
        fields = ["category", "title", "body", "occurred_on"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "maxlength": 160}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "occurred_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "category": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        """لا تُعرض في القائمة إلّا الخاناتُ التي يحقّ له الكتابةُ فيها.

        وهذا ليس تجميلاً: `clean_category` يُعيد الفحص، فالقائمةُ المحدودة
        راحةٌ للمستخدم والحارسُ في مكانٍ آخر.
        """
        super().__init__(*args, **kwargs)
        self.user = user
        allowed = set(writable_categories(user)) if user else set()
        self.fields["category"].choices = [(k, v) for k, v in NOTE_CATEGORIES if k in allowed]
        self.fields["occurred_on"].initial = timezone.localdate()

    def clean_category(self):
        category = self.cleaned_data["category"]
        allowed = set(writable_categories(self.user)) if self.user else set()
        if category not in allowed:
            raise forms.ValidationError("لا تكتب في خانةِ جهةٍ لست منها.")
        return category

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if len(body) < 3:
            raise forms.ValidationError("اكتب نصّ الملاحظة.")
        return body
