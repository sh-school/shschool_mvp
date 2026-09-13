"""`{% brand_color "MAROON" %}` — لونُ الهويّة في قالبٍ لا يحلّ `var()`.

قوالبُ البريد تُرسَل إلى عملاءَ لا يقرؤون ملفَّ أنماطٍ ولا يحلّون المتغيّرات
المخصَّصة، ومولّدُ الـPDF الاحتياطيّ (xhtml2pdf) لا يحلّها كذلك، وصفحةُ الخطأ
500 قد تُعرض والأنماطُ نفسُها لا تُحمَّل. فتحتاج القيمةَ رقماً في السمة. وبدل أن
تُكتب هناك نسخةً تنجرف، تُقرأ من `core.brand` — مرآةُ `:root` و`html.dark`
التي يحرسها `tests/test_design_tokens_resolve.py`.

`{% brand_color "SURFACE" "dark" %}` قيمةُ الليل من `brand.DARK`.
"""

from django import template

from core import brand

register = template.Library()


@register.simple_tag
def brand_color(name: str, theme: str = "light") -> str:
    """يُعيد قيمةَ ثابتٍ لونيٍّ من `core.brand` — ويُخفق إن لم يُعرَّف."""
    if theme == "dark":
        value = brand.DARK.get(name)
    elif theme == "light":
        value = getattr(brand, name, None)
    else:
        raise template.TemplateSyntaxError(f"brand_color: الوضعُ {theme!r} ليس light ولا dark")
    if not isinstance(value, str) or not value.startswith("#"):
        raise template.TemplateSyntaxError(
            f"brand_color: لا لونَ اسمُه {name!r} ({theme}) في core.brand"
        )
    return value
