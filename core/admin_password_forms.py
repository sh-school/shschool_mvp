"""صفحتا كلمة المرور في الإدارة بالعربيّة — تعديل المستخدم، وتغيير كلمته (OWN-19).

نصوصُ جانغو 5.2 في هاتين الصفحتين بلا ترجمةٍ عربيّة في كتالوجه: «Reset password»، و«Raw passwords are not stored…»،
وتسميتا «salt» و«hash» في ملخّص التجزئة، و«Password-based authentication: Enabled/Disabled» — وجملةٌ منها
(«If disabled, the current password for this user will be lost.») حرفيّةٌ في الشيفرة بلا `gettext` أصلاً،
فلا يُترجمها كتالوجٌ مهما اكتمل.

ولا ينفع ملفُّ `.po` هنا (`compilemessages` في preDeploy وقرصُه غيرُ قرص الخدمة)، فالتعريبُ في النموذج والأداة:
يُترجَم النصُّ إن جاء إنجليزيّاً كما هو، وما ترجمه جانغو يبقى ترجمتَه — فإن أكمل كتالوجَه غلبت ترجمتُه.

يحرسه `tests/test_admin_password_arabic.py`: كلُّ نصٍّ إنجليزيٍّ من هذه الصفحات غائبٌ عن الصفحتين المرسومتين.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.forms import (
    AdminPasswordChangeForm,
    ReadOnlyPasswordHashWidget,
    UserChangeForm,
)

#: النصُّ الإنجليزيُّ كما يُخرجه جانغو ← العربيّة. المفتاحُ نصُّه الحرفيُّ (بما فيه الفاصلةُ العليا ’).
ARABIC = {
    "salt": "الملح",
    "hash": "التجزئة",
    "checksum": "المجموع الاختباري",
    "variety": "النوع",
    "version": "الإصدار",
    "memory cost": "كلفة الذاكرة",
    "time cost": "كلفة الزمن",
    "parallelism": "التوازي",
    "work factor": "معامل العمل",
    "block size": "حجم الكتلة",
    "Reset password": "إعادة تعيين كلمة المرور",
    "Set password": "تعيين كلمة المرور",
    "No password set.": "لا توجد كلمة مرور.",
    "Invalid password format or unknown hashing algorithm.": "صيغة كلمة المرور غير صحيحة، أو خوارزمية التجزئة غير معروفة.",
    "Raw passwords are not stored, so there is no way to see the user’s password.": (
        "لا تُخزَّن كلمات المرور كما كُتبت، فلا سبيل إلى عرض كلمة مرور المستخدم."
    ),
    "Enable password-based authentication for this user by setting a password.": (
        "فعِّل الدخول بكلمة مرور لهذا المستخدم بتعيين كلمة مرورٍ له."
    ),
    "Password-based authentication": "الدخول بكلمة مرور",
    "Enabled": "مفعّل",
    "Disabled": "معطّل",
}

#: تحذيرُ الحفظ بلا كلمة مرور — نصُّ جانغو حرفيٌّ بلا gettext، فهو نصُّه لا ترجمتُه.
USABLE_PASSWORD_HELP = (
    "هل يستطيع المستخدم الدخولَ بكلمة مرور؟ إن عُطّل فقد يدخل بوسيلةٍ أخرى، كالدخول الموحَّد."
    '<ul id="id_unusable_warning" class="messagelist"><li class="warning">'
    "إن عُطّل فستُفقد كلمةُ المرور الحاليّةُ لهذا المستخدم.</li></ul>"
)


def arabic(text: object) -> Any:
    """العربيّةُ إن كان النصُّ إنجليزيّاً لجانغو بلا ترجمة، وإلا فالنصُّ كما هو (ترجمةُ جانغو تغلب)."""
    return ARABIC.get(str(text), text)


class ArabicPasswordHashWidget(ReadOnlyPasswordHashWidget):
    """ملخّصُ تجزئة كلمة المرور وزرُّ إعادة تعيينها بالعربيّة."""

    def get_context(self, name: str, value: Any, attrs: Any) -> dict[str, Any]:
        context: dict[str, Any] = super().get_context(name, value, attrs)
        context["summary"] = [
            {**entry, "label": arabic(entry["label"])} for entry in context["summary"]
        ]
        context["button_label"] = arabic(context["button_label"])
        return context


class ArabicUserChangeForm(UserChangeForm):
    """نموذجُ تعديل المستخدم: حقلُ كلمة المرور المقروءُ بأداةٍ ونصِّ مساعدةٍ عربيّين."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        password = self.fields.get("password")
        if password is not None:
            password.widget = ArabicPasswordHashWidget()
            password.help_text = arabic(password.help_text)


class ArabicAdminPasswordChangeForm(AdminPasswordChangeForm):
    """نموذجُ تغيير كلمة مرور المستخدم: «الدخول بكلمة مرور» ونصُّه بالعربيّة."""

    usable_password_help_text = USABLE_PASSWORD_HELP

    def __init__(self, user: Any, *args: Any, **kwargs: Any) -> None:
        super().__init__(user, *args, **kwargs)
        field = self.fields.get("usable_password")
        if field is not None:
            field.label = arabic(field.label)
            field.choices = [("true", arabic("Enabled")), ("false", arabic("Disabled"))]  # type: ignore[attr-defined]
