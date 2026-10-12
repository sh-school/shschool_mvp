"""وسمُ شعار المدرسة للقوالب — `{% load school_logo %}` ثمّ `{% school_logo "nav" %}` (W-20261012-012).

يعرض المكوّنَ `components/school_logo.html` (الشاشة) أو الصورةَ المضمَّنة (PDF) بحسب `pdf=True`:

    {% school_logo "login" %}                 ← شاشة: رابطُ الملفّ الثابت
    {% school_logo "print" pdf=True %}        ← PDF: data URI

والمصدرُ في `core/school_logo.py`؛ والأحجامُ أصنافُ CSS `school-logo--<size>` في `20-components.css`.
"""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from core import school_logo as logo

register = template.Library()


@register.simple_tag
def school_logo(size: str = "nav", pdf: bool = False) -> str:
    """وسمُ `<img>` للشعار: زخرفيٌّ (`alt` فارغ) لأنّ اسمَ المدرسة نصٌّ يجاوره."""
    if size not in logo.SIZES_PX:
        raise template.TemplateSyntaxError(
            f"school_logo: حجمٌ غير معروف «{size}» ({', '.join(logo.SIZES_PX)})"
        )
    side = logo.SIZES_PX[size]
    try:
        src = logo.logo_data_uri() if pdf else static(logo.LOGO_STATIC_PATH)
    except FileNotFoundError:
        return ""
    return format_html(
        '<img class="school-logo school-logo--{}" src="{}" alt="" width="{}" height="{}" decoding="async">',
        size,
        src,
        side,
        side,
    )


@register.simple_tag
def school_logo_data_uri() -> str:
    """الشعارُ `data:` URI للأنماط/القوالب التي تحتاج المصدرَ لا الوسم (ترويسةُ Playwright)."""
    try:
        return logo.logo_data_uri()
    except FileNotFoundError:
        return ""
