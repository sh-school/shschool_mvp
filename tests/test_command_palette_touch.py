"""[MOBILE M-06 / K10] لوحةُ الأوامر لها مدخلُ لمس — زرُّ بحثٍ في الترويسة.

كانت اللوحةُ (`#cmd-palette`) تُفتح بـCtrl+K وحدَها، ولا لوحةَ مفاتيحَ على الجوال: فمن يحمل هاتفاً
(وهو موضعُ استعمال المشرف في الممرّ) لا يبلغ البحثَ السريعَ أصلاً. صار في الترويسة زرُّ بحثٍ:

- زرٌّ حقيقيّ (`<button>`) باسمٍ عربيّ (`aria-label`) ويعلن أنّه يفتح حواراً (`aria-haspopup`، `aria-controls`)؛
- يفتحها بـ`data-call="openPalette"` — سياسةُ أمن المحتوى تحجب `onclick`، والفعلُ من القائمة البيضاء في `actions.js`؛
- يشارك `.theme-toggle` مظهرَه ومنطقةَ لمسه (44px على المؤشّر الخشن — `test_touch_target_token`) وإخفاءَه في الطباعة،
  فلا قاعدةَ CSS جديدة (ميزانيّةُ CSS الخامّ لا تحتمل مكرَّراً)؛
- ظهورُه بشرط وجود اللوحة نفسِه (`user.is_authenticated`)، وإغلاقُها يُعيد التركيزَ إلى ما فتحها.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from tests.test_quality_new_views import make_admin

ROOT = Path(__file__).resolve().parent.parent
BASE = (ROOT / "templates/base/base.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
ACTIONS_JS = (ROOT / "static/js/actions.js").read_text(encoding="utf-8")


def _button(html: str) -> str:
    found = re.search(r"<button[^>]*\bid=\"nav-search-btn\"[^>]*>", html, re.S)
    assert found, "لا زرَّ بحثٍ (#nav-search-btn) في الترويسة"
    return found.group(0)


def test_the_header_has_a_search_button_that_names_and_controls_the_palette():
    tag = _button(BASE)
    assert 'type="button"' in tag
    assert 'data-call="openPalette"' in tag
    assert 'aria-controls="cmd-palette"' in tag and 'aria-haspopup="dialog"' in tag
    label = re.search(r'aria-label="([^"]+)"', tag)
    assert label and re.search(r"[؀-ۿ]", label.group(1)), "اسمُ الزرّ ليس عربيّاً"
    assert (
        "theme-toggle" in tag.split('class="')[1].split('"')[0]
    ), "الزرُّ لا يشارك .theme-toggle فيفقد منطقةَ اللمس 44px والإخفاءَ في الطباعة"


def test_the_button_sits_in_the_header_under_the_palettes_own_condition():
    header = re.search(r'<header class="site-header".*?</header>', BASE, re.S)
    assert header and 'id="nav-search-btn"' in header.group(0)
    before = header.group(0).split('id="nav-search-btn"')[0]
    assert before.rfind("{% if user.is_authenticated %}") > before.rfind(
        "{% endif %}"
    ), "الزرُّ خارجَ شرط user.is_authenticated — يظهر حيث لا لوحةَ يفتحها"
    assert re.search(r"{% if user\.is_authenticated %}\s*<div id=\"cmd-palette\"", BASE)


def test_the_call_is_whitelisted_and_the_function_is_global():
    block = re.search(r"var CALLABLE = \[(.*?)\];", ACTIONS_JS, re.S)
    assert block and '"openPalette"' in block.group(1), "openPalette ليست في CALLABLE"
    assert (
        "window.openPalette = openPalette" in APP_JS
    ), "الدالّةُ محلّيّةٌ في الغلاف — لن يجدها actions.js"


def test_closing_the_palette_returns_focus_to_what_opened_it():
    opener = re.search(r"function openPalette\(\) \{\s*opener = document\.activeElement;", APP_JS)
    assert opener, "openPalette لا تحفظ ما كان مركَّزاً"
    closer = APP_JS[APP_JS.index("window.closePalette = function") :].split("};")[0]
    assert "opener.focus()" in closer and "opener.isConnected" in closer, closer


@pytest.mark.django_db
def test_a_signed_in_page_renders_one_button_inside_the_header(client, school):
    client.force_login(make_admin(school))
    response = client.get(reverse("dashboard"), follow=True)
    html = response.content.decode()

    assert response.status_code == 200
    assert html.count('id="nav-search-btn"') == 1
    header = re.search(r'<header class="site-header".*?</header>', html, re.S).group(0)
    assert 'id="nav-search-btn"' in header
    assert html.count('id="cmd-palette"') == 1, "زرٌّ بلا لوحةٍ يفتحها"


@pytest.mark.django_db
def test_the_login_page_has_neither_the_button_nor_the_palette(client):
    html = client.get(reverse("login")).content.decode()
    assert "nav-search-btn" not in html and "cmd-palette" not in html
