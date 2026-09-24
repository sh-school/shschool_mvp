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
        ("--nav-bg", "nav-bg"),
        ("--nav-fg", "maroon-dark"),
        ("--nav-mark", "maroon"),
        ("--menu-label", "menu-label"),
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
        ("--nav-bg", "nav-bg"),
    ):
        assert f"{admin_var}: {_token(themes, token)};" in dark, (admin_var, token)


def test_the_admin_page_fade_is_the_platform_fade():
    """مدّةُ التلاشي رمزٌ واحدٌ وحركةُ الظهور واحدة — نُقلا حرفيّاً كألوان الهويّة، فلا يتباعد الانتقالان (قرارُ المالك 2026-09-24)."""
    platform_token = re.search(
        r"--transition-page:\s*([^;]+);", (CUSTOM / "10-foundation.css").read_text(encoding="utf-8")
    )
    admin = ADMIN.read_text(encoding="utf-8")
    admin_token = re.search(r"--transition-page:\s*([^;]+);", admin)
    assert platform_token and admin_token
    assert admin_token.group(1).strip() == platform_token.group(1).strip()

    def keyframes(css: str) -> str:
        return " ".join(re.search(r"@keyframes page-in\s*\{.*?\}\s*\}", css, re.S).group(0).split())

    assert keyframes(admin) == keyframes((CUSTOM / "20-components.css").read_text(encoding="utf-8"))
    for rule in (
        "animation: page-in var(--transition-page) backwards;",
        "transition: opacity var(--transition-page);",
    ):
        assert rule in admin, rule

    # المزجُ الأصليُّ بين الصفحتين (`@view-transition`) بالمدّة نفسِها — وحدةُ `animation-duration` لا تقبل الرمزَ المركَّب فتُكرَّر.
    duration = admin_token.group(1).split()[0]
    assert re.search(
        rf"::view-transition-group\(root\)\s*\{{\s*animation-duration:\s*{re.escape(duration)}\s*;",
        admin,
    )
    assert re.search(
        r"prefers-reduced-motion:\s*no-preference\)\s*\{\s*@view-transition\s*\{\s*navigation:\s*auto;",
        admin,
    )


def test_the_admin_hands_the_page_mix_to_the_browser_and_keeps_the_js_fade_as_fallback():
    """صفحاتُ الإدارة تُحمَّل كاملةً (أدواتُها تهيَّأ عند load): المزجُ للمتصفّح حيث يدعمه، والتلاشي بـJS ولا شيءَ سواه حيث لا يدعمه."""
    admin = ADMIN.read_text(encoding="utf-8")
    assert "@supports not at-rule(@view-transition)" in admin
    fallback = admin[admin.index("@supports not at-rule(@view-transition)") :]
    assert fallback.index("#content-start.is-leaving > *") < fallback.index(
        ".adm-nav__item.is-fading"
    )
    js = pathlib.Path("static/js/page-nav.js").read_text(encoding="utf-8")
    assert "at-rule(@view-transition)" in js and "FADE_ONLY && NATIVE_VT" in js


def test_the_admin_preloads_the_fonts_its_header_uses():
    """بلا تحميلٍ مسبقٍ يُرسم نصُّ الترويسة بخطٍّ بديلٍ لحظةً ثمّ يتبدّل عند كلّ صفحة (وميض)."""
    base = pathlib.Path("templates/admin/base_site.html").read_text(encoding="utf-8")
    css = ADMIN.read_text(encoding="utf-8")
    for weight in ("Regular", "Medium", "Bold"):
        assert f"fonts/Tajawal-{weight}.woff2" in base and f"fonts/Tajawal-{weight}.woff2" in css
    assert base.count('rel="preload"') >= 3 and "crossorigin" in base


