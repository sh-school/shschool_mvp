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
from core.icons import BADGES, GROUPS, ICONS, MAX_LOCAL, VIOLATION_DEGREES, symbol_id

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
    expected = {symbol_id(k) for k in ICONS} | {
        symbol_id("behavior_violation", d) for d in VIOLATION_DEGREES
    }
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


def test_the_new_icon_classes_are_styled():
    css = (ROOT / "static" / "css" / "custom.css").read_text(encoding="utf-8")
    assert ".icon-hg" in css and ".icon-mirror" in css
