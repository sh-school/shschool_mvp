"""بابُ الرصد بحصّةٍ مؤقّتة في القوالب (W-20261005-006): وسمٌ يقرأ مفتاحَ التشغيل — لا سياقَ إضافيّ في عرض جدول المعلّم (سقفُ طبقات العروض)."""

from django import template

from operations.services import provisional_session

register = template.Library()


@register.simple_tag
def provisional_enabled() -> bool:
    """هل مفتاحُ الحصّة المؤقّتة مشغَّل؟ مطفأً لا يظهر زرٌّ ولا أثر."""
    return provisional_session.enabled()