def test_dropdown_menus_share_the_nav_colour_on_both_surfaces():
    """القوائمُ المنسدلة بلونِ القائمة الرئيسيّة نفسِه لا أبيضَ ثابتاً (طلبُ المالك 2026-09-24).

    رمزٌ واحدٌ `--menu-bg: var(--nav-bg)` — من غيّر لونَ القائمة تبعته قوائمُها في المنصّة والإدارة
    نهاراً وليلاً، ولا يُكتب لونٌ ثانٍ للقائمة المنسدلة ينجرف عنها.
    """
    platform = (CUSTOM / "10-foundation.css").read_text(encoding="utf-8")
    themes = (CUSTOM / "40-themes.css").read_text(encoding="utf-8")
    admin = ADMIN.read_text(encoding="utf-8")

    same = re.compile(r"--menu-bg:\s*var\(--nav-bg\)\s*;")
    for css in (platform, admin):
        assert same.search(css)
    assert "--menu-bg" not in themes  # نظيرٌ ليليٌّ خاصٌّ بالقائمة المنسدلة هو ما يفصلها عن القائمة
    assert admin.count("--menu-bg:") == 1
    # ولا خلفيّةَ ثابتةَ البياض على القائمة المنسدلة في المنصّة ولا الإدارة
    components = (CUSTOM / "20-components.css").read_text(encoding="utf-8")
    assert re.search(r"\.sd-menu\s*\{[^}]*background:\s*var\(--menu-bg\)", components)
    assert re.search(r"\.adm-nav__menu\s*\{[^}]*background:\s*var\(--menu-bg\)", admin)


def _raw(css: str, name: str) -> str:
    match = re.search(rf"^\s*--{re.escape(name)}\s*:\s*([^;]+);", css, re.M)
    assert match, name
    return " ".join(match.group(1).split())


def test_the_dropdown_shadow_is_the_platform_token_on_both_surfaces():
    """ظلُّ القائمة المنسدلة رمزٌ واحد `--shadow-menu` في المنصّة والإدارة نهاراً وليلاً (طلبُ المالك 2026-09-24)."""
    platform = (CUSTOM / "10-foundation.css").read_text(encoding="utf-8")
    themes = (CUSTOM / "40-themes.css").read_text(encoding="utf-8")
    admin = ADMIN.read_text(encoding="utf-8")

    light = _admin_block(admin, 'html[data-theme="light"]')
    dark = _admin_block(admin, 'html[data-theme="dark"]')
    assert _raw(light, "shadow-menu") == _raw(platform, "shadow-menu")
    assert _raw(dark, "shadow-menu") == _raw(themes, "shadow-menu")
    assert re.search(r"\.adm-nav__menu\s*\{[^}]*box-shadow:\s*var\(--shadow-menu\)", admin)


def test_header_and_footer_are_one_colour_on_both_surfaces():
    """الذيلُ لونُ الترويسة نفسُه، نهاراً وليلاً، في المنصّة وفي الإدارة (قرارُ المالك 2026-09-24).

    رمزٌ واحدٌ يقرؤه الاثنان — `--footer-bg: var(--header-bg)` — فلا يُكتب لونٌ ثانٍ للذيل
    ينجرف عن الترويسة. ونظيرٌ ليليٌّ يُعرَّف للذيل وحدَه هو بالذات ما يفصله عنها.
    """
    platform = (CUSTOM / "10-foundation.css").read_text(encoding="utf-8")
    themes = (CUSTOM / "40-themes.css").read_text(encoding="utf-8")
    admin = ADMIN.read_text(encoding="utf-8")

    for css in (platform, admin):
        assert re.search(r"--footer-bg:\s*var\(--header-bg\)\s*;", css)
    assert "--footer-bg" not in themes
    assert admin.count("--footer-bg:") == 1


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


BRAND_COMPONENT = pathlib.Path("templates/components/site_brand.html")
LINE_COMPONENT = pathlib.Path("templates/components/site_footer_line.html")


def test_both_footer_logos_sit_on_a_white_chip_of_the_same_height():
    html = BRAND_COMPONENT.read_text(encoding="utf-8")
    assert html.count('class="site-footer-brand-logo-chip"') == 2
    assert html.count('height="28"') == 2
    css = ADMIN.read_text(encoding="utf-8")
    assert "background: #fff" in _admin_rule(css, ".adm-footer .site-footer-brand-logo-chip")
    assert "block-size: 1.75rem" in _admin_rule(css, ".adm-footer .site-footer-brand-logo")


