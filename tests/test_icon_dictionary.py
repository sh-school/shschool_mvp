"""حارسُ قاموس الأيقونات — المعنى واحدٌ ورسمُه واحد، والورقةُ ناتجٌ لا يُحرَّر.

كان للمنصّة ستُّ طرقٍ لإظهار الأيقونة، وكان الشكلُ الواحدُ يحمل معانيَ لا صلةَ
بينها (`list-checks` لستّة بنودٍ في القائمة نفسها). والقاموسُ في
``core/icons.py`` يُنهي ذلك بشرط أن يبقى صادقاً، وهذه شروطُه:

* الورقةُ ``static/icons/sprite.svg`` تطابق مولّدَها بايتاً ببايت.
* لكلّ معنًى رمزٌ في الورقة، ولا رمزَ فيها بلا معنى.
* لا يتشارك معنيان رسماً — وإلّا عاد الشكلُ يحمل معنيين.
* كلُّ رسمٍ من المكتبة موجودٌ في مصدرها المقتطَع، والترخيصُ يرافقه.
* لا حرفَ لاتينيّاً داخل رسم، والمجموعةُ المحلّيّة لا تتجاوز سقفها.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from django.template import Context, Template, TemplateSyntaxError

from core import icon_sprite
from core.icons import (
    BADGES,
    DETAILED_AT,
    GROUPS,
    ICONS,
    MAX_LOCAL,
    VIOLATION_DEGREES,
    symbol_id,
)

ROOT = Path(__file__).resolve().parent.parent


def _render(src: str) -> str:
    return Template("{% load icons %}" + src).render(Context({}))


# ── الورقة ────────────────────────────────────────────────────────────────


def test_the_sprite_is_generated_not_edited():
    # نهايةُ السطر لا تُحسب: غيت على Windows يسحب الملفَّ بـCRLF
    on_disk = icon_sprite.SPRITE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert (
        on_disk == icon_sprite.build_sprite()
    ), "ورقةُ الرموز تخالف القاموس — شغّل: python manage.py build_icon_sprite"


def test_every_meaning_has_exactly_one_symbol_and_no_symbol_is_orphaned():
    ids = re.findall(r'<symbol id="([^"]+)"', icon_sprite.SPRITE.read_text(encoding="utf-8"))
    expected = (
        {symbol_id(k) for k in ICONS}
        | {symbol_id("behavior_violation", d) for d in VIOLATION_DEGREES}
        | {symbol_id(k, size=sizes[0]) for k, sizes in DETAILED_AT.items()}
    )
    assert len(ids) == len(set(ids)), "معرّفٌ مكرّر في الورقة"
    assert set(ids) == expected


def test_every_symbol_carries_its_arabic_name():
    sprite = icon_sprite.SPRITE.read_text(encoding="utf-8")
    for key, spec in ICONS.items():
        assert (
            f'<symbol id="{symbol_id(key)}" viewBox="0 0 24 24"><title>{spec.label}</title>'
            in sprite
        )


def test_the_sprite_has_no_hardcoded_colour():
    """الألوانُ رموزُ المنصّة — رقمٌ سداسيٌّ لا يتبع الوضعَ الداكن."""
    sprite = icon_sprite.SPRITE.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", sprite.split("-->", 2)[-1])


# ── القاموس ───────────────────────────────────────────────────────────────


def test_no_two_meanings_share_a_glyph():
    shared = {
        g: [k for k, s in ICONS.items() if s.glyph == g]
        for g, n in Counter(s.glyph for s in ICONS.values()).items()
        if n > 1
    }
    assert not shared, f"رسمٌ واحدٌ لمعنيين: {shared}"


def test_keys_are_snake_case_and_groups_are_known():
    for key, spec in ICONS.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*", key), key
        assert spec.group in GROUPS, (key, spec.group)
        assert spec.kind in ("hi", "cmp", "local"), (key, spec.glyph)


def test_every_library_glyph_is_in_the_vendored_source():
    icons = icon_sprite.library()["icons"]
    for key, spec in ICONS.items():
        if spec.kind == "hi":
            assert spec.source in icons, (key, spec.source)
        elif spec.kind == "cmp":
            base, badge = spec.source.split("+")
            assert base in icons, (key, base)
            assert badge in BADGES, (key, badge)


def test_the_vendored_source_carries_no_unused_glyph():
    """المصدرُ مقتطَعٌ بما يطلبه القاموس — لا ستّةُ آلاف رسمٍ في المستودع."""
    used = {"school"}
    for spec in ICONS.values():
        if spec.kind == "hi":
            used.add(spec.source)
        elif spec.kind == "cmp":
            used.add(spec.source.split("+")[0])
    assert set(icon_sprite.library()["icons"]) == used


def test_the_library_licence_ships_with_it():
    meta = json.loads(icon_sprite.SOURCE.read_text(encoding="utf-8"))
    assert meta["package"] == "@iconify-json/hugeicons" and meta["version"]
    licence = (icon_sprite.SOURCE.parent / "LICENSE-hugeicons.md").read_text(encoding="utf-8")
    assert licence.startswith("MIT License") and "Hugeicons" in licence


def test_the_local_set_stays_small():
    local = {s.source for s in ICONS.values() if s.kind == "local"}
    assert len(local) <= MAX_LOCAL, f"المجموعةُ المحلّيّة {len(local)} رسماً — السقف {MAX_LOCAL}"


def test_no_latin_letter_inside_any_glyph():
    """الرسمُ في منصّةٍ عربيّة لا يحمل A ولا XLS — الحرفُ إن لزم عربيّ."""
    sprite = icon_sprite.SPRITE.read_text(encoding="utf-8")
    for text in re.findall(r"<text[^>]*>([^<]*)</text>", sprite):
        assert not re.search(r"[A-Za-z]", text), text


# ── الوسم ─────────────────────────────────────────────────────────────────


def test_the_tag_points_at_the_external_sprite_by_meaning():
    html = _render('{% icon "absence" %}')
    assert 'class="icon icon-hg"' in html
    assert 'aria-hidden="true"' in html
    assert re.search(r'<use href="[^"]*icons/sprite\.svg#i-absence"></use>', html)


def test_a_directional_glyph_is_mirrored():
    assert "icon-mirror" in _render('{% icon "next" %}')
    assert "icon-mirror" not in _render('{% icon "print" %}')


def test_a_standalone_icon_is_named_for_screen_readers():
    html = _render('{% icon "close" label="إغلاق" %}')
    assert 'role="img"' in html and 'aria-label="إغلاق"' in html and "aria-hidden" not in html


def test_size_maps_to_an_existing_class():
    assert "icon-sm" in _render('{% icon "print" size="sm" %}')


def test_violation_degree_selects_its_own_symbol():
    assert "#i-violation-degree-3" in _render('{% icon "behavior_violation" degree=3 %}')


def test_the_wing_is_a_plain_star_in_menus_and_detailed_when_large():
    assert '#i-wings"' in _render('{% icon "wings" %}')
    assert "#i-wings-lg" in _render('{% icon "wings" size="2xl" %}')


def test_components_draw_a_meaning_with_the_new_sprite():
    html = _render('{% icon_named "library" size="2xl" %}')
    assert "icons/sprite.svg#i-library" in html and "icon-2xl" in html


def test_components_still_draw_a_legacy_name_during_the_migration():
    """الملفّاتُ الساخنة تُرحَّل في دفعةٍ لاحقة — والسقّاطةُ تمنع أن يزيد القديم."""
    assert '<use href="#icon-bar-chart"/>' in _render('{% icon_named "bar-chart" %}')


def test_components_refuse_a_name_from_neither_sprite():
    with pytest.raises(TemplateSyntaxError):
        _render('{% icon_named "📚" %}')


@pytest.mark.parametrize(
    "src",
    [
        '{% icon "list-checks" %}',
        '{% icon "print" size="huge" %}',
        '{% icon "behavior_violation" degree=5 %}',
        '{% icon "absence" degree=2 %}',
    ],
)
def test_misuse_fails_loudly(src):
    with pytest.raises(TemplateSyntaxError):
        _render(src)


TEMPLATES = ROOT / "templates"
ICON_TAG = re.compile(r'\{%\s*icon\s+"([^"]+)"')


def _icon_calls():
    for path in sorted(TEMPLATES.rglob("*.html")):
        for key in ICON_TAG.findall(path.read_text(encoding="utf-8")):
            yield path.relative_to(TEMPLATES).as_posix(), key


@pytest.mark.parametrize("path,key", sorted(set(_icon_calls())))
def test_every_requested_meaning_exists(path, key):
    """الوسمُ يسقط عند العرض — وهذا يسقط قبله، في صفحةٍ لم يفتحها اختبار."""
    assert key in ICONS, f"{path}: لا أيقونةَ بالمعنى {key!r}"


def test_the_shell_speaks_only_the_dictionary():
    """القائمةُ وشريطُ الهاتف والرأس: لا ورقةَ قديمة، ولا حرفَ يقوم مقامَ رسم."""
    base = (TEMPLATES / "base" / "base.html").read_text(encoding="utf-8")
    assert "components/icon.html" not in base
    for glyph in ("☰", "✕", "📲"):
        assert glyph not in base, glyph
    assert '<path stroke-linecap="round"' not in base, "رسمٌ مكتوبٌ داخل القالب"


def test_the_theme_toggle_carries_both_glyphs_from_the_dictionary():
    """base.js يُظهر أحدَهما — كان يكتب رسمَ الورقة القديمة بعد أوّل نقرة."""
    base = (TEMPLATES / "base" / "base.html").read_text(encoding="utf-8")
    assert base.count('data-theme-icon="dark"') == base.count('data-theme-icon="light"') >= 2
    js = (ROOT / "static" / "js" / "base.js").read_text(encoding="utf-8")
    assert "#icon-sun" not in js and "#icon-moon" not in js


LEGACY_BASELINE = ROOT / "tests" / "icon_legacy_baseline.json"
_LEGACY_INCLUDE = re.compile(r"components/icon\.html")
_LEGACY_USE = re.compile(r'<use href="#icon-')
_COMPONENT_ICON = re.compile(
    r"(?:\{%\s*(?:page_header|section_card|empty_state|action_tile)\b"
    r'|components/(?:ui/)?(?:empty_state|action_tile|page_header|section_card)\.html")'
    r'[^%]*?\bicon="([\w-]+)"'
)
_LEGACY_EXEMPT = {"components/sprite.html", "components/icon.html", "styleguide/icon_preview.html"}


def legacy_counts() -> dict[str, int]:
    """استعمالاتُ الورقة القديمة في كلّ قالب: استدعاءٌ، ومعاملُ مكوّنٍ باسمٍ قديم، و`<use>` مكتوب."""
    counts = {}
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel in _LEGACY_EXEMPT:
            continue
        text = path.read_text(encoding="utf-8")
        n = len(_LEGACY_INCLUDE.findall(text)) + len(_LEGACY_USE.findall(text))
        n += sum(1 for name in _COMPONENT_ICON.findall(text) if name not in ICONS)
        if n:
            counts[rel] = n
    return counts


def test_legacy_icons_only_shrink():
    """سقّاطة: القديمُ لا يزيد في ملفّ، ولا يدخل ملفّاً خلا منه.

    والنقصانُ لا يُلزم تحديثَ السجلّ — جلستان تُرحّلان معاً لا تتصادمان عليه.
    ولتسجيل الأعداد بعد ترحيل: ``python -m tests.test_icon_dictionary``.
    """
    baseline = json.loads(LEGACY_BASELINE.read_text(encoding="utf-8"))
    grown = {
        f: (baseline.get(f, 0), n) for f, n in legacy_counts().items() if n > baseline.get(f, 0)
    }
    assert not grown, f"أيقوناتٌ قديمةٌ زادت (المسجَّل، الآن) — استعمل {{% icon %}}: {grown}"


def test_the_new_icon_classes_are_styled():
    css = (ROOT / "static" / "css" / "custom.css").read_text(encoding="utf-8")
    assert ".icon-hg" in css and ".icon-mirror" in css


if __name__ == "__main__":
    counts = legacy_counts()
    LEGACY_BASELINE.write_text(
        json.dumps(counts, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"سُجّل {sum(counts.values())} استعمالاً قديماً في {len(counts)} قالباً")
