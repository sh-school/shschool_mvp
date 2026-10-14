"""وسمُ عبارة الوزارة للقوالب — `{% load ministry %}` ثمّ `{% ministry_name %}` (W-20261012-008).

مطفأً (الافتراضيّ) يُخرج نصّاً فارغاً؛ فمن جاورته فاصلةٌ يلفّه بالشرط:

    {% ministry_name as ministry %}{% if ministry %}<p>{{ ministry }}</p>{% endif %}

والمصدرُ والمفتاحُ في `core/ministry.py`.
"""

from django import template

from core.ministry import ministry_name as _ministry_name

register = template.Library()


@register.simple_tag
def ministry_name(short: bool = False) -> str:
    """عبارةُ الوزارة أو «» حين يكون المفتاحُ مطفأً."""
    return _ministry_name(short=short)
