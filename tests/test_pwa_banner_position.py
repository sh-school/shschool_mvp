"""[MOBILE M-03] شريطُ «ثبّت المنصّة» لا يقاطع الشريطَ السفليّ ولا شريطَ الإجراء.

كانت لـ`.pwa-banner` قاعدتان: في `20-components.css` (`bottom: 80px`، فوق الشريط السفليّ)
وفي `50-utilities.css` (`bottom: 16px`، `z-index: 9999`) — والثانيةُ تغلب بطبقتها، فكان الشريطُ
يجلس فوق الشريط السفليّ نفسِه على الجوال (K7). صارت قاعدةً واحدة في المكوّنات:

- الجوال: يرتفع فوق الشريط السفليّ (`80px` + المنطقةُ الآمنة)، وحشوةُ `body` تحجز المساحةَ نفسها.
- الحاسوب (≥ 641px): لا شريطَ سفليّ فيعود إلى `--sp-4` من الحافّة.
- الإظهارُ بسمة `hidden` (قاعدةُ `[hidden]` في reset)، فلا `display: none` في قاعدته — وإلّا بقي مخفيّاً دائماً.
- لا يجلس على شريط الإجراء اللاصق (`.per-bar` في رصد الشعبة): يُخفى حيث وُجد.

يقرأ الحارسُ **كلَّ** قاعدةٍ يُستهدف بها الشريط (مجمَّعةً أو بمعرّفه أو بسلفٍ)، لا الصيغةَ الحرفيّةَ الواحدة —
فتكرارٌ بأيّ صيغةٍ لـ`bottom` أو `display` يُسقطه.
"""

import re

from tests.css_contrast import iter_rules
from tests.css_source import read_css

TARGETS_BANNER = re.compile(r"(?:^|[\s>+~])[.#]pwa-banner$")
OFFSET_PROPS = ("bottom", "inset-block-end", "inset-block", "inset")
DESKTOP = "(min-width: 641px)"


def _banner_rules():
    """كلُّ (مُحدِّد، تصريحات، سياق) يستهدف الشريطَ نفسَه — لا أبناءَه (`.pwa-banner__icon`)."""
    for selector, decls, ctx in iter_rules(read_css()):
        parts = [" ".join(p.split()) for p in selector.split(",")]
        if any(TARGETS_BANNER.search(p) for p in parts):
            yield selector, decls, ctx


def _in(ctx, needle):
    return any(needle in head for head in ctx)


def test_the_banner_has_one_base_offset_and_one_desktop_offset():
    offsets = [
        (selector, ctx)
        for selector, decls, ctx in _banner_rules()
        if any(prop in decls for prop in OFFSET_PROPS)
    ]
    base = [s for s, ctx in offsets if not _in(ctx, "@media")]
    desktop = [s for s, ctx in offsets if _in(ctx, DESKTOP)]
    assert len(offsets) == 2 and len(base) == 1 and len(desktop) == 1, (
        "قاعدتان للموضع لا غير: أساسٌ ومكتبيّ — وُجد: " + repr(offsets)
    )


def test_the_banner_is_never_hidden_by_display_none_except_over_a_sticky_action_bar():
    for selector, decls, ctx in _banner_rules():
        if _in(ctx, "print"):  # الطباعةُ تُخفيه عمداً مع بقيّة الواجهة
            continue
        display = decls.get("display", "").strip()
        if display == "none":
            assert ":has(.per-bar)" in selector, f"{selector}: يُخفي الشريطَ دائماً"
        elif display:
            assert display == "flex", f"{selector}: display: {display}"


def test_the_banner_reads_its_layer_token_once():
    layers = [d["z-index"].strip() for _s, d, _c in _banner_rules() if "z-index" in d]
    assert layers == ["var(--z-banner)"], layers


def test_the_banner_clears_the_bottom_nav_reserved_by_the_body():
    base = next(
        d for _s, d, c in _banner_rules() if "inset-block-end" in d and not _in(c, "@media")
    )
    offset = re.fullmatch(
        r"calc\((\d+)px \+ var\(--safe-bottom\)\)", base["inset-block-end"].strip()
    )
    assert offset, base["inset-block-end"]
    body = next(
        d["padding-bottom"]
        for s, d, c in iter_rules(read_css())
        if s.strip() == "body" and "padding-bottom" in d and d["padding-bottom"].strip() != "0"
    )
    padding = re.fullmatch(r"calc\((\d+)px \+ var\(--safe-bottom\)\)", body.strip())
    assert padding, "حشوةُ body لا تحجز الشريطَ السفليّ"
    assert int(offset.group(1)) >= int(padding.group(1)), "الشريطُ أخفضُ من حافّة الشريط السفليّ"


def test_the_desktop_returns_it_to_the_edge():
    desktop = [d for _s, d, c in _banner_rules() if _in(c, DESKTOP) and "inset-block-end" in d]
    assert [d["inset-block-end"].strip() for d in desktop] == ["var(--sp-4)"]


def test_the_sticky_action_bar_keeps_clear_of_the_bottom_nav_like_the_body():
    """`.per-bar` (رصد الشعبة) يلتصق فوق الشريط السفليّ بحشوة `body` نفسِها لا برقمٍ منفصل."""
    bottoms = [
        d["bottom"].strip()
        for s, d, c in iter_rules(read_css())
        if s.strip() == ".per-bar" and _in(c, "max-width: 640px") and "bottom" in d
    ]
    assert bottoms == ["calc(72px + var(--safe-bottom))"], bottoms
