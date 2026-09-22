"""شريطُ «أضف المنصة لشاشتك الرئيسية» يُغلقه زرُّه.

قاعدةُ `.pwa-banner { display: flex }` في طبقة `utilities` (#232) غلبت
`display: none` القديمةَ في `components`، والشريطُ يُظهَر ويُخفى بصنف `.visible`
— فصار ظاهراً في كلّ صفحةٍ ولا يُغلقه ✕. والعلاجُ سمةُ `hidden`: قاعدتُها في `reset`
بـ`!important` تغلب الطبقاتِ كلَّها، وبها يعمل شريطُ وليّ الأمر أصلاً.
"""

from pathlib import Path

from tests.css_source import read_css

ROOT = Path(__file__).resolve().parent.parent


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_the_staff_banner_starts_hidden():
    assert '<div id="pwa-banner" class="pwa-banner" hidden>' in _read("templates/base/base.html")


def test_the_banner_is_shown_and_closed_by_the_hidden_attribute():
    script = _read("static/js/base.js")
    start = script.index("PWA Install Banner")
    block = script[start : script.index("Service Worker", start)]

    assert "classList" not in block, "الصنفُ لا يغلب `display:flex` في طبقة utilities"
    assert "b.hidden = true" in block
    assert "b.hidden = false" in block


def test_the_banner_never_returns_once_installed_or_dismissed():
    """قرارُ 2026-09-13: بعد التثبيت أو الإغلاق أو الفتح تطبيقاً مثبّتاً لا يعود الشريط."""
    script = _read("static/js/base.js")
    start = script.index("PWA Install Banner")
    block = script[start : script.index("Service Worker", start)]

    assert "'appinstalled'" in block
    assert "display-mode: standalone" in block
    assert "localStorage.setItem(key, '1')" in block
    assert "pwaInstalled" in block and "pwaDismissed" in block
    assert block.count("_pwaSettled()") >= 2, "يُسأل قبل الإظهار وعند حلول موعده"


def test_hidden_wins_over_every_layer():
    assert "[hidden] { display: none !important; }" in read_css()
