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
    assert "fadeMenus(); return;" in JS


# ── القوائمُ المنسدلة تتلاشى من لحظة النقر (قرارُ المالك 2026-09-24) ───────────────────────────


def test_a_menu_fades_from_the_click_not_after_the_swap():
    """كانت القائمةُ تبقى مفتوحةً 500ms بعد النقر (ما دام المحتوى يتلاشى) ثمّ تختفي فجأةً عند التبديل."""
    go = JS[JS.index("function go(") : JS.index("function go(") + 700]
    assert "fadeMenus();" in go.split("Promise.all")[0], "التلاشي يبدأ مع `is-leaving` لا بعد الردّ"
    assert "setTimeout(closeMenus, fadeMs())" in JS, "تُغلق بعد مدّة تلاشي الصفحة نفسِها لا برقمٍ آخر"


def test_the_menu_fade_uses_the_page_token_and_is_not_cut_by_hover_closers():
    assert re.search(
        r"\.sd-menu\.is-fading\s*\{[^}]*animation:\s*sdFadeOut\s+var\(--transition-page\)", CSS
    )
    base = pathlib.Path("static/js/base.js").read_text(encoding="utf-8")
    assert "'.sd-menu.open:not(.is-fading)'" in base, "مؤشّرٌ يخرج من قائمةٍ تتلاشى لا يقطعها"
    admin_nav = pathlib.Path("static/js/admin_nav.js").read_text(encoding="utf-8")
    assert "item.classList.contains('is-fading')" in admin_nav
    # نقرةٌ عاديّةٌ على رابطٍ في قائمة الإدارة لا تُغلقها `admin_nav.js` فوراً — كان هذا سببَ الاختفاء المفاجئ قبل أن يُخفتها page-nav.
    assert "e.target.closest('.adm-nav__menu a[href]')" in admin_nav


def test_leaving_restores_the_content_when_the_page_is_restored_or_no_navigation_happens():
    """`is-leaving` يبقى على الصفحة المحفوظة (bfcache) وعلى صفحةٍ كان انتقالُها تنزيلاً — فيبقى المحتوى شفّافاً."""
    assert "'pageshow'" in JS and "e.persisted" in JS
    assert "function restoreLater" in JS and "restoreLater(); window.location.href = url" in JS


# ── لوحةُ الإدارة: الآليّةُ نفسُها بنمط fade ────────────────────────────────────────────────────


def test_the_admin_loads_the_same_script_in_fade_mode_and_never_swaps_its_dom():
    base = pathlib.Path("templates/admin/base_site.html").read_text(encoding="utf-8")
    tag = re.search(r"<script[^>]*js/page-nav\.js[^>]*>", base)
    assert tag, "لوحةُ الإدارة لا تحمل page-nav.js"
    assert 'data-page-nav="fade"' in tag.group(
        0
    ) and 'data-page-nav-root="#content-start"' in tag.group(0)
    # نمطُ fade يخرج قبل معالجَي النماذج والسجلّ: صفحاتُ الإدارة تهيّئ أدواتِها عند load فلا يصحّ تبديلُ DOM فيها.
    assert JS.index("if (FADE_ONLY) return;") < JS.index("addEventListener('submit'")
    assert JS.index("if (FADE_ONLY) return;") < JS.index("addEventListener('popstate'")


def test_the_admin_fade_root_and_popups_are_excluded():
    assert "document.body.classList.contains('popup')" in JS
    admin = pathlib.Path("static/css/admin_theme.css").read_text(encoding="utf-8")
    assert (
        "body:not(.popup) #content-start > *" in admin
        and "body:not(.popup) #content-start.is-leaving > *" in admin
    )
    assert "@media (prefers-reduced-motion: reduce)" in admin


def test_the_main_menu_opens_on_hover_with_intent_delays_and_escape():
    js = pathlib.Path("static/js/base.js").read_text(encoding="utf-8")
    assert "(hover: hover) and (pointer: fine)" in js
    assert "OPEN_MS" in js and "CLOSE_MS" in js and "'Escape'" in js
    assert "function markCurrentSection" in js
