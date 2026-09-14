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

import re
from pathlib import Path

from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from core.icons import ICONS, VIOLATION_DEGREES, symbol_id

register = template.Library()

#: أحجامُ الأيقونة — أصنافٌ قائمةٌ في custom.css.
SIZES = ("", "sm", "lg", "xl", "2xl")

SPRITE_PATH = "icons/sprite.svg"


@register.simple_tag
def icon(key, size="", label="", degree=None):
    if key not in ICONS:
        raise template.TemplateSyntaxError(f"icon: لا أيقونةَ بالمعنى {key!r} في core/icons.py")
    if size not in SIZES:
        raise template.TemplateSyntaxError(
            f"icon: حجمٌ {size!r} لا صنفَ له — المتاح: sm, lg, xl, 2xl"
        )
    if degree not in (None, ""):
        if key != "behavior_violation":
            raise template.TemplateSyntaxError("icon: الدرجةُ لأيقونة المخالفة وحدها")
        if int(degree) not in VIOLATION_DEGREES:
            raise template.TemplateSyntaxError(f"icon: درجةُ المخالفة {degree!r} خارج اللائحة (1–4)")
        degree = int(degree)
    else:
        degree = None

    spec = ICONS[key]
    classes = ["icon", "icon-hg"]
    if size:
        classes.append(f"icon-{size}")
    if spec.mirror:
        classes.append("icon-mirror")
    href = f"{static(SPRITE_PATH)}#{symbol_id(key, degree, size)}"
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


#: أسماءُ الورقة القديمة ``components/sprite.html`` — تُقرأ مرّةً عند التحميل.
_LEGACY_SPRITE = (
    Path(__file__).resolve().parent.parent.parent / "templates" / "components" / "sprite.html"
)
_LEGACY_NAMES = frozenset(
    re.findall(r'id="icon-([a-z0-9-]+)"', _LEGACY_SPRITE.read_text(encoding="utf-8"))
)


@register.simple_tag
def icon_named(name, size=""):
    """وسمُ المكوّنات في الانتقال — يُحذف مع ``components/sprite.html`` (المرحلة 5).

    المكوّناتُ (``page_header`` و``section_card`` و``empty_state`` و``action_tile``)
    تستقبل الأيقونةَ معاملاً من 136 قالباً لا تُرحَّل في طلبٍ واحد. فمعنى القاموس
    يُرسم بالوسم الجديد، والاسمُ القديم يُرسم كما كان — والسقّاطةُ في
    ``tests/test_icon_dictionary.py`` تمنع أن يزيد القديم.
    """
    if not name:
        return ""
    if name in ICONS:
        return icon(name, size=size)
    if name in _LEGACY_NAMES:
        return format_html(
            '<svg class="icon{}" aria-hidden="true" focusable="false"><use href="#icon-{}"/></svg>',
            f" icon-{size}" if size else "",
            name,
        )
    raise template.TemplateSyntaxError(
        f"icon_named: {name!r} ليس معنًى في القاموس ولا اسماً في الورقة القديمة"
    )