def test_the_footer_has_one_source_for_the_platform_and_the_admin():
    """OWN-22: ذيلُ المنصّة وذيلُ الإدارة يضمّنان المكوّنَين نفسَيهما — لا نسخةَ ثالثةً تنجرف.

    كانت ثلاثُ نسخٍ من الرؤية والتوقيع (`base.html` والإدارةُ والمكوّن)، فتعديلُ شعارٍ في
    إحداها يُنسى في الأخرى. والنصُّ الحرفيُّ للتوقيع في المكوّن وحدَه.
    """
    platform = pathlib.Path("templates/base/base.html").read_text(encoding="utf-8")
    admin_footer = FOOTER_TEMPLATE.read_text(encoding="utf-8")
    for html in (platform, admin_footer):
        assert '{% include "components/site_footer_line.html" %}' in html
        assert '{% include "components/site_brand.html" %}' in html
    owners = [
        path.as_posix()
        for path in pathlib.Path("templates").rglob("*.html")
        if "أذكياء للبرمجيات</span>" in path.read_text(encoding="utf-8")
    ]
    assert owners == [BRAND_COMPONENT.as_posix()], owners
    assert "وزارة التربية والتعليم والتعليم العالي — دولة قطر" in LINE_COMPONENT.read_text(
        encoding="utf-8"
    )


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


def test_the_nav_search_field_reads_the_nav_tokens_not_the_white_of_the_header():
    """حقلُ بحث الإدارة كان بنصٍّ أبيضَ على رملٍ فاتح (1.11:1) — أسقطه axe في CI (#547).

    كلُّ ما يُرسم داخل شريط القائمة يقرأ `--nav-fg` و`--nav-hover`، لا بياضَ الترويسة العنّابيّة؛ فمن
    غيّر لونَ القائمة تبعه الحقلُ نهاراً وليلاً بلا موضعٍ ثانٍ يُصلَح.
    """
    admin = ADMIN.read_text(encoding="utf-8")
    field = _admin_rule(admin, ".adm-nav__search-input")
    assert "var(--nav-fg)" in field and "var(--nav-hover)" in field
    assert "--header-link-color" not in field and "#fff" not in field
    assert "var(--nav-fg)" in _admin_rule(admin, ".adm-nav__search-input::placeholder")


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
    assert ".adm-nav__btn, #header .adm-nav__menu a { min-block-size: var(--adm-control-h);" in css


def test_the_admin_touch_minimum_is_the_platform_token():
    """`--adm-control-h` نسخةٌ حرفيّةٌ من `--control-h` — فإن غُيّر الحدُّ في المنصّة تغيّر هنا أو سقط هذا."""
    platform = re.findall(
        r"--control-h\s*:\s*([^;]+);", (CUSTOM / "10-foundation.css").read_text(encoding="utf-8")
    )
    admin = re.findall(r"--adm-control-h\s*:\s*([^;]+);", ADMIN.read_text(encoding="utf-8"))

    assert platform and admin == platform, (platform, admin)


def test_no_admin_touch_minimum_is_written_44px():
    """كما `test_touch_target_token` للمنصّة: الحدُّ يُكتب `var(--adm-control-h)` لا رقماً."""
    css = ADMIN.read_text(encoding="utf-8")
    assert not re.findall(r"\bmin-(?:height|width|block-size|inline-size)\s*:\s*44px", css)


def test_phone_touch_rules_cover_the_admin_controls():
    """قيسَت 736 هدفاً دون الحدّ — القواعدُ تسمّي الأصنافَ التي وُجدت، لا تخمّن."""
    css = ADMIN.read_text(encoding="utf-8")
    block = css[css.index("أهدافُ اللمس على الجوّال في صفحات الإدارة") :]
    block = block[: block.index("\n}\n", block.index("@media")) + 3]
    for selector in (
        "#user-tools :is(a, button)",
        "a.addlink",
        ".related-widget-wrapper-link",
        ".datetimeshortcuts a",
        ".selector button",
        ".app-fold__summary",
        "#changelist-filter summary",
        "select",
        "textarea",
    ):
        assert selector in block, selector
    assert "var(--adm-control-h)" in block and "44px" not in block
