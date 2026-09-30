"""تحديدُ مستلمي رسالة المطوّر الصادرة — فردٌ، أو قسمٌ أكاديميّ، أو دورٌ وظيفيّ، أو الجميع.

أربعةُ مستوياتٍ فقط (قرارُ المالك 2026-09-30)، وكلُّها تؤول إلى قائمة مستخدمين — فلا
فرقَ عند الإرسال (`OutboundMessageRecipient`) بين مستلمٍ واحدٍ ومئة.
"""

from __future__ import annotations

from core.models import CustomUser, Department
from core.models.access import Role


class AudienceError(ValueError):
    """قيمةُ هدفٍ غيرُ صالحة — تُعرض رسالتُها للمستخدم كما هي."""


def resolve_recipients(school, sender, target_kind: str, target_value: str):
    """يُعيد QuerySet[CustomUser] حسب `target_kind`، مُستبعِداً المرسِلَ نفسَه دائماً."""
    if target_kind == "user":
        qs = CustomUser.objects.filter(
            id=target_value, memberships__school=school, memberships__is_active=True
        )
    elif target_kind == "department":
        try:
            department = Department.objects.get(id=target_value, school=school)
        except Department.DoesNotExist as exc:
            raise AudienceError("القسمُ غيرُ موجود.") from exc
        qs = department.get_teachers()
    elif target_kind == "role":
        valid_roles = {code for code, _label in Role.ROLES}
        if target_value not in valid_roles:
            raise AudienceError("الدورُ غيرُ معروف.")
        qs = CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name=target_value,
        )
    elif target_kind == "all":
        qs = CustomUser.objects.filter(memberships__school=school, memberships__is_active=True)
    else:
        raise AudienceError("نوعُ الفئة المستهدفة غيرُ معروف.")
    return qs.exclude(id=sender.id).distinct()


def audience_label(target_kind: str, target_value: str, recipients_count: int) -> str:
    """وصفٌ نصّيٌّ مختصرٌ للفئة يُحفظ مع الرسالة (للسجلّ فقط)."""
    if target_kind == "user":
        user = CustomUser.objects.filter(id=target_value).first()
        return f"فردٌ: {user.full_name}" if user else "فردٌ محدّد"
    if target_kind == "department":
        dept = Department.objects.filter(id=target_value).first()
        return f"قسمُ {dept.name}" if dept else "قسمٌ أكاديميّ"
    if target_kind == "role":
        label = dict(Role.ROLES).get(target_value, target_value)
        return f"كلّ {label} ({recipients_count})"
    if target_kind == "all":
        return f"الجميع ({recipients_count})"
    return ""
