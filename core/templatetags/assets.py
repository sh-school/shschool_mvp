"""وسمُ أنماط المنصّة: `<link>` لكلّ ملفٍّ من `core.css_files` بترتيبه (ADR-0003)."""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html_join
from django.utils.safestring import SafeString

from core.css_files import always_loaded_static_names

register = template.Library()


@register.simple_tag
def custom_css() -> SafeString:
    return format_html_join(
        "\n  ",
        '<link rel="stylesheet" href="{}">',
        ((static(name),) for name in always_loaded_static_names()),
    )
