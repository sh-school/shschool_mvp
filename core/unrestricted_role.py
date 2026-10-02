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


#: قدراتٌ يُستثنى منها المطوّرُ بقرارٍ مباشرٍ من المالك رغم «لا حظرَ في أيّ صفحة» (D-128م):
#: لا يُدخل ولا يعتمد رصدَ غياب الطلبة. والاستثناءُ بالدور الحاكم لا بصفة الحساب، فيسري ولو كان
#: حسابُه superuser (وهو الغالب في الإنتاج).
DEVELOPER_EXCLUDED_CAPABILITIES = frozenset(
    {"attendance.mark", "wings.record_day", "wings.excuse_after_deadline"}
)


def is_excluded_developer(user: Any, capability_key: str) -> bool:
    """أمطوّرٌ يُمنع من هذه القدرة بقرارٍ مالكيّ صريح؟"""
    return capability_key in DEVELOPER_EXCLUDED_CAPABILITIES and has_unrestricted_role(user)
