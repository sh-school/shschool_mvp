"""
tests/test_focus_and_names.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
من يتنقّل بلوحة المفاتيح يرى أين هو، ومن يسمع الصفحةَ يعرف ما يضغط.

قِيس التركيزُ يومَ 2026-09-13 في متصفّحٍ يملك التركيز فعلاً (Edge بلا واجهة؛ لوحُ
المعاينة لا يملكه فلا تنطبق `:focus` فيه أصلاً) على أربعة عشر عنصراً في الوضعين:

  - حلقةُ المنصّة كلّها `outline: 2px solid var(--maroon)` — 9.35 نهاراً و**1.56
    ليلاً**: العنّابيُّ الثابتُ على السطح الداكن. حتى الزرُّ الرئيسيُّ والرابط.
  - ثمانيةُ مواضعَ تُلغي الحلقةَ (`outline: none`) ببديلٍ أخفت منها: 1.51 نهاراً
    وحتى 1.11 ليلاً.
  - وحقلٌ بلا صنفٍ يُعلَّم تركيزُه بحدٍّ عنّابيٍّ ثابت — 1.23 ليلاً.

فصار للتركيز رمزٌ واحد `--focus-color` (= `--maroon-fg`، ينقلب)، وأدنى علامةِ تركيزٍ
بعدها 4.14. والحدُّ المعتمدُ هنا 3:1 — حدُّ WCAG لما ليس نصّاً.
"""

import pathlib
import re

from tests.css_contrast import iter_rules, ratio, resolve, token_table
from tests.css_source import read_css

ROOTS = [pathlib.Path("templates")] + sorted(pathlib.Path(".").glob("*/templates"))

NON_TEXT_AA = 3.0

#: طبقاتٌ تعلو `components` حيث تُعرَّف حلقةُ المنصّة — `outline: none` فيها يغلبها.
LAYERS_ABOVE_THE_RING = ("modules", "utilities", "themes")


def _css():
    return read_css()


def _layer(ctx):
    return next((c.split()[-1] for c in ctx if c.startswith("@layer")), "")


def test_the_focus_colour_is_visible_on_every_surface_in_both_themes():
    light, dark = token_table(_css())
    offenders = []
    for theme, tokens in (("النهار", light), ("الليل", dark)):
        ring = resolve("var(--focus-color)", tokens)
        assert ring is not None, f"--focus-color لا يُحلّ في {theme}"
        for surface in ("--surface", "--surface-alt", "--page-bg"):
            got = ratio(ring, resolve(f"var({surface})", tokens))
            if got < NON_TEXT_AA:
                offenders.append(f"  {theme}: {got:.2f} على {surface}")
    assert not offenders, "حلقةُ التركيز لا تُرى:\n" + "\n".join(offenders)


def test_focus_outlines_use_the_focus_token():
    """حلقةٌ بلونٍ مكتوب — أو `--maroon` الثابت — تختفي في أحد الوضعين."""
    offenders = []
    for sel, decls, _ctx in iter_rules(_css()):
        if ":focus" not in sel:
            continue
        outline = decls.get("outline") or decls.get("outline-color") or ""
        if not outline or re.search(r"\b(none|0)\b|transparent", outline):
            continue
        if "var(--focus-color)" not in outline and "currentColor" not in outline:
            offenders.append(f"  {' '.join(sel.split())[:70]}  →  {outline}")
    assert not offenders, "حلقةُ تركيزٍ بغير `var(--focus-color)`:\n" + "\n".join(offenders)


def test_nothing_switches_the_focus_ring_off():
    """`outline: none` في قاعدة تركيز، أو في طبقةٍ تعلو الحلقة، يمحوها بلا بديل يُرى.

    والحلقةُ الشفّافة (`outline: 2px solid transparent`) مسموحة: تظهر في وضع التباين
    العالي للنظام، ويُعلَّم التركيزُ بغيرها.
    """
    offenders = []
    for sel, decls, ctx in iter_rules(_css()):
        outline = decls.get("outline", "")
        if not re.fullmatch(r"\s*(none|0)\s*(!important)?\s*", outline):
            continue
        flat = " ".join(sel.split())
        if ":focus" in flat or _layer(ctx) in LAYERS_ABOVE_THE_RING:
            offenders.append(f"  [{_layer(ctx) or '—'}] {flat[:80]}")
    assert not offenders, "حلقةُ التركيز مُطفأة:\n" + "\n".join(offenders)


# ══════════════════════════════════════════════════════════════════
# أسماءُ ما يُضغط
# ══════════════════════════════════════════════════════════════════

ELEMENT = re.compile(r"<(button|a)\b([^>]*)>(.*?)</\1\s*>", re.S | re.I)
ICON = re.compile(
    r"\{%\s*include\s+[\"']components/icon\.html[\"'][^%]*%\}|<svg\b.*?</svg\s*>", re.S | re.I
)
NOISE = re.compile(
    r"\{#.*?#\}|\{%\s*(?:if|elif|else|endif|with|endwith)\b[^%]*%\}|<!--.*?-->|&nbsp;|\s", re.S
)
NAMED = re.compile(r"\baria-label(?:ledby)?\s*=|\btitle\s*=", re.I)


def test_icon_only_controls_have_a_name():
    """الأيقونةُ `aria-hidden` — فزرٌّ أو رابطٌ ليس فيه غيرُها يُقرأ «رابط» فحسب."""
    offenders = []
    for root in ROOTS:
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for m in ELEMENT.finditer(text):
                tag, attrs, inner = m.groups()
                if not ICON.search(inner) or NAMED.search(attrs):
                    continue
                rest = re.sub(r"<[^>]+>", "", NOISE.sub("", ICON.sub("", inner)))
                if not rest:
                    line = text[: m.start()].count("\n") + 1
                    offenders.append(f"  {path.as_posix()}:{line} <{tag}>")
    assert not offenders, "عنصرٌ بأيقونةٍ وحدها بلا اسم — أضف aria-label:\n" + "\n".join(offenders)
