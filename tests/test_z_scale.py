"""
tests/test_z_scale.py
━━━━━━━━━━━━━━━━━━━━━
قائمةُ الشريط تعلو الشريطَ الذي فُتحت منه.

على الجوّال: تُفتح لوحةُ القائمة، ثمّ «إدارة الشؤون الأكاديمية» فتنسدل
قائمتُها الفرعيّة — **تحت** اللوحة، فيُحجب أعلاها ولا يُضغط. وجده المستخدم
يومَ 2026-09-12.

والسبب: `.sd-menu` تُعرَّف في `base.html` **خارج** `<nav class="site-nav">`،
فتقع في سياق التكديس الجذريّ. و`.site-nav` لزجٌ بطبقةٍ فينشئ سياقاً مستقلّاً
تجلس فيه لوحةُ الجوّال. فالمقارنةُ الفعليّة بين طبقة القائمة وطبقة الشريط —
وكانت القائمةُ على `--z-dropdown` (500) والشريطُ على `--z-navbar` (1000).

وعلى الحاسوب تنفتح القائمةُ **تحت** الشريط فلا يتقاطعان، فلا يظهر العطب.
"""

import pathlib
import re

from tests.css_contrast import iter_rules, token_table
from tests.css_source import read_css

BASE = pathlib.Path("templates/base/base.html")

#: المقياسُ مرتَّباً من الأدنى — كلُّ طبقةٍ تعلو ما قبلها.
ORDER = ["--z-dropdown", "--z-navbar", "--z-sidebar", "--z-nav-menu", "--z-modal", "--z-toast"]


def _tokens():
    light, _dark = token_table(read_css())
    return light


def _z_of(selector: str) -> int:
    """طبقةُ مُحدِّدٍ بعينه في الملفّ، بعد حلّ رمزها."""
    tokens = _tokens()
    for sel, decls, ctx in iter_rules(read_css()):
        if any("media" in c for c in ctx):
            continue
        if " ".join(sel.split()) == selector and "z-index" in decls:
            raw = decls["z-index"].strip()
            m = re.match(r"var\((--[\w-]+)\)", raw)
            return int(tokens[m.group(1)] if m else raw)
    raise AssertionError(f"لا `z-index` لـ`{selector}`")


def test_the_scale_is_ordered():
    """كلُّ طبقةٍ في المقياس تعلو ما قبلها — لا تساوي ولا انقلاب."""
    tokens = _tokens()
    missing = [t for t in ORDER if t not in tokens]
    assert not missing, "رموزُ طبقاتٍ مفقودة: " + ", ".join(missing)
    values = [int(tokens[t]) for t in ORDER]
    assert values == sorted(values) and len(set(values)) == len(values), (
        "المقياسُ غيرُ مرتَّب:\n  " + "\n  ".join(f"{t:16} {v}" for t, v in zip(ORDER, values))
    )


def test_nav_menus_sit_outside_the_nav_bar():
    """الافتراضُ الذي يقوم عليه الحارسُ التالي — فإن تغيّر تغيّر الحكم.

    لو نُقلت `.sd-menu` إلى داخل `<nav>` لصارت في سياق الشريط نفسِه،
    ولقُورنت بلوحة الجوّال مباشرةً لا بالشريط.
    """
    html = BASE.read_text(encoding="utf-8")
    nav_open = html.index('<nav class="site-nav"')
    nav_close = html.index("</nav>", nav_open)
    first_menu = html.index('class="sd-menu"')
    assert (
        first_menu > nav_close
    ), '`.sd-menu` صارت داخل `<nav class="site-nav">` — راجع مقارنةَ الطبقات'


def test_a_nav_menu_is_drawn_above_the_bar_it_opens_from():
    """القائمةُ في السياق الجذريّ، فتُقارَن بطبقة الشريط ولوحة الجوّال معاً."""
    menu = _z_of(".sd-menu")
    bar = _z_of(".site-nav")
    assert menu > bar, (
        f"`.sd-menu` بطبقة {menu} و`.site-nav` بطبقة {bar} — "
        "فتُرسم القائمةُ الفرعيّةُ تحت لوحة الجوّال ولا تُضغط"
    )
    tokens = _tokens()
    assert menu > int(tokens["--z-sidebar"]), "القائمةُ دون لوحة الجوّال"
    assert menu < int(tokens["--z-modal"]), "القائمةُ تعلو النوافذَ الحواريّة"
