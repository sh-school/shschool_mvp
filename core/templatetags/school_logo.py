"""وسمُ شعار المنصّة للقوالب — `{% load school_logo %}` ثمّ `{% school_logo "nav" %}` (W-20261012-012؛ W-20261014-009).

شاشةٌ فقط: رابطُ الملفّ الثابت. وشعارُ الوزارة للتصدير في `ministry_logo` ولا يشاركه شيئاً.
والمصدرُ في `core/school_logo.py`؛ والأحجامُ أصنافُ CSS `school-logo--<size>` في `20-components.css`.
"""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from core import school_logo as logo

register = template.Library()


@register.simple_tag
def school_logo(size: str = "nav") -> str:
    """وسمُ `<img>` للشعار: زخرفيٌّ (`alt` فارغ) لأنّ اسمَ المدرسة نصٌّ يجاوره."""
    if size not in logo.SIZES_PX:
        raise template.TemplateSyntaxError(
            f"school_logo: حجمٌ غير معروف «{size}» ({', '.join(logo.SIZES_PX)})"
        )
    side = logo.SIZES_PX[size]
    return format_html(
        '<img class="school-logo school-logo--{size}" src="{src}" alt="" width="{side}" height="{side}" decoding="async">',
        size=size,
        src=static(logo.LOGO_STATIC_PATH),
        side=side,
    )
