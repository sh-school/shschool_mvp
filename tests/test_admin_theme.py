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
