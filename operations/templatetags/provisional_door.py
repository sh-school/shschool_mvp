"""بابُ الرصد بحصّةٍ مؤقّتة في القوالب (W-20261005-006): وسمٌ يقرأ مفتاحَ التشغيل — لا سياقَ إضافيّ في عرض جدول المعلّم (سقفُ طبقات العروض)."""

from django import template

from operations.services import provisional_session

register = template.Library()


@register.simple_tag
def provisional_enabled() -> bool:
    """هل مفتاحُ الحصّة المؤقّتة مشغَّل؟ مطفأً لا يظهر زرٌّ ولا أثر."""
    return provisional_session.enabled()


#: أدوارُ المعلّم والمنسّق ومن في حكمهم — لهم يُعطَّل جدولُ المنصّة عند تشغيل الرصد المؤقّت (القيادةُ والإدارةُ تُديران الجدولَ ولا تُعطَّل لهما).
TEACHER_ROLES = frozenset(
    {
        "teacher",
        "ese_teacher",
        "specialist",
        "coordinator",
        "teacher_assistant",
        "ese_assistant",
        "e_projects_coordinator",
    }
)


@register.simple_tag
def provisional_teacher_off(user) -> bool:
    """هل جدولُ المنصّة مُطفأٌ لهذا الدور؟ — مفتاحُ الحصّة المؤقّتة مشغَّلٌ والدورُ معلّمٌ أو منسّقٌ أو في حكمهما (D-231م)."""
    return provisional_session.enabled() and user.get_role() in TEACHER_ROLES
