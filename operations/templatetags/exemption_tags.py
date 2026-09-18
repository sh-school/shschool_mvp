from django import template
from django.utils.html import format_html

from operations.schedule_paper import EXEMPTION_COLORS

register = template.Library()


@register.simple_tag
def exempt_dot(exempt_map: dict | None, day: int, period: int) -> str:
    """شارةُ تفريغٍ صغيرةٌ في زاوية خليّة الجدول العام — أو فراغ.

    الجدولُ العامّ مُلوَّنٌ صفّاً كاملاً بقسم معلّمه أصلاً (قرارُ 2026-09-14)،
    فخلفيّةٌ كاملةٌ ثانيةٌ للتفريغ تتصادم معه. شارةٌ صغيرةٌ في الزاوية — بلونها
    الخاصّ لكلّ قرار وحرفٍ واحدٍ داخلها (قرارُ المستخدم 2026-09-18: السببُ
    مذكورٌ لا لوناً وحده) — تكفي ولا تُضجّ.

    هنا في `operations/templatetags` لا `core/templatetags`: الشارةُ تقرأ
    `EXEMPTION_COLORS` من `operations.schedule_paper` — وimportٌ نازلٌ من
    core إلى operations يخالف حارس الطبقات (`tests/test_layering.py`).
    """
    found = (exempt_map or {}).get((day, period))
    if not found:
        return ""
    source, reason = found
    css_class, label, letter = EXEMPTION_COLORS[source]
    title = f"{label} — {reason}" if reason else label
    return format_html(
        '<span class="m-exempt-dot {}" title="{}">{}</span>', css_class, title, letter
    )
