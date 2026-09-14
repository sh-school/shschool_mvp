"""صفحاتُ الجداول على آيفون وشاشات اللمس: لا إطار، بل فتحٌ كاملٌ أو PDF.

كانت الورقةُ — عشراتُ صفحاتٍ بعرض A4 — في إطارٍ مضمَّن، فظهرت على آيفون (التطبيقُ
المثبَّت) صفحةً بيضاءَ بلا جداول، والخادمُ يرسمها كاملة. فالإطارُ لا يُحمَّل على
الهاتف واللمس، ويقوم مقامَه زرّان.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "schedule" / "pages_view.html"
TOUCH_QUERY = "(max-width: 640px), (hover: none) and (pointer: coarse)"


def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def test_the_frame_has_no_src_until_the_script_decides():
    iframe = re.search(r"<iframe[^>]*>", _template()).group(0)
    assert " src=" not in iframe, "إطارٌ بـsrc يُحمَّل على آيفون ولو كان مخفيّاً"
    assert "data-src=" in iframe


def test_script_and_css_share_one_touch_condition():
    """لو اختلف الشرطان لرأى الهاتفُ إطاراً فارغاً، أو حمّل ما لا يُعرض."""
    assert f"matchMedia('{TOUCH_QUERY}')" in _template()
    css = (ROOT / "static" / "css" / "custom.css").read_text(encoding="utf-8")
    block = css[css.index(f"@media {TOUCH_QUERY}") :]
    block = block[: block.index("\n  }\n")]
    assert ".schedule-paper-frame" in block
    assert ".schedule-frame-print" in block
    assert ".schedule-paper-touch" in block


def test_touch_screens_get_the_full_page_and_the_pdf(client_as, school, principal_user):
    response = client_as(principal_user).get("/teacher/weekly-schedule/pages/?kind=classes")
    html = response.content.decode()
    assert response.status_code == 200
    touch = re.search(r'<div class="schedule-paper-touch">(.*?)</div>', html, re.S).group(1)
    assert "/teacher/weekly-schedule/pages/paper/?" in touch
    assert "/teacher/weekly-schedule/pages/pdf/?" in touch
    assert "kind=classes" in touch
