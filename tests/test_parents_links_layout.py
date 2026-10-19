"""صفحةُ ربط أولياء الأمور — لا تداخلَ بين شريط «إضافة ربط جديد» وما حوله (W-20261010-018).

كان `.links-add__bar` بهوامش سالبةٍ بكسليّةٍ ثابتةٍ (‎-18px ‎-20px) مكتوبةٍ بيدٍ مقابل حشو البطاقة،
فتتقاطع مع حشوٍ ثانٍ إن تغيّر أحدهما. والآن الهامشُ من رموز الحشو نفسِها فيتبعها.
"""

import re

from tests.css_contrast import iter_rules
from tests.css_source import read_css


def _bar_rules():
    return [
        (sel, decls)
        for sel, decls, _ctx in iter_rules(read_css())
        if ".links-add__bar" in sel and "::-webkit" not in sel
    ]


def test_the_bar_margins_are_tokens_not_fixed_negative_pixels():
    rules = _bar_rules()
    assert rules, "لا قاعدةَ لـ`.links-add__bar`"
    for sel, decls in rules:
        for prop in ("margin", "margin-block-end"):
            value = decls.get(prop, "")
            assert not re.search(r"-\d+px", value), f"{sel} {prop}: {value} — هامشٌ سالبٌ بكسليّ"


def test_the_bar_pulls_back_by_the_card_padding_tokens():
    margins = " ".join(d.get("margin", "") for _s, d in _bar_rules())
    assert "calc(-1 * var(--sp-4-5))" in margins and "calc(-1 * var(--sp-5))" in margins


def test_a_closed_card_drops_its_bottom_padding_instead_of_a_negative_bar_margin():
    """الشريطُ المطويّ يسحب ما تحته بسالبٍ فيتراكب مع النموذج المخفيّ 18px (أدلّة 0502)؛ فيُصفَّر حشوُ البطاقة بدله."""
    rules = {sel: decls for sel, decls, _ctx in iter_rules(read_css())}
    bar = rules.get(".links-add:not([open]) > .links-add__bar", {})
    card = rules.get(".links-add:not([open])", {})
    assert bar.get("margin-block-end") == "0"
    assert card.get("padding-block-end") == "0"
