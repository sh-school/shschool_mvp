"""نماذجُ إدخال طلبات الأولياء وشكاواهم (W-20261001-019؛ 01 و02 و05 و06 و08).

نموذجٌ واحدٌ بحقولٍ مشروطةٍ بالنوع: الحقلُ الذي لا يخصّ النوعَ يُهمَل فلا يُحفظ شيءٌ لا يلزم (الحدُّ الأدنى
من البيانات). لا رقمَ شخصيّاً لوليّ الأمر في أيّ حقل.
"""

from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone

from .guardian_request_models import GuardianRequest as GR  # noqa: N817 — اختصارُ ثوابت الأنواع

_phone = RegexValidator(
    regex=r"^\+?[\d\s\-]{7,20}$",
    message="رقم الجوال غير صحيح — استخدم صيغة دولية مثل +97455xxxxxx",
)

#: ما يلزم كلَّ نوعٍ فوق الحقول المشتركة؛ وما لا يرد هنا يبقى اختيارياً أو مُهملاً.
REQUIRED_BY_KIND = {
    GR.KIND_REQUEST: ("student_id", "guardian_name", "body"),
    GR.KIND_COMPLAINT: ("student_id", "guardian_name", "body"),
    GR.KIND_STATEMENT: ("student_id", "body"),
    GR.KIND_CONTACT_CHANGE: ("student_id", "guardian_name", "new_phone"),
    GR.KIND_HOTLINE: (
        "call_reference",
        "call_at",
        "caller_capacity",
        "directed_to",
        "receiver_name",
        "body",
    ),
}

#: الحقولُ التي يحملها كلُّ نوع (لقالبٍ واحدٍ يُظهر الأقسام المناسبة، وللخدمة تُمرَّر المحمولةُ وحدَها).
FIELDS_BY_KIND = {
    GR.KIND_REQUEST: ("student_id", "guardian_name", "request_date", "body", "contact_phone"),
    GR.KIND_COMPLAINT: ("student_id", "guardian_name", "request_date", "body", "contact_phone"),
    GR.KIND_STATEMENT: ("student_id", "guardian_name", "request_date", "body", "contact_phone"),
    GR.KIND_CONTACT_CHANGE: (
        "student_id",
        "guardian_name",
        "request_date",
        "current_phone",
        "new_phone",
        "body",
    ),
    GR.KIND_HOTLINE: (
        "call_reference",
        "call_at",
        "caller_capacity",
        "caller_capacity_note",
        "directed_to",
        "directed_note",
        "receiver_name",
        "guardian_name",
        "related_students_text",
        "request_date",
        "body",
    ),
}


class GuardianRequestForm(forms.Form):
    student_id = forms.UUIDField(required=False)
    guardian_name = forms.CharField(max_length=200, required=False)
    request_date = forms.DateField(required=False)
    body = forms.CharField(max_length=3000, required=False)
    contact_phone = forms.CharField(max_length=20, required=False, validators=[_phone])
    current_phone = forms.CharField(max_length=20, required=False, validators=[_phone])
    new_phone = forms.CharField(max_length=20, required=False, validators=[_phone])
    related_students_text = forms.CharField(max_length=500, required=False)
    call_reference = forms.CharField(max_length=60, required=False)
    call_at = forms.DateTimeField(required=False)
    caller_capacity = forms.ChoiceField(choices=GR.CAPACITY_CHOICES, required=False)
    caller_capacity_note = forms.CharField(max_length=200, required=False)
    directed_to = forms.ChoiceField(choices=GR.DIRECT_CHOICES, required=False)
    directed_note = forms.CharField(max_length=200, required=False)
    receiver_name = forms.CharField(max_length=200, required=False)

    def __init__(self, *args, kind: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind

    def clean(self):
        data = super().clean()
        for name in REQUIRED_BY_KIND[self.kind]:
            if not data.get(name) and name not in self.errors:
                self.add_error(name, "هذا الحقل مطلوب.")
        if self.kind == GR.KIND_HOTLINE:
            for choice, note in (
                ("caller_capacity", "caller_capacity_note"),
                ("directed_to", "directed_note"),
            ):
                if data.get(choice) == "other" and not data.get(note):
                    self.add_error(note, "وضّح عند اختيار «غير ذلك».")
        data["request_date"] = data.get("request_date") or timezone.localdate()
        return data

    def service_fields(self) -> dict:
        """الحقولُ الخاصّة بالنوع وحدَها، بأسماء أعمدة النموذج (الطالبُ يُمرَّر كائناً من العرض)."""
        keep = [n for n in FIELDS_BY_KIND[self.kind] if n != "student_id"]
        return {n: self.cleaned_data.get(n) or "" for n in keep} | {
            "request_date": self.cleaned_data["request_date"],
            **({"call_at": self.cleaned_data["call_at"]} if self.kind == GR.KIND_HOTLINE else {}),
        }
