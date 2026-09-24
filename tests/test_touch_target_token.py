"""[MOBILE] الحدُّ الأدنى لهدف اللمس يُكتب `var(--control-h)` لا `44px` (H-01).

كان الرقمُ مكتوباً حرفيّاً في سبعة عشر موضعاً في ثلاثة ملفّات (2026-09-23)، والرمزُ `--control-h`
معرَّفٌ في `10-foundation.css` لهذا بالضبط منذ #423. فمن غيّر الحدَّ يوماً (أو رفعه لطبقةٍ
`coarse`، M-01) غيّره في موضعٍ واحد لا يعرف أين الباقي. والحارسُ يمنع عودتَه حرفيّاً.

ما يبقى 44px عمداً ليس حدَّ لمس: عرضُ مسار المفتاح (`.ui-switch__track`)، ومقاسُ الشارة
(`.per-head__badge`)، وارتفاعُ هيكل التحميل (`.skeleton-row`) — أبعادٌ بصريّةٌ لا حدودٌ دنيا.
"""

import re

from tests.css_source import read_css

TOUCH_MINIMUM = re.compile(r"\bmin-(?:height|width|block-size|inline-size)\s*:\s*44px")


def test_touch_minimums_read_the_control_token():
    found = TOUCH_MINIMUM.findall(read_css())
    assert not found, f"حدٌّ أدنى للّمس مكتوبٌ 44px حرفيّاً ({len(found)} موضعاً) — اكتبه var(--control-h)"


def test_the_control_token_is_44px_and_defined_once():
    css = read_css()
    definitions = re.findall(r"--control-h\s*:\s*([^;]+);", css)
    assert definitions == ["44px"], definitions
