"""التنقّلُ بتبديل المحتوى مركزيٌّ في القالب الأساس — لا ربطَ لكلّ صفحةٍ أو قائمةٍ فرعيّة (قرارُ المالك 2026-09-20).

يعمل `static/js/page-nav.js` على مستوى المستند كلِّه، فأيّ رابطٍ أو نموذجٍ في أيّ صفحةٍ (جديدةٍ أو قائمةٍ فرعيّةٍ جديدة)
يُبدَّل محتواه بلا تحميلٍ كامل، ما دامت الصفحةُ من `base/base.html`. فهنا يُحرَس أنّ القالبَ يحمل ما يلزمه، وأنّ الحركةَ من
رمز الهويّة لا من رقمٍ مكتوب.
"""

import pathlib
import re

BASE = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")
JS = pathlib.Path("static/js/page-nav.js").read_text(encoding="utf-8")
CSS = pathlib.Path("static/css/custom/20-components.css").read_text(encoding="utf-8")


def test_the_base_template_carries_the_shell_the_script_swaps():
    assert "data-page-nav" in BASE
    for hook in ('id="main-content"', 'id="crumbs"', 'id="page-msgs"'):
        assert hook in BASE, hook
    assert "js/page-nav.js" in BASE


def test_the_fade_comes_from_the_identity_token_not_a_number_in_js():
    assert re.search(r"transition:\s*opacity\s+var\(--transition-page\)", CSS)
    # لا مدّةً بالمللي ثانية مكتوبةً في السكربت: يقرأ الرمزَ نفسَه من `:root`.
    assert "--transition-page" in JS and "FADE_MS" not in JS


def test_the_entrance_is_a_keyframe_animation_not_a_class_toggled_transition():
    """الظهورُ فجأةً كان لأنّ التدرّج يتوقّف على إزالة صنفٍ في اللحظة نفسها؛ الحركةُ تبدأ بإدراج العنصر."""
    assert "@keyframes page-in" in CSS and "animation: page-in var(--transition-page)" in CSS
    assert "is-entering" not in JS and "requestAnimationFrame" not in JS


def test_no_section_sub_menu_remains():
    """قرارُ المالك 2026-09-20: القائمةُ الرئيسيّةُ بالمرور تكفي — لا شريطَ قسمٍ فرعيّاً ولا شيفرتَه."""
    assert "section-nav" not in CSS and "section-nav" not in JS
    assert not pathlib.Path("core/section_navs.py").exists()


def test_a_click_on_the_current_page_reloads_nothing():
    """النقرةُ الثانيةُ على مفتاحٍ في القائمة الرئيسيّة أو فرعيّتها لا تعيد التحميل."""
    assert "a.pathname === location.pathname && a.search === location.search" in JS
    assert "closeMenus(); return;" in JS


def test_the_main_menu_opens_on_hover_with_intent_delays_and_escape():
    js = pathlib.Path("static/js/base.js").read_text(encoding="utf-8")
    assert "(hover: hover) and (pointer: fine)" in js
    assert "OPEN_MS" in js and "CLOSE_MS" in js and "'Escape'" in js
    assert "function markCurrentSection" in js
