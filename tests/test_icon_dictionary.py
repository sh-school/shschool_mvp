"""حارسُ قاموس الأيقونات — المعنى واحدٌ ورسمُه واحد، والورقةُ ناتجٌ لا يُحرَّر.

كان للمنصّة ستُّ طرقٍ لإظهار الأيقونة، وكان الشكلُ الواحدُ يحمل معانيَ لا صلةَ
بينها (`list-checks` لستّة بنودٍ في القائمة نفسها). والقاموسُ في
``core/icons.py`` يُنهي ذلك بشرط أن يبقى صادقاً، وهذه شروطُه:

* الورقةُ ``static/icons/sprite.svg`` تطابق مولّدَها بايتاً ببايت.
* لكلّ معنًى رمزٌ في الورقة، ولا رمزَ فيها بلا معنى.
* لا يتشارك معنيان رسماً — وإلّا عاد الشكلُ يحمل معنيين.
* كلُّ رسمٍ من المكتبة موجودٌ في مصدرها المقتطَع، والترخيصُ يرافقه.
* لا حرفَ لاتينيّاً داخل رسم، والمجموعةُ المحلّيّة لا تتجاوز سقفها.
* لا سكربتَ يكتب مرجعاً لرمزٍ ليس في الورقة (الحارسُ يمسح `*.js` كما يمسح `*.html`).
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
from tests.css_source import read_css

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


def test_components_skip_a_missing_icon_without_erroring():
    assert _render('{% icon_named "" %}') == ""


def test_components_refuse_an_unknown_meaning():
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


# ── لوحة الأوامر (core/views_search.py) — JSON لا وسمٌ، فلا يسقط عند العرض ──

_SEARCH_VIEW = ROOT / "core" / "views_search.py"
_SEARCH_ICON_RE = re.compile(r'"icon":\s*"([^"]*)"')


def _search_view_icon_keys():
    return sorted(set(_SEARCH_ICON_RE.findall(_SEARCH_VIEW.read_text(encoding="utf-8"))))


@pytest.mark.parametrize("key", _search_view_icon_keys())
def test_the_command_palette_names_a_real_meaning(key):
    """كانت نتائجُ Ctrl+K إيموجي خاماً (🎓👨‍🏫🏠…) — رسمٌ موازٍ خارج القاموس
    تماماً، لا يمرّ على `{% icon %}` فلا يحرسه شيء. صار كلُّ عنصرٍ مفتاحاً
    دلاليّاً يرسمه `static/js/app.js` من الورقة نفسها التي يرسمها الوسم —
    فهذا الحارسُ يمنع عودة رمزٍ خامٍّ، والتصيير الفعليّ في المتصفّح يبقى
    خارج نطاق هذا الملفّ الساكن.
    """
    assert key, "قيمةُ icon فارغة في core/views_search.py"
    assert key in ICONS, f"core/views_search.py: لا أيقونةَ بالمعنى {key!r}"


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


_LEGACY_ICON_INCLUDE = re.compile(r"components/icon\.html")
_LEGACY_SPRITE_INCLUDE = re.compile(r"components/sprite\.html")
_LEGACY_USE = re.compile(r'<use href="#icon-')
_COMPONENT_ICON = re.compile(
    r"(?:\{%\s*(?:page_header|section_card|empty_state|action_tile)\b"
    r'|components/(?:ui/)?(?:empty_state|action_tile|page_header|section_card)\.html")'
    r'[^%]*?\bicon="([\w-]+)"'
)
#: مجلّداتٌ لا تُفحص — وليس ``templates/`` وحده: كان لِـexam_control
#: وdeveloper_feedback مجلّدا قوالبَ محليّان داخل التطبيق خارج ذلك المسح، فبقيت
#: 16 قالباً (35+ استعمالاً قديماً) معطوبةَ الأيقونات على الإنتاج بلا رصدٍ حتى
#: اكتُشفت يدويّاً 2026-09-18 — فهذا الحارسُ يمسح المشروعَ كلَّه.
_SKIP_DIRS = {".git", "node_modules", ".venv", "staticfiles"}


def _legacy_icon_usages() -> dict[str, list[str]]:
    """كلُّ استعمالٍ للورقة القديمة (المحذوفة) في أيّ قالبٍ بالمشروع."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(ROOT.rglob("*.html")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = []
        if _LEGACY_ICON_INCLUDE.search(text):
            hits.append("include components/icon.html")
        if _LEGACY_SPRITE_INCLUDE.search(text):
            hits.append("include components/sprite.html")
        if _LEGACY_USE.search(text):
            hits.append('<use href="#icon-...">')
        bad_names = sorted({n for n in _COMPONENT_ICON.findall(text) if n not in ICONS})
        if bad_names:
            hits.append(f"icon=معنًى غيرُ موجود {bad_names}")
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    return offenders


def test_no_template_anywhere_in_the_project_uses_the_legacy_icon_sheet():
    """الورقةُ القديمة (``components/sprite.html``/``icon.html``) محذوفةٌ نهائيّاً
    2026-09-18 — لا استثناءَ يُبقيها، ولا مصدرَ يُرضي استعمالاً قديماً بعد اليوم.
    """
    offenders = _legacy_icon_usages()
    assert not offenders, offenders


