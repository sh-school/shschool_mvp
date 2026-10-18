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

NL = chr(10)


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


@register.simple_tag
def grade_row_css(selector: str, ratio: float = 0.2) -> str:
    """قواعدُ تظليل صفوف الجدول (على `tr` فلا يطمس خلايا الحالة) بلون صفّها الدراسيّ للـPDF: الصفُّ `tr.g-g7` … `tr.g-g12` تحت `selector`."""
    from django.utils.safestring import mark_safe

    rules = []
    for grade, hue in brand.GRADE_HUES.items():
        key = grade.lower()
        tint = brand.grade_tint(grade, ratio)
        rules.append(
            f"{selector} tr.g-{key} {{ background: {tint}; }} "
            f"{selector} tr.g-{key} td:first-child {{ border-right: 3px solid {hue}; }}"
        )
    return mark_safe(NL.join(rules))  # noqa: S308 — ثوابتُ لونٍ من core.brand لا مدخلُ مستخدم
