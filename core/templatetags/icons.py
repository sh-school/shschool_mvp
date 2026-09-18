"""وسمُ الأيقونة — المعنى من ``core/icons.py``، والرسمُ من ورقةٍ خارجيّةٍ مبصومة.

    {% load icons %}
    {% icon "absence" %}
    {% icon "print" size="sm" %}
    {% icon "behavior_violation" degree=3 label="مخالفة من الدرجة الثالثة" %}

الورقةُ ``static/icons/sprite.svg`` تُطلب مرّةً وتُخبَّأ: اسمُها في الإنتاج
مبصومٌ بمحتواها، فلا تُحمَل مع كلّ صفحةٍ كما تُحمَل ``components/sprite.html``.

والأيقونةُ زينةٌ بجانب نصٍّ افتراضاً (``aria-hidden``). فإن وقفت وحدها — زرٌّ بلا
نصّ — مُرِّر ``label`` فصارت صورةً لها اسمٌ يُقرأ.

والخطأُ ``TemplateSyntaxError`` لا خانةٌ فارغة: معنًى لا وجودَ له، أو حجمٌ لا صنفَ
له، أو درجةٌ خارج اللائحة.
"""

from __future__ import annotations

from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import SafeString

from core.icons import ICONS, VIOLATION_DEGREES, symbol_id

register = template.Library()

#: أحجامُ الأيقونة — أصنافٌ قائمةٌ في custom.css.
SIZES = ("", "sm", "lg", "xl", "2xl")

SPRITE_PATH = "icons/sprite.svg"


@register.simple_tag
def icon(key: str, size: str = "", label: str = "", degree: int | str | None = None) -> SafeString:
    if key not in ICONS:
        raise template.TemplateSyntaxError(f"icon: لا أيقونةَ بالمعنى {key!r} في core/icons.py")
    if size not in SIZES:
        raise template.TemplateSyntaxError(
            f"icon: حجمٌ {size!r} لا صنفَ له — المتاح: sm, lg, xl, 2xl"
        )
    level: int | None = None
    if degree is not None and degree != "":
        if key != "behavior_violation":
            raise template.TemplateSyntaxError("icon: الدرجةُ لأيقونة المخالفة وحدها")
        level = int(degree)
        if level not in VIOLATION_DEGREES:
            raise template.TemplateSyntaxError(f"icon: درجةُ المخالفة {degree!r} خارج اللائحة (1–4)")

    spec = ICONS[key]
    classes = ["icon", "icon-hg"]
    if size:
        classes.append(f"icon-{size}")
    if spec.mirror:
        classes.append("icon-mirror")
    href = f"{static(SPRITE_PATH)}#{symbol_id(key, level, size)}"
    if label:
        return format_html(
            '<svg class="{}" role="img" aria-label="{}" focusable="false"><use href="{}"></use></svg>',
            " ".join(classes),
            label,
            href,
        )
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="{}"></use></svg>',
        " ".join(classes),
        href,
    )


@register.simple_tag
def icon_named(name: str, size: str = "") -> SafeString | str:
    """وسمُ المكوّنات (``page_header``/``section_card``/``empty_state``/``action_tile``):
    معاملُ ``icon`` عندها اختياريّ، فالخانةُ الفارغة ترسم لا شيء بدل الخطأ.
    """
    if not name:
        return ""
    if name in ICONS:
        return icon(name, size=size)
    raise template.TemplateSyntaxError(f"icon_named: لا أيقونةَ بالمعنى {name!r} في core/icons.py")