def test_the_new_icon_classes_are_styled():
    css = read_css()
    assert ".icon-hg" in css and ".icon-mirror" in css


# ── السكربتات ─────────────────────────────────────────────────────────────
# الحارسُ أعلاه يمسح `*.html` وحدَها، والسكربتُ يكتب `<svg><use>` نصّاً في
# `innerHTML` فلا يمرّ على وسمٍ ولا على مسحٍ. وحوارُ التأكيد في `base.js` كان
# يكتب `#icon-alert-triangle` من ورقةٍ حُذفت، فيظهر عنوانُه بلا رسم — ولا يسقط
# شيءٌ لأنّ المتصفّح لا يُبلغ عن `<use>` لا يجد هدفَه. وصوابُ السكربت أن يبني
# المسارَ من `data-icon-sprite` في `<body>` كما يفعل الوسمُ و`static/js/app.js`.

_JS_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\\\"'])//[^\n]*", re.S)
#: `<use href="#…">` — الورقةُ خارجيّةٌ، فأيُّ مرجعٍ يبدأ بـ`#` لا هدفَ له في الصفحة.
_JS_LOCAL_USE = re.compile(r"""<use\b[^>]*?\b(?:xlink:)?href\s*=\s*["']#""")
_JS_LEGACY_ID = re.compile(r"#icon-[\w-]+")
#: معرّفٌ مكتوبٌ كاملاً (`…sprite.svg#i-status_warning`) — أمّا `'#i-' + key` فيُبنى
#: وقتَ التشغيل ويحرسه `test_the_command_palette_names_a_real_meaning` بمفاتيحه.
_JS_SYMBOL_ID = re.compile(r"#(i-[a-z0-9_-]+)")
_JS_SKIP_PARTS = {"vendor", "node_modules"}


def js_icon_problems(js: str, symbols: set[str]) -> list[str]:
    """كلُّ مرجعِ أيقونةٍ في سكربتٍ لا يجد رمزَه في الورقة."""
    code = _JS_COMMENT.sub("", js)
    problems = [
        f"مرجعٌ محلّيٌّ لا هدفَ له (الورقةُ خارجيّة): {m.group(0)}…" for m in _JS_LOCAL_USE.finditer(code)
    ]
    problems += [
        f"معرّفٌ من الورقة القديمة المحذوفة: {m.group(0)}" for m in _JS_LEGACY_ID.finditer(code)
    ]
    problems += [
        f"رمزٌ ليس في sprite.svg: #{m.group(1)}"
        for m in _JS_SYMBOL_ID.finditer(code)
        if m.group(1) not in symbols
    ]
    return problems


def _project_scripts() -> list[Path]:
    """سكربتاتُ المنصّة الحيّة: `static/js` وأيُّ `<app>/static` وقوالبُ الـPWA."""
    found = [
        *ROOT.glob("static/js/*.js"),
        *ROOT.glob("*/static/**/*.js"),
        *ROOT.glob("templates/**/*.js"),
    ]
    return sorted(
        p
        for p in set(found)
        if not p.name.endswith(".min.js") and not _JS_SKIP_PARTS & set(p.relative_to(ROOT).parts)
    )


def _sprite_symbols() -> set[str]:
    sprite = icon_sprite.SPRITE.read_text(encoding="utf-8")
    return set(re.findall(r'<symbol id="([^"]+)"', sprite))


def test_no_script_references_an_icon_the_sprite_lacks():
    symbols = _sprite_symbols()
    offenders = {
        path.relative_to(ROOT).as_posix(): problems
        for path in _project_scripts()
        if (problems := js_icon_problems(path.read_text(encoding="utf-8"), symbols))
    }
    assert not offenders, offenders


def test_the_script_scan_covers_the_shell_scripts():
    """مسحٌ فارغٌ يخضرّ كاذباً: يجب أن يشمل الملفّين اللذين يبنيان `<use>` فعلاً."""
    names = {p.relative_to(ROOT).as_posix() for p in _project_scripts()}
    assert {"static/js/base.js", "static/js/app.js"} <= names


@pytest.mark.parametrize(
    "snippet,is_broken",
    [
        ("'<svg><use href=\"#icon-alert-triangle\"/></svg>'", True),  # ما كان في base.js
        (
            "'<svg><use xlink:href=\"#i-status_warning\"/></svg>'",
            True,
        ),  # الورقةُ خارجيّة: المحلّيّ لا يصل
        ("node.setAttribute('href', '#icon-close')", True),
        ("'<use href=\"' + sprite + '#i-no_such_meaning\"></use>'", True),
        ("'<use href=\"' + sprite + '#i-status_warning\"></use>'", False),  # الصواب
        ("'<use href=\"' + sprite + '#i-' + key + '\"></use>'", False),  # مبنيٌّ وقتَ التشغيل
        ("// كان يكتب #icon-alert-triangle", False),  # التعليقُ لا يُحسب
    ],
)
def test_the_script_guard_catches_what_it_is_meant_to(snippet, is_broken):
    assert bool(js_icon_problems(snippet, _sprite_symbols())) is is_broken, snippet
