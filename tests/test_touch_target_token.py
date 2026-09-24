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


#: M-01: ما رفعته كتلةُ `pointer: coarse` إلى `--control-h` — كان 190 من 213 هدفاً صغيراً في رحلات
#: الأدوار الخمسة في الترويسة والفتات وحدَهما (mobile_audit 2026-09-24، K1 49.4% ← 0.5%).
COARSE_TARGETS = (
    ".site-header .nav-logo",
    ".site-header .nav-user-btn",
    ".site-header .nav-bell",
    ".theme-toggle",
    ".bc-back",
    ".breadcrumbs a",
    ".btn-sm",
    ".btn-xs",
    ".th-sort",
    ".ui-tip__btn",
    ".toast-close",
    ".modal-close-btn",
)


def _coarse_block(css: str) -> str:
    start = css.index("@media (pointer: coarse)")
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return css[i : j + 1]
    raise AssertionError("كتلةُ pointer: coarse لم تُغلق")


def test_coarse_pointer_raises_every_small_target_to_the_control_token():
    """على اللمس يصير كلُّ هدفٍ صغيرٍ معروفٍ بارتفاع `--control-h` — وحذفُ أحدها يُعيده دون 44px."""
    block = _coarse_block(read_css())
    raised = {
        selector.strip()
        for rule in re.findall(r"([^{}]+)\{[^}]*min-block-size:\s*var\(--control-h\)", block)
        for selector in rule.split(",")
    }
    missing = [s for s in COARSE_TARGETS if s not in raised]
    assert not missing, f"أهدافٌ لم تعد ترتفع إلى --control-h على coarse: {missing}"
