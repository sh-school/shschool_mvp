"""`{% brand_color "MAROON" %}` — لونُ الهويّة في قالبٍ لا يحلّ `var()`.

قوالبُ البريد تُرسَل إلى عملاءَ لا يقرؤون ملفَّ أنماطٍ ولا يحلّون المتغيّرات
المخصَّصة، فتحتاج القيمةَ رقماً في السمة نفسِها. وبدل أن تُكتب هناك نسخةً
ثالثةً تنجرف، تُقرأ من `core.brand` — وهو مرآةُ `:root` التي يحرسها
`tests/test_design_tokens_resolve.py`.
"""

from django import template

from core import brand

register = template.Library()


@register.simple_tag
def brand_color(name: str) -> str:
    """يُعيد قيمةَ ثابتٍ لونيٍّ من `core.brand` — ويُخفق إن لم يُعرَّف."""
    value = getattr(brand, name, None)
    if not isinstance(value, str) or not value.startswith("#"):
        raise template.TemplateSyntaxError(f"brand_color: لا لونَ اسمُه {name!r} في core.brand")
    return value
