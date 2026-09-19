"""قائمةُ الجوال (بلاغا 2026-09-14 من آيفون).

١. زرُّ القائمة كان يحتاج ضغطتين: كان يُبدَّل نصُّه (`textContent = '✕'`) فتُنزع
   أيقونةُ SVG الملموسة من الصفحة، ومستمعُ «النقر خارج القائمة» يسأل بعده
   `e.target.closest('#mob-menu-btn')` عن عقدةٍ منزوعةٍ فلا يجد زرّاً، فيُغلق ما فُتح.
٢. القائمةُ الفرعيّةُ كانت تُثبَّت أعلى الشاشة فوق اللوحة فتُخفيها. والقرار: تبقى
   عائمةً، واللوحةُ تنكمش يميناً (`nb-split`) والفرعيّةُ يساراً (`sd-drawer`).
"""

import pathlib
import re

from tests.css_source import read_css

BASE_JS = pathlib.Path("static/js/base.js").read_text(encoding="utf-8")
CSS = read_css()
BASE_HTML = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")


def _function(name):
    start = BASE_JS.index(f"window.{name} = function")
    return BASE_JS[start : BASE_JS.index("\n};", start)]


def test_the_menu_button_keeps_its_content_when_toggled():
    assert "textContent" not in _function("toggleMobMenu")
    assert not re.search(r"mob-menu-btn[^\n]*textContent|btn\.textContent\s*=\s*'[☰✕]'", BASE_JS)


def test_both_menu_icons_live_in_the_button_and_css_picks_one():
    button = re.search(r'<button id="mob-menu-btn".*?</button>', BASE_HTML, re.S).group(0)
    assert "nav-hamburger-open" in button and "nav-hamburger-close" in button
    assert '.nav-hamburger[aria-expanded="true"] .nav-hamburger-close' in CSS


def test_outside_click_reads_the_path_at_click_time():
    """الشجرةُ بعد مستمعٍ غيّرها لا تشهد على ما لُمس."""
    start = BASE_JS.index("window.toggleMobMenu")
    closer = BASE_JS[start : BASE_JS.index("/* ── PWA Install Banner", start)]
    assert "composedPath" in closer
    assert "sd-menu" in closer  # الفرعيّةُ العائمةُ بجانب اللوحة من «الداخل»


def test_closing_the_drawer_leaves_the_user_menu_alone():
    """مستمعُ «خارج اللوحة» يعمل بعد مستمع التفويض: لو أغلق القوائمَ كلَّها لأغلق
    قائمةَ المستخدم (#btn-user خارج اللوحة) لحظةَ فتحها — فلا خروجَ ولا تبديلَ دور."""
    start = BASE_JS.index("document.addEventListener('click', function(e) {\n  // المسارُ كما كان")
    closer = BASE_JS[start : BASE_JS.index("\n});", start)]
    code = "\n".join(line.split("//")[0] for line in closer.splitlines())
    assert "sdCloseAll" not in code
    assert ".sd-menu.sd-drawer.open" in code


def test_submenu_floats_beside_the_drawer_not_over_it():
    assert "(max-width: 640px)" in BASE_JS  # نقطةُ التحوّل نفسُها في CSS
    drawer = CSS[CSS.index(".nb-bar.nb-split") :]
    assert "inline-size: 50%" in drawer.split("}")[0]
    assert ".sd-menu.sd-drawer" in drawer
