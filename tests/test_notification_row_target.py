"""[MOBILE M-02 / K1] صفُّ الإشعار كلُّه هدفُ لمسٍ واحد على المؤشّر الخشن.

كان في صفّ الإشعار هدفان صغيران: رابطُ العنوان (سطرٌ واحدٌ ≈20px ارتفاعاً) وزرُّ «مقروء» (32×32) — فأصبع
المشرف في الممرّ يخطئ الصفَّ كلَّه ولا يصيب إلّا سطرَ العنوان. وقياسُ `mobile_audit` يقرأ **صندوقَ العنصر** لا
منطقةَ النقر، فلا يكفي `::after` ممتدٌّ وحدَه: يجب أن يكبر صندوقُ الرابط نفسُه.

على `pointer: coarse` وحدَه (الفأرةُ كما كانت):
- الرابطُ `display: block` بحشوةٍ `--sp-3-5` وهامشٍ سالبٍ **مساوٍ** لها: صندوقُه 48px والتخطيطُ لا يتغيّر (ارتفاعُ الصفّ نفسُه)؛
- و`::after` ممتدٌّ (`position: absolute; inset: 0`) على الصفّ كلِّه — فالنقرُ على أيّ موضعٍ منه يفتح الرابط؛
- وزرُّ «مقروء» 44×44 وفوق الامتداد: كلاهما `position: relative` وهو يلي الرابطَ في الشيفرة فيُرسم فوقه بلا `z-index`.

مقيسٌ عند 375 (مؤشّرٌ خشن): الأهدافُ الصغيرة (<44) في الصندوق من 6 من 6 إلى 0 من 6، وارتفاعُ الصفوف كما كان.
"""

import re
from pathlib import Path

from tests.css_contrast import iter_rules
from tests.css_source import read_css

ROOT = Path(__file__).resolve().parent.parent
PARTIAL = (ROOT / "templates/notifications/partials/notif_item.html").read_text(encoding="utf-8")


def _rules(coarse: bool):
    """{محدِّدٌ مفرد: [تصريحات كلّ قاعدةٍ تحويه]} داخل سياق `pointer: coarse` أو خارجه."""
    found: dict[str, list[dict]] = {}
    for selector, decls, ctx in iter_rules(read_css()):
        if any("pointer: coarse" in head for head in ctx) != coarse:
            continue
        for part in selector.split(","):
            found.setdefault(" ".join(part.split()), []).append(decls)
    return found


def _merged(rules, selector):
    assert selector in rules, f"{selector} غيرُ معرَّفٍ على المؤشّر الخشن"
    merged: dict[str, str] = {}
    for decls in rules[selector]:
        merged.update({k: v.strip() for k, v in decls.items()})
    return merged


def test_the_read_button_is_a_44px_target_on_touch():
    button = _merged(_rules(True), ".notif-item__read")
    assert button["min-inline-size"] == "var(--control-h)"
    assert button["min-block-size"] == "var(--control-h)"


def test_the_title_link_grows_its_box_without_changing_the_layout():
    link = _merged(_rules(True), ".notif-item__title a")
    assert link["display"] == "block"
    pad = re.fullmatch(r"var\((--sp-[\w-]+)\)", link["padding-block"])
    assert pad, link["padding-block"]
    assert (
        link["margin-block"] == f"calc(-1 * var({pad.group(1)}))"
    ), "الهامشُ السالبُ لا يساوي الحشوةَ فيتغيّر ارتفاعُ الصفّ"


def test_the_link_is_stretched_over_the_whole_row_and_the_button_stays_above():
    rules = _rules(True)
    stretch = _merged(rules, ".notif-item__title a::after")
    assert stretch["content"] == '""'
    assert stretch["position"] == "absolute" and stretch["inset"] == "0"
    # الصفُّ مرجعُ الامتداد، والزرُّ مُوضَعٌ فيُرسم فوقه (وهو يلي الرابطَ في الشيفرة)
    assert _merged(rules, ".notif-item")["position"] == "relative"
    assert _merged(rules, ".notif-item__read")["position"] == "relative"
    assert PARTIAL.index("notif-item__main") < PARTIAL.index(
        'class="notif-item__read"'
    ), "الزرُّ قبل الرابط في الشيفرة — يُرسم تحته فلا يُضغط"


def test_the_mouse_layout_is_untouched():
    """الامتدادُ للّمس وحدَه: لا `::after` ولا رابطَ كتلةً خارج `pointer: coarse`."""
    outside = _rules(False)
    assert ".notif-item__title a::after" not in outside
    for decls in outside.get(".notif-item__title a", []):
        assert decls.get("display", "").strip() != "block", "الرابطُ كتلةٌ على الفأرة أيضاً"
