"""لوحةُ الإدارة تَرِث ألوانَ المنصّة: القيمُ المنقولةُ إلى `admin_theme.css` تطابق رموزَ المنصّة.

لوحةُ الإدارة لا تحمل ملفّات المنصّة، فنُقلت قيمُها حرفيّاً — وهذا الاختبارُ يمنع أن تنجرف
إن غُيّر رمزٌ في المنصّة ونُسي هنا.
"""

import pathlib
import re

CUSTOM = pathlib.Path("static/css/custom")
ADMIN = pathlib.Path("static/css/admin_theme.css")


def _token(text: str, name: str) -> str:
    match = re.search(rf"^\s*--{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{3,8}})", text, re.M)
    assert match, name
    return match.group(1).lower()


def _admin_block(css: str, selector_start: str) -> str:
    start = css.index(selector_start)
    return css[start : css.index("}", start)]


def test_light_admin_colours_are_the_platform_tokens():
    platform = (CUSTOM / "10-foundation.css").read_text(encoding="utf-8")
    light = _admin_block(ADMIN.read_text(encoding="utf-8"), 'html[data-theme="light"]')

    for admin_var, token in (
        ("--primary", "maroon"),
        ("--header-bg", "maroon"),
        ("--button-bg", "maroon"),
        ("--accent", "gold"),
        ("--button-hover-bg", "maroon-dark"),
        ("--breadcrumbs-bg", "maroon-dark"),
        ("--body-fg", "text-primary"),
        ("--body-quiet-color", "text-secondary"),
        ("--border-color", "border-strong"),
        ("--hairline-color", "border"),
        ("--darkened-bg", "surface-alt"),
    ):
        assert f"{admin_var}: {_token(platform, token)};" in light, (admin_var, token)


def test_dark_admin_colours_are_the_platform_dark_tokens():
    themes = (CUSTOM / "40-themes.css").read_text(encoding="utf-8")
    dark = _admin_block(ADMIN.read_text(encoding="utf-8"), 'html[data-theme="dark"]')

    for admin_var, token in (
        ("--body-fg", "text-primary"),
        ("--body-quiet-color", "text-secondary"),
        ("--body-bg", "page-bg"),
        ("--darkened-bg", "surface"),
        ("--hairline-color", "border"),
        ("--border-color", "border-strong"),
        ("--link-fg", "maroon-fg"),
    ):
        assert f"{admin_var}: {_token(themes, token)};" in dark, (admin_var, token)


def test_the_admin_uses_the_platform_favicon():
    base = pathlib.Path("templates/admin/base_site.html").read_text(encoding="utf-8")
    platform = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")

    assert "icons/favicon.png" in base and "icons/favicon.png" in platform
    assert "css/admin_theme.css" in base


# ── فوتر لوحة الإدارة = فوتر المنصّة (قرارُ المالك 2026-09-23) ─────────────────────────────

FOOTER_TEMPLATE = pathlib.Path("templates/admin/_footer.html")


def test_the_admin_footer_has_no_app_name_or_version():
    html = FOOTER_TEMPLATE.read_text(encoding="utf-8")
    assert "platform_version" not in html and "SchoolOS" not in html


def test_both_footer_logos_sit_on_a_white_chip_of_the_same_height():
    html = FOOTER_TEMPLATE.read_text(encoding="utf-8")
    assert html.count('class="adm-footer__chip"') == 2
    assert html.count('height="28"') == 2
    css = ADMIN.read_text(encoding="utf-8")
    assert "background: #fff" in _admin_rule(css, ".adm-footer__chip")
    assert "block-size: 1.75rem" in _admin_rule(css, ".adm-footer__logo")


def test_the_admin_footer_is_one_three_section_row_on_desktop_after_the_base_rules():
    """قاعدةُ الحاسوب بعد الأساسيّة: بالأولويّة نفسها يحسم الأخير، وإلا غلبت `center` على `start`."""
    css = ADMIN.read_text(encoding="utf-8")
    base = css.index(".adm-footer { margin-block-start")
    desktop = css.index("grid-template-columns: 1fr auto 1fr")
    assert desktop > base
    assert "var(--accent)" in _admin_rule(css, ".adm-footer")


def test_the_vision_is_drawn_with_the_platform_tashkeel_font():
    css = ADMIN.read_text(encoding="utf-8")
    assert css.count("font-family: 'Tajawal Tashkeel';") >= 3
    assert "--tashkeel-dark" in css and ".vision-text" in css
    for weight in ("Regular", "Medium", "Bold"):
        assert pathlib.Path(f"static/fonts/Tajawal-{weight}-tk.woff2").exists()


def _admin_rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


# ── بنيةُ الوصولية: معلَمٌ واحدٌ وعنصرٌ تفاعليٌّ واحدٌ لكلّ موضع (axe: nested-interactive و landmark-*) ──────


def test_the_admin_footer_is_not_a_second_contentinfo_landmark():
    """جانغو يلفّ الكتلةَ بـ`<footer id="footer">`؛ وسمٌ ثانٍ أو role=contentinfo يكرّر المعلَم ويعشّشه."""
    html = FOOTER_TEMPLATE.read_text(encoding="utf-8")
    assert "<footer" not in html.replace("{% comment %}", "").split("{% endcomment %}")[-1]
    assert "contentinfo" not in html.split("{% endcomment %}")[-1]


def test_the_app_fold_summary_holds_no_link():
    """رابطٌ داخل `<summary>` عنصرٌ تفاعليٌّ داخل عنصرٍ تفاعليّ — 21 موضعاً في الرئيسيّة كانت تُخالف axe."""
    import re

    html = pathlib.Path("templates/admin/app_list.html").read_text(encoding="utf-8")
    for summary in re.findall(r"<summary.*?</summary>", html, flags=re.S):
        assert "<a " not in summary and "<button" not in summary, summary


# ── قائمةُ الإدارة على الجوّال: سطرٌ واحدٌ مطويّ، وتعزيزٌ تدريجيّ (بلا سكربتٍ تبقى مفتوحة) ──────────


def test_the_mobile_nav_toggle_is_hidden_until_the_script_shows_it():
    html = pathlib.Path("templates/admin/_nav.html").read_text(encoding="utf-8")
    toggle = html[html.index('class="adm-nav__btn adm-nav__toggle"') :]
    toggle = toggle[: toggle.index("</button>")]
    assert (
        " hidden" in toggle
        and 'aria-controls="adm-nav"' in toggle
        and 'aria-expanded="false"' in toggle
    )
    assert 'id="adm-nav"' in html


def test_the_nav_collapses_only_on_phones_and_only_when_the_script_ran():
    css = ADMIN.read_text(encoding="utf-8")
    assert ".adm-nav__toggle { display: none; }" in css
    block = css[css.index(".adm-nav.has-toggle .adm-nav__toggle") - 40 :]
    assert (
        block.lstrip().startswith("@media (max-width: 767px)")
        or "@media (max-width: 767px) {\n  .adm-nav.has-toggle" in css
    )
    assert ".adm-nav.has-toggle:not(.is-expanded) > .adm-nav__item" in css
    js = pathlib.Path("static/js/admin_nav.js").read_text(encoding="utf-8")
    assert "classList.add('has-toggle')" in js and "toggle.hidden = false" in js


def test_nav_touch_targets_are_44px_on_phones():
    css = ADMIN.read_text(encoding="utf-8")
    assert ".adm-nav__btn, #header .adm-nav__menu a { min-block-size: 44px;" in css
