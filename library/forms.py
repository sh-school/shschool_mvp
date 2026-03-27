"""library/forms.py — نماذج المكتبة المدرسية"""
import datetime

from django import forms


class BookBorrowForm(forms.Form):
    book_id = forms.UUIDField(label="الكتاب")
    user_id = forms.UUIDField(label="المستخدم")
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="تاريخ الإعادة",
    )

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if due <= datetime.date.today():
            raise forms.ValidationError("يجب أن يكون تاريخ الإعادة بعد اليوم.")
        return due


class BookAddForm(forms.Form):
    title = forms.CharField(max_length=500, label="عنوان الكتاب")
    author = forms.CharField(max_length=200, label="المؤلف")
    isbn = forms.CharField(max_length=20, required=False, label="ISBN")
    copies = forms.IntegerField(initial=1, min_value=1, label="عدد النسخ")
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="وصف الكتاب",
    )
