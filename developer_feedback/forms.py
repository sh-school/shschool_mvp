"""
Forms لميزة Developer Feedback.

- DeveloperMessageForm: إرسال رسالة جديدة (بدون مرفقات — E1)
- OnboardingConsentForm: موافقة المستخدم على الشروط القانونية
- OnboardingQuizForm: اختبار فهم قصير قبل أول استخدام
"""

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from developer_feedback.models import DeveloperMessage

# ═══════════════════════════════════════════════════════════════
# 1) DeveloperMessageForm
# ═══════════════════════════════════════════════════════════════


class DeveloperMessageForm(forms.ModelForm):
    """نموذج إرسال رسالة للمطوّر — نص فقط (E1)."""

    consent_privacy = forms.BooleanField(
        required=True,
        label=_(
            "أوافق على إرسال معلومات السياق التقني " "(الصفحة، الدور، الوقت) لتسهيل حل المشكلة"
        ),
        error_messages={
            "required": _("الموافقة على إرسال السياق إلزامية للإرسال."),
        },
    )
    context_json_raw = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = DeveloperMessage
        fields = ["message_type", "priority", "subject", "body"]
        widgets = {
            "message_type": forms.Select(attrs={"class": "form-select", "aria-required": "true"}),
            "priority": forms.Select(attrs={"class": "form-select", "aria-required": "true"}),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "maxlength": 200,
                    "aria-required": "true",
                    "placeholder": _("ملخّص قصير وواضح"),
                }
            ),
            "body": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 8,
                    "maxlength": 4000,
                    "aria-required": "true",
                    "placeholder": _(
                        "اشرح ما حدث، وما كنت تتوقعه، " "وكيف يمكن إعادة إظهار المشكلة"
                    ),
                }
            ),
        }
        labels = {
            "message_type": _("نوع الرسالة"),
            "priority": _("الأولوية"),
            "subject": _("العنوان"),
            "body": _("الوصف"),
        }
        error_messages = {
            "subject": {"required": _("العنوان مطلوب.")},
            "body": {"required": _("الوصف مطلوب.")},
        }

    def clean_subject(self):
        subject = (self.cleaned_data.get("subject") or "").strip()
        if len(subject) < 5:
            raise ValidationError(_("العنوان يجب أن يكون 5 أحرف على الأقل."))
        if len(subject) > 200:
            raise ValidationError(_("العنوان يجب ألا يتجاوز 200 حرف."))
        return subject

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if len(body) < 10:
            raise ValidationError(_("الوصف يجب أن يكون 10 أحرف على الأقل."))
        if len(body) > 4000:
            raise ValidationError(_("الوصف يجب ألا يتجاوز 4000 حرف."))
        return body

    def clean_context_json_raw(self):
        """يحوّل JSON النصي إلى dict + يُزيل المفاتيح الحساسة (PDPPL + Security)."""
        raw = self.cleaned_data.get("context_json_raw") or ""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, TypeError):
            return {}

        # قائمة المفاتيح المسموح بها فقط (whitelist)
        allowed = {
            "url_path",
            "view_name",
            "viewport",
            "role",
            "language",
            "timestamp",
        }
        cleaned = {k: v for k, v in data.items() if k in allowed}

        # منع القيم المشبوهة (tokens/passwords/keys في القيم النصية)
        blocked_substrings = (
            "token",
            "password",
            "secret",
            "jwt",
            "cookie",
            "session",
        )
        for k, v in list(cleaned.items()):
            if isinstance(v, str) and any(b in v.lower() for b in blocked_substrings):
                cleaned.pop(k, None)

        # حذف query string من url_path احتياطياً
        if "url_path" in cleaned and isinstance(cleaned["url_path"], str):
            cleaned["url_path"] = cleaned["url_path"].split("?", 1)[0]

        return cleaned

    def save(self, commit=True, user=None):
        instance: DeveloperMessage = super().save(commit=False)
        if user is not None:
            instance.user = user
        instance.context_json = self.cleaned_data.get("context_json_raw") or {}

        # consent_given_at يُسجّل الآن — روجِع عبر consent_privacy checkbox
        from django.utils import timezone

        instance.consent_given_at = timezone.now()

        if commit:
            instance.save()
        return instance


