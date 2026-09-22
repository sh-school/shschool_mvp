"""بوّابةُ موافقة وليّ الأمر (PDPPL 13/2016) — سياسةٌ واحدة يقرؤها الوسيطُ والـAPI.

كان الوسيطُ يسأل «ألَه عضويّةُ وليّ أمر؟» فيحجب **كلَّ** المنصّة حتّى يوافق. فمعلّمٌ
ابنُه في المدرسة يُحوَّل عن لوحته إلى صفحة الموافقة، وصفحةُ الموافقة نفسُها تحت
``/parents/`` التي تحرسها بوّابةٌ بالدور الحاكم — فيُردّ ٤٠٣، ولا يوافق، ولا يعمل.

وقرارُ المالك (2026-09-16): **الكادرُ الذي هو وليُّ أمرٍ لا يُحجب عن عمله**. فالموافقةُ
تحمي معالجةَ بيانات الأبناء لصالح وليّ الأمر — بوّابتَه وواجهتَه البرمجيّة — لا عملَ
الموظّف. فتظهر له صفحةُ الموافقة حين يفتح شاشاتِ وليّ الأمر وحدَها. ووليُّ الأمر
الخالصُ باقٍ على حاله حرفاً: كلُّ مسارٍ عدا المستثنى.

والترتيبُ مقصود: السؤالُ الرخيصُ أوّلاً. فالكادرُ على مسارٍ غيرِ موجَّهٍ لوليّ الأمر
يُجاب عنه من الدور الحاكم المحفوظ على الكائن، بلا استعلام. والعضويّةُ تُقرأ من
``active_memberships`` المحفوظة أيضاً — لا من ``has_role`` الذي يسأل القاعدةَ كلَّ مرّة.

والمعاملاتُ ``Any`` لا ``CustomUser``: المستخدمُ قد يكون ``AnonymousUser``، ودوالُّ
النموذج بلا أنواعٍ فتُعدّ استدعاءاتٍ غيرَ مُنمَّطة تحت إعداد mypy الصارم على ``core``.
"""

from __future__ import annotations

from typing import Any

#: ما لا يُحجب عن أحد — كما كان في الوسيط حرفاً.
EXEMPT_PREFIXES: tuple[str, ...] = (
    "/auth/",
    "/parents/consent/",
    "/static/",
    "/media/",
    "/admin/",
)

#: الشاشاتُ التي تعالج بياناتِ الأبناء لصالح وليّ الأمر: البوّابةُ وواجهتُها البرمجيّة.
PARENT_FACING_PREFIXES: tuple[str, ...] = ("/parents/", "/api/v1/parent/")

#: شاشةُ كادرٍ تحت ``/parents/`` — ربطُ الأولياء بالطلبة (المديرُ والإدارة) — لا تُحجب
#: عن كادرٍ هو وليُّ أمرٍ أيضاً.
STAFF_SCREENS_UNDER_PARENTS: tuple[str, ...] = ("/parents/admin/",)


def is_parent_facing(path: str) -> bool:
    """أهذا المسارُ من شاشات وليّ الأمر؟"""
    return path.startswith(PARENT_FACING_PREFIXES) and not path.startswith(
        STAFF_SCREENS_UNDER_PARENTS
    )


def holds_parent_membership(user: Any) -> bool:
    """أله عضويّةُ وليّ أمرٍ نشطة — أيّاً كان دورُه الحاكم؟ بلا استعلامٍ جديد.

    وهو منحُ بوّابة وليّ الأمر لمن ليس دورُه الحاكمُ فيها: المعلّمُ والممرّضُ وسائرُ
    الكادر ممّن له ابنٌ في المدرسة يدخلها ليرى أبناءه وحدَهم — فالبوّابةُ لا تعرض إلّا
    ما يربطه ``ParentStudentLink`` بصاحب الطلب.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.has_parent_membership)


def needs_parent_consent(user: Any) -> bool:
    """وليُّ أمرٍ (بأيّ عضويّة) لم يوافق بعد."""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.consent_given_at is None and holds_parent_membership(user)


def consent_blocks(user: Any, path: str) -> bool:
    """أيُردّ هذا الطلبُ إلى صفحة الموافقة؟

    وليُّ الأمر الخالص: كلُّ مسارٍ عدا المستثنى (كما كان).
    الكادرُ الذي هو وليُّ أمرٍ أيضاً: شاشاتُ وليّ الأمر وحدَها.

    والكادرُ هو ``is_staff_member()`` — الدورُ الحاكم، وهو ما تقرؤه لوحةُ التحكّم
    وبوّاباتُ الوحدات، فيتّسق الحجبُ مع الشاشات التي يُعطاها المستخدمُ فعلاً.
    """
    if path.startswith(EXEMPT_PREFIXES):
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_staff_member() and not is_parent_facing(path):
        return False
    return needs_parent_consent(user)
