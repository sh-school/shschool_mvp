from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.simple_tag
def exempt_dot(exempt_map, day: int, period: int):
    """شارةُ تفريغٍ صغيرةٌ في زاوية خليّة الجدول العام — أو فراغ.

    الجدولُ العامّ مُلوَّنٌ صفّاً كاملاً بقسم معلّمه أصلاً (قرارُ 2026-09-14)،
    فخلفيّةٌ كاملةٌ ثانيةٌ للتفريغ تتصادم معه. شارةٌ صغيرةٌ في الزاوية — بلونها
    الخاصّ لكلّ قرار وحرفٍ واحدٍ داخلها (قرارُ المستخدم 2026-09-18: السببُ
    مذكورٌ لا لوناً وحده) — تكفي ولا تُضجّ.
    """
    from operations.schedule_paper import EXEMPTION_COLORS

    found = (exempt_map or {}).get((day, period))
    if not found:
        return ""
    source, reason = found
    css_class, label, letter = EXEMPTION_COLORS[source]
    title = f"{label} — {reason}" if reason else label
    return format_html('<span class="m-exempt-dot {}" title="{}">{}</span>', css_class, title, letter)


@register.filter
def duration_ms(value):
    """مدّةٌ بالملّي ثانية تُقرأ: «25.6 ث» تحت الدقيقة، و«6:14 د» فوقها.

    فـ«374379ms» رقمٌ يُحسب لا يُقرأ — ومن يقارن توليدين يريد أن يرى الفرق
    بين ست دقائق ونصف دقيقة بلا قسمة.
    """
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return ""
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} ث"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}:{rest:02d} د"
