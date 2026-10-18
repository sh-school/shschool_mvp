"""
tests/test_behavior_mobile_layout.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
تقرير المخالفة على الهاتف (W-20261012-029): كلُّ درجةٍ بطاقةٌ بعرضٍ كاملٍ مكدّسةٌ بلا تمريرٍ داخليّ،
وأزرارُ الدرجة صفٌّ لكلّ درجةٍ بهدفِ لمسٍ لا يقلّ عن ارتفاع التحكّم. حارسٌ نصّيٌّ؛ والقياسُ في المتصفّح.
"""

from tests.css_source import ROOT, read_css

CSS = read_css()
FORM = (ROOT / "templates" / "behavior" / "partials" / "quick_log_form.html").read_text(
    encoding="utf-8"
)


def _phone_block(first_rule: str) -> str:
    """كتلةُ `@media (max-width: 640px)` التي تبدأ بالقاعدة المعطاة."""
    start = CSS.index("@media (max-width: 640px) {\n  " + first_rule)
    return CSS[start : CSS.index("\n}\n", start)]


def test_each_degree_is_a_full_width_card_without_inner_scroll_on_phones():
    block = _phone_block(".beh-degrees {")
    assert "grid-template-columns: minmax(0, 1fr)" in block
    assert "max-block-size: none; overflow-y: visible;" in block


def test_the_level_picker_is_one_row_per_degree_with_a_touch_target():
    block = _phone_block(".beh-level-pick {")
    assert "grid-template-columns: minmax(0, 1fr)" in block
    assert "min-block-size: var(--control-h)" in block


def test_the_degree_name_is_hidden_on_desktop_and_the_radio_is_unchanged():
    assert ".beh-level-pick__name { display: none; }" in CSS
    assert 'class="beh-level-pick__name">{{ label }}' in FORM
    assert 'type="radio" name="level"' in FORM
