"""وسمُ شعار الوزارة لقوالب المخرجات فقط — `{% load ministry_logo %}` ثمّ `{% ministry_logo %}` (W-20261014-009).

أعلى وسط الترويسة واسمُ المدرسة تحته وسطاً. مضمَّنٌ `data:` فلا شبكة، والصنفُ `ministry-logo` مخفيٌّ على الشاشة (الطباعةُ وPDF وحدَهما).
لا يُستعمل في قالبٍ حيٍّ من المنصّة: يحرسه `tests/test_ministry_logo_exports_only.py` بقائمةِ قوالب المخرجات المسموحة.
"""

from django import template
from django.utils.html import format_html

from core import ministry_logo as logo

register = template.Library()


@register.simple_tag
def ministry_logo() -> str:
    try:
        src = logo.logo_data_uri()
    except FileNotFoundError:
        return ""
    return format_html(
        '<img class="ministry-logo" src="{src}" alt="" width="48" height="48" decoding="async">',
        src=src,
    )