# ═══════════════════════════════════════════════════════════════
# 2) OnboardingConsentForm
# ═══════════════════════════════════════════════════════════════


class OnboardingConsentForm(forms.Form):
    """موافقة المستخدم على الشروط القانونية + إثبات التفويض الإداري."""

    accept_privacy_policy = forms.BooleanField(
        required=True,
        label=_("قرأت سياسة الخصوصية الخاصة بالميزة وأوافق عليها."),
        error_messages={
            "required": _("يجب الموافقة على سياسة الخصوصية."),
        },
    )
    accept_data_handling = forms.BooleanField(
        required=True,
        label=_(
            "أفهم أن رسائلي تُحفظ 90 يوماً ثم تُحذف تلقائياً، " "ويمكنني طلب الحذف الفوري في أي وقت."
        ),
        error_messages={
            "required": _("يجب الإقرار بفهم آلية معالجة البيانات."),
        },
    )
    no_student_data_pledge = forms.BooleanField(
        required=True,
        label=_("أتعهد بألّا أُرسل في الرسالة أي بيانات شخصية لطلاب " "(أسماء، درجات، سجلات)."),
        error_messages={
            "required": _("التعهّد بحماية بيانات الطلاب إلزامي."),
        },
    )
    admin_authorization_doc = forms.CharField(
        required=True,
        max_length=255,
        label=_("رقم تفويض مدير المدرسة (كتابي)"),
        help_text=_("أدخل رقم/مرجع التفويض الإداري الكتابي الصادر عن مدير المدرسة."),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": _("مثال: AUTH-2026-042"),
            }
        ),
    )


# ═══════════════════════════════════════════════════════════════
# 3) OnboardingQuizForm
# ═══════════════════════════════════════════════════════════════


class OnboardingQuizForm(forms.Form):
    """اختبار قصير 3 أسئلة للتأكد من فهم المستخدم لقواعد الخصوصية."""

    Q1_CHOICES = [
        ("yes", _("نعم، مسموح")),
        ("no", _("لا، ممنوع منعاً باتاً")),  # الإجابة الصحيحة
        ("maybe", _("مسموح مع موافقة ولي الأمر")),
    ]
    Q2_CHOICES = [
        ("a", _("7 أيام")),
        ("b", _("30 يوماً")),
        ("c", _("90 يوماً")),  # الإجابة الصحيحة
        ("d", _("دائماً")),
    ]
    Q3_CHOICES = [
        ("yes", _("نعم، يمكنني طلب الحذف في أي وقت")),  # الإجابة الصحيحة
        ("no", _("لا، الرسائل نهائية")),
        ("admin", _("فقط مدير المدرسة يمكنه الحذف")),
    ]

    q1 = forms.ChoiceField(
        label=_("هل يجوز إرسال رسالة تحوي اسم طالب أو درجاته؟"),
        choices=Q1_CHOICES,
        widget=forms.RadioSelect,
    )
    q2 = forms.ChoiceField(
        label=_("ما المدة التي تُحفظ فيها رسالتك قبل الحذف التلقائي؟"),
        choices=Q2_CHOICES,
        widget=forms.RadioSelect,
    )
    q3 = forms.ChoiceField(
        label=_("هل يحق لك طلب حذف رسائلك لاحقاً؟"),
        choices=Q3_CHOICES,
        widget=forms.RadioSelect,
    )

    CORRECT_ANSWERS = {"q1": "no", "q2": "c", "q3": "yes"}
    PASS_THRESHOLD = 3  # 3/3 إلزامي

    def get_score(self) -> int:
        if not self.is_valid():
            return 0
        return sum(
            1
            for key, correct in self.CORRECT_ANSWERS.items()
            if self.cleaned_data.get(key) == correct
        )

    def is_passed(self) -> bool:
        return self.get_score() >= self.PASS_THRESHOLD

    def clean(self):
        cleaned = super().clean()
        # تحقّق فقط إذا كل الحقول عُبئت (بدون أخطاء أخرى)
        if not self.errors and not self.is_passed():
            raise ValidationError(
                _("إجاباتك غير مكتملة الصحة. " "يرجى مراجعة المادة التعليمية والمحاولة مجدداً.")
            )
        return cleaned
