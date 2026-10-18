"""تباينُ النصّ المكتوم والخطر على أرضيّات الصفحة ≥ 4.5 محسوباً من الرموز نفسِها لا من تعليقاتها (W-20261014-027).

كانت تعليقاتُ الرموز تقول 5.03 و5.06 بعد تغميق `--page-bg` في 2026-09-18 والفعليُّ 4.21 و4.24 فسقطا تحت حدّ WCAG 1.4.3.
وهذا الحارسُ يقرأ القيمَ من `token_table` (نهاراً وليلاً) فلا يكذب كالتعليق. ولا موضعَ نصٍّ تحت 12px في الموضعين اللذين رُفعا.
"""

import pytest

from tests.css_contrast import resolve, token_table
from tests.css_source import read_css

TEXT_TOKENS = ("--text-muted", "--status-danger-fg", "--text-secondary", "--maroon-fg")
GROUNDS = ("--surface", "--surface-alt", "--page-bg")


def _luminance(colour) -> float:
    lin = [
        (c / 255) / 12.92 if c / 255 <= 0.03928 else ((c / 255 + 0.055) / 1.055) ** 2.4
        for c in colour[:3]
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture(scope="module")
def tables():
    return token_table(read_css())


@pytest.mark.parametrize("mode", [0, 1], ids=["light", "dark"])
@pytest.mark.parametrize("token", TEXT_TOKENS)
@pytest.mark.parametrize("ground", GROUNDS)
def test_text_tokens_hold_4_5_on_every_ground(tables, mode, token, ground):
    tokens = tables[mode]
    foreground = resolve(f"var({token})", tokens)
    background = resolve(f"var({ground})", tokens)
    assert foreground and background, (token, ground)
    assert _contrast(foreground, background) >= 4.5, (token, ground, foreground, background)


def test_no_text_below_12px_in_the_two_fixed_places():
    css = read_css()
    for opener in (".kpi-donut-unit {", ".schedule-matrix .m-exempt-dot {"):
        start = css.index(opener)
        block = css[start : css.index("}", start)]
        assert "font-size: var(--text-xs)" in block, opener
