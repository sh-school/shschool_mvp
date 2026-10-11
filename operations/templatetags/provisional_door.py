"""بابُ الرصد بحصّةٍ مؤقّتة في القوالب (W-20261005-006): وسمٌ يقرأ مفتاحَ التشغيل — لا سياقَ إضافيّ في عرض جدول المعلّم (سقفُ طبقات العروض)."""

from django import template

from operations.services import provisional_session

register = template.Library()


def _school(context, user=None):
    """مدرسةُ الطلب (تُخزَّن على الطلب لتُحسب مرّةً واحدةً في الصفحة)."""
    request = context.get("request")
    if request is None:
        return None
    if not hasattr(request, "_prov_door_school"):
        who = user or getattr(request, "user", None)
        request._prov_door_school = who.get_school() if who and who.is_authenticated else None
    return request._prov_door_school


@register.simple_tag(takes_context=True)
def provisional_enabled(context) -> bool:
    """هل بابُ الرصد المؤقّت مشغَّل؟ تلقائيّاً حين لا جدولَ حيَّ للمدرسة؛ وباعتماد الجدول يسقط فيظهر جدولُ المنصّة."""
    request = context.get("request")
    if request is None:
        return provisional_session.enabled()
    if not hasattr(request, "_prov_door"):
        request._prov_door = provisional_session.enabled(_school(context))
    return request._prov_door


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


@register.simple_tag(takes_context=True)
def provisional_teacher_off(context, user) -> bool:
    """هل جدولُ المنصّة مُطفأٌ لهذا الدور؟ — بابُ الرصد المؤقّت مشغَّلٌ (لا جدولَ حيَّ) والدورُ معلّمٌ أو منسّقٌ أو في حكمهما (D-231م)."""
    return provisional_enabled(context) and user.get_role() in TEACHER_ROLES
