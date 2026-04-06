"""transport/forms.py — نماذج النقل المدرسي"""

from django import forms


class BusForm(forms.Form):
    bus_number = forms.CharField(max_length=20, label="رقم الحافلة")
    driver_name = forms.CharField(max_length=200, label="اسم السائق")
    driver_phone = forms.CharField(max_length=20, label="جوال السائق")
    capacity = forms.IntegerField(min_value=1, max_value=100, label="طاقة الاستيعاب")
    karwa_id = forms.CharField(max_length=50, required=False, label="معرّف كروا")
    gps_link = forms.URLField(required=False, label="رابط GPS")

    def clean_driver_phone(self):
        phone = self.cleaned_data["driver_phone"]
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 7:
            raise forms.ValidationError("رقم الجوال غير صحيح.")
        return phone


class RouteAreaForm(forms.Form):
    area_name = forms.CharField(max_length=200, label="اسم المنطقة")
    students = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="الطلاب",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, student_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student_choices:
            self.fields["students"].choices = student_choices
