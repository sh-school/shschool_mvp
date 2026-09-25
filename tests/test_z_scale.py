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

from tests.css_contrast import iter_rules, strip_noise, token_table
from tests.css_source import css_paths, read_css

BASE = pathlib.Path("templates/base/base.html")

#: المقياسُ مرتَّباً من الأدنى — كلُّ طبقةٍ تعلو ما قبلها.
ORDER = [
    "--z-banner",
    "--z-dropdown",
    "--z-navbar",
    "--z-sidebar",
    "--z-nav-menu",
    "--z-modal",
    "--z-toast",
]

#: أدنى رقمٍ خامٍّ يُعدّ «طبقةَ صفحة» (K18 في خطّة الجوال): ما دونه ترتيبٌ محلّيٌّ داخل مكوّنٍ.
RAW_LAYER_FLOOR = 20


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


def test_no_page_layer_is_a_raw_number():
    """K18 = 0: طبقةُ الصفحة (≥ 20) رمزٌ من السلّم لا رقمٌ خام.

    الرقمُ الخامّ يُخفي مقارنتَه بغيره: كان شريطُ التثبيت على `9999` فيعلو المودالَ والتوستَ
    (طبقاتُ 9000 و9500)، وثلاثُ قوائمَ منسدلةٍ على 20 و50 فتسقط تحت ترويسات الجداول اللاصقة (100).
    """
    raw = []
    for path in css_paths():
        text = strip_noise(path.read_text(encoding="utf-8"))
        for number, line in enumerate(text.splitlines(), 1):
            for match in re.finditer(r"(?i)z-index\s*:\s*(-?\d+)", line):
                if int(match.group(1)) >= RAW_LAYER_FLOOR:
                    raw.append(f"{path.name}:{number}: {line.strip()[:90]}")
    assert not raw, "z-index خامٌّ ≥ 20 — استعمل رمزاً من `--z-*`:\n  " + "\n  ".join(raw)


def test_the_install_banner_sits_under_everything_the_user_opens():
    """شريطُ «ثبّت المنصّة» فوق المحتوى وتحت كلّ ما يفتحه المستخدم أو يثبت في الشاشة.

    لوحةُ الهامبرغر ابنةُ `.site-nav` اللزج (سياقُ تكديسٍ بطبقة 1000)، فطبقتُها الفعليّة في الجذر
    1000 لا `--z-sidebar` — فما كان فوق 1000 غطّى اللوحةَ. لذلك الشريطُ دون `--z-navbar` لا فوقه.
    """
    tokens = _tokens()
    banner = _z_of(".pwa-banner")
    assert banner == int(tokens["--z-banner"]), "`.pwa-banner` لا تقرأ `--z-banner`"
    assert int(tokens["--z-raised"]) < banner < int(tokens["--z-dropdown"])
    assert banner < int(tokens["--z-navbar"]) < _z_of(".sd-menu") < int(tokens["--z-modal"])
    assert int(tokens["--z-modal"]) < int(tokens["--z-toast"])
