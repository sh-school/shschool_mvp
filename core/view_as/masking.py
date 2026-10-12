"""قناعُ الدور المعروض على كائن المستخدم في الطلب — في الذاكرة وحدَها، ولا يُحفظ.

`request.user` يبقى حسابَ المطوّر (هويّتُه في كلّ كتابةٍ ومفتاحٍ أجنبيّ)، ويُحسب له:

- **عضويّةٌ حاكمةٌ معروضة** غيرُ محفوظة: مدرستُه الحقيقيّة (فلا يتغيّر عزلُ المدرسة ولا سياقُ RLS) والدورُ المعروض.
  فكلُّ ما يقرأ `get_role()` و`active_membership` و`has_role` يرى الدورَ المعروض.
- **`is_superuser` و`is_staff` مطفأتان**: 119 فحصاً في 60 ملفّاً تمرّر المشرفَ الأعلى بلا دور، وأغلبُ حسابات
  المطوّر في الإنتاج superuser — فبلا هذا لكانت المعاينةُ شكلاً لا صلاحيّات («دورٌ لا يملك الصلاحية يُرفض»).
  وحفظُ الكائن كاملاً مرفوضٌ في `CustomUser.save` كي لا تُكتب الرايتان المطفأتان في القاعدة.
"""

from __future__ import annotations

from typing import Any

from core.models.access import Membership, Role


def mask_user(user: Any, role: str) -> None:
    """يُلبس `user` الدورَ المعروض في مدرسته الحقيقيّة — `user` كائنٌ محمَّلٌ لهذا الطلب وحدَه."""
    real = user.active_membership
    school = real.school if real is not None else None
    role_obj = Role.objects.filter(school=school, name=role).first() if school is not None else None
    if role_obj is None:
        # مدرسةٌ لم يُنشأ فيها صفُّ هذا الدور بعد: دورٌ غيرُ محفوظٍ يكفي لكلّ ما يقرأ اسمَه.
        role_obj = Role(school=school, name=role)
    masked = Membership(user=user, school=school, role=role_obj, is_active=True)
    user.__dict__["_view_as_membership"] = masked
    user.__dict__["_view_as_role"] = role
    user.is_superuser = False
    user.is_staff = False
