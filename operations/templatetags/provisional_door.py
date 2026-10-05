"""بابُ الرصد بحصّةٍ مؤقّتة في القوالب (W-20261005-006): وسمٌ يقرأ مفتاحَ التشغيل — لا سياقَ إضافيّ في عرض جدول المعلّم (سقفُ طبقات العروض)."""

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from operations.services import provisional_session

register = template.Library()


@register.simple_tag
def provisional_enabled() -> bool:
    """هل مفتاحُ الحصّة المؤقّتة مشغَّل؟ مطفأً لا يظهر زرٌّ ولا أثر."""
    return provisional_session.enabled()


@register.simple_tag
def action_tile_off(title: str, desc: str = "", icon: str = "") -> str:
    """بلاطةُ انتقالٍ **مُعطَّلة** بمظهر `action_tile` نفسِه — لا رابطَ ولا تركيز (أمرُ المالك D-228م: مفاتيحُ الجدول تُطفأ بالمفتاح)."""
    return mark_safe(
        render_to_string(
            "components/ui/action_tile_off.html", {"title": title, "desc": desc, "icon": icon}
        )
    )
