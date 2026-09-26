"""[DESIGN] رصدُ الغياب (`wings/record`): بطاقةُ الجناح بقدر محتواها لا بطول أطولِ أعمدتها (قرارُ المالك 2026-09-26).

كانت الأعمدةُ الخمسةُ تتساوى بطول أطولها فيبقى في الأقصر فراغٌ أبيضُ (لُوحظ على الإنتاج بلقطة). و`align-self: start` وحدَه يُسقط الاحتواءَ: تخرج
البطاقةُ عن الصفّ فلا تنضغط منطقةُ التمرير — فيلزم معه `max-block-size: 100%` (الوصفةُ نفسُها لـ`.fill-grid > .ui-section` وللأخيرة في `.ui-grid-2`).
"""

import re

from tests.css_source import read_css


def test_wing_cards_fit_their_content_and_stay_inside_their_row():
    rule = re.search(
        r"#main-content\.page-noscroll \.wing-cols > \.wing-panel \{([^}]*)\}", read_css()
    )
    assert rule, "لا قاعدةَ لبطاقة الجناح في رصد الغياب"
    body = rule.group(1)
    assert "align-self: start" in body
    assert "max-block-size: 100%" in body, "بلا سقف الصفّ تفيض البطاقةُ ولا تُمرَّر منطقتُها"
    assert "min-height: 0" in body
