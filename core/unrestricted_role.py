"""مطوّرُ المنصّة لا حظرَ عليه في أيّ صفحة (قرارُ المالك D-118م، W-20261002-012).

كان `platform_developer` يُدرَج في قوائم أدوار الصفحات واحدةً واحدةً، فتسقط عنه كلُّ صفحةٍ لم تُذكره،
ثمّ جاء استبعادُه الصريح من `/analytics/` (D-98م) فألغاه D-118م. والقرارُ للصفحات كلِّها، فلا يُترك
لكلّ قائمةٍ أن تتذكّره: بوّاباتُ الدخول المركزيّة (`role_required`، `department_scoped`، قدرات
`capabilities`، بوّابةُ الوحدات، `navigation.can_open`) تمرّره بهذه الدالّة وحدَها.

**هذا حقُّ دخولِ الصفحة لا نطاقُ البيانات**: عزلُ المدرسة (RLS و`request.school`) وقيودُ البيانات
الأخرى لا تتغيّر به.
"""

from __future__ import annotations

from typing import Any

PLATFORM_DEVELOPER = "platform_developer"


def has_unrestricted_role(user: Any) -> bool:
    """أدورُ هذا المستخدم الحاكمُ مطوّرُ المنصّة؟ — يمرّ بوّابات الصفحات كلَّها."""
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and user.get_role() == PLATFORM_DEVELOPER
    )
