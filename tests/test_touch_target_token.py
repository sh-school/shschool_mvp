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
    ".parent-child__actions .btn-secondary",
    ".notif-group-switch__opt",
    ".period-switch__item",
    "a.status-badge",
    "a.ui-kpi",
    ".staff-name",
    ".th-sort",
    ".ui-tip__btn",
    ".pwa-dismiss-btn",
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


def _split_selectors(text: str) -> list[str]:
    """يقسم على الفواصل خارج الأقواس فقط — `:is(a, summary).btn-sm` محدِّدٌ واحد."""
    parts, depth, current = [], 0, ""
    for char in text:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    return [*parts, current.strip()]


def _selectors_of(block: str, declaration: str) -> set[str]:
    """محدِّداتُ كلّ قاعدةٍ في الكتلة يحوي جسمُها `declaration`."""
    found: set[str] = set()
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)  # التعليقُ يلتصق بمحدِّد ما بعده
    for rule in re.findall(r"([^{}]+)\{[^}]*" + declaration, block):
        found.update(_split_selectors(rule))
    return found


def test_coarse_pointer_raises_every_small_target_to_the_control_token():
    """على اللمس يصير كلُّ هدفٍ صغيرٍ معروفٍ بارتفاع `--control-h` — وحذفُ أحدها يُعيده دون 44px."""
    raised = _selectors_of(_coarse_block(read_css()), r"min-block-size:\s*var\(--control-h\)")
    missing = [s for s in COARSE_TARGETS if s not in raised]
    assert not missing, f"أهدافٌ لم تعد ترتفع إلى --control-h على coarse: {missing}"


def test_coarse_links_and_summaries_are_not_inline_boxes():
    """`min-block-size` لا يعمل على صندوقٍ سطريّ: رابطُ `btn-sm` في خليّة جدولٍ أو فقرةٍ يبقى ~29px،
    ثمّ إن صار مرناً بلا توسيطٍ التصق نصُّه بأعلاه — فالتوسيطُ شرطٌ لا زينة (مراجعة M-01)."""
    centred = _selectors_of(
        _coarse_block(read_css()), r"display:\s*inline-flex;\s*align-items:\s*center"
    )
    assert {":is(a, summary).btn-sm", ".btn-xs"} <= centred, sorted(centred)


def test_coarse_pointer_keeps_checkboxes_at_24px():
    """WCAG 2.5.8: على اللمس لا تنزل الخاناتُ وأزرارُ الاختيار دون 24px (K2)."""
    block = _coarse_block(read_css())
    assert re.search(
        r'input\[type="checkbox"\],\s*input\[type="radio"\]\s*\{[^}]*min-inline-size:\s*24px[^}]*min-block-size:\s*24px',
        block,
    ), "كتلةُ coarse لم تعد ترفع الخانات إلى 24px"


def test_the_warning_disc_stays_24px_inside_its_44px_target():
    """مراجعة M-01: رفعُ `.ui-tip__btn` إلى 44px كان يجعل قرصَ التحذير الأبيضَ في الشريط العنّابيّ 44px
    بدل 24px. الحشوةُ مع `background-clip: content-box` تُبقي المسَّ 44 والرسمَ 24."""
    block = _coarse_block(read_css())
    rule = re.search(r"\.card-bar \.ui-tip--warning \.ui-tip__btn\s*\{([^}]*)\}", block)
    assert rule, "لا قاعدةَ لقرص التحذير داخل كتلة coarse"
    assert "background-clip: content-box" in rule.group(1) and "padding:" in rule.group(1)


def test_breadcrumb_links_reach_the_mouse_minimum_on_every_pointer():
    """DBT-44: رابطُ الفتات كان 19px على سطح المكتب — 40 من 48 هدفاً دون 24px (قياس 25 صفحة، 1440) —
    لأنّ الحدَّ الأدنى كان في كتلة الهاتف وحدَها. صار في القاعدة العامّة لا داخل `@media`، وصفُّ الفتات
    24px أصلاً بزرّ الرجوع فلا يكبر (قِيس: ارتفاعُ كلّ صفحةٍ لم يتغيّر). وinline-flex موسَّطٌ وإلّا
    التصق النصُّ بأعلى الصندوق."""
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    rule = re.search(r"(?m)^\.breadcrumbs a\s*\{([^}]*)\}", css)
    assert rule, "لا قاعدةَ عامّةً لـ.breadcrumbs a خارجَ الـ@media"
    body = rule.group(1)
    assert re.search(r"min-block-size:\s*24px", body), "رابطُ الفتات دون 24px على سطح المكتب"
    assert "display: inline-flex" in body and "align-items: center" in body, "النصُّ لا يتوسّط"
