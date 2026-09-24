"""[MOBILE Q-08] اللمسُ بلا تأخير، والشريطُ السفليّ يعلن موضعَه.

`touch-action: manipulation` على التحكّمات فلا ينتظر المتصفّحُ نقرةً مزدوجة، و`aria-current="page"`
على عنصر الشريط السفليّ الحاليّ فيعلن القارئُ موضعَ المستخدم. (والمانيفستُ في `test_pwa_install.py`.)
"""

import re
from pathlib import Path

from tests.css_source import read_css

ROOT = Path(__file__).resolve().parent.parent


def test_controls_do_not_wait_for_a_double_tap():
    css = re.sub(r"/\*.*?\*/", "", read_css(), flags=re.S)
    rule = re.search(r"([^{}]*)\{\s*touch-action:\s*manipulation;?\s*\}", css)
    assert rule, "لا touch-action: manipulation على التحكّمات"
    selectors = {s.strip() for s in rule.group(1).split(",")}
    assert {"a", "button", "input", "select", "textarea", "summary"} <= selectors, selectors


def test_the_current_bottom_nav_item_is_announced():
    source = (ROOT / "static" / "js" / "base.js").read_text(encoding="utf-8")
    assert re.search(
        r"\.mobile-nav-item\.active'\)\.forEach\(function\s*\(a\)\s*\{\s*a\.setAttribute\('aria-current', 'page'\)",
        source,
    ), "عنصرُ الشريط السفليّ الحاليّ بلا aria-current"
