"""[MOBILE M-11 / K16] رسائلُ الخطأ لا تختفي قبل القراءة — على كلّ الأجهزة (D6).

الإشعارُ العائمُ مركزيّ (`static/js/base.js::showToast`، `#toast-container` في CSS):
- **زمنُ الظهور بالنوع**: الخطأُ 12 ثانيةً على الأقلّ، والنجاحُ 7 (خطّة الجوال M-11)،
  و`duration = 0` يُبقيه حتى يُغلق (إشعارُ «جارٍ التحضير»).
- **لا يغطّي التنقّل**: الحاويةُ أعلى الصفحة تحت الترويسة (قرار المالك 2026-09-23، #509) —
  فلا يقع على الشريط السفليّ للجوال كما كان بـ`bottom`.
"""

import re
from pathlib import Path

from tests.css_source import read_css

BASE_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "base.js"


def _durations() -> dict[str, int]:
    source = BASE_JS.read_text(encoding="utf-8")
    block = re.search(r"TOAST_DURATION\s*=\s*\{([^}]*)\}", source)
    assert block, "TOAST_DURATION غيرُ معرَّف في base.js — زمنُ الظهور مركزيٌّ هناك"
    return {k: int(v) for k, v in re.findall(r"(\w+)\s*:\s*(\d+)", block.group(1))}


def test_an_error_stays_at_least_twelve_seconds_and_a_success_seven():
    durations = _durations()
    assert durations["danger"] >= 12000, durations
    assert durations["success"] >= 7000, durations
    assert durations["warning"] >= durations["success"], durations


def test_a_zero_duration_keeps_the_toast_until_closed():
    source = BASE_JS.read_text(encoding="utf-8")
    assert re.search(
        r"if\s*\(\s*duration\s*>\s*0\s*\)\s*setTimeout", source
    ), "المدّةُ 0 يجب أن تُبقي الإشعارَ حتى يُغلق — لا مؤقّتَ حذف"


def test_the_toast_container_sits_under_the_header_not_on_the_bottom_bar():
    css = read_css()
    rule = re.search(r"#toast-container\s*\{([^}]*)\}", css)
    assert rule, "#toast-container غيرُ معرَّف"
    body = rule.group(1)
    assert re.search(r"(?<![-\w])top\s*:", body), body
    assert not re.search(
        r"(?<![-\w])bottom\s*:", body
    ), "الإشعارُ في أسفل الشاشة يغطّي الشريطَ السفليَّ على الجوال (M-11)"
