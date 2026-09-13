"""
tests/test_brand_literals.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
العنّابيُّ في صفحةٍ حيّةٍ يُقرأ من رمزه — لا يُكتب رقماً في `style=`.

الصفحةُ الحيّةُ تحمّل `custom.css`، فالرمزُ متاحٌ لها، وهو ينقلب ليلاً إلى
درجةٍ تُقرأ على السطح الداكن. والرقمُ المكتوبُ لا ينقلب: كان `custom.css`
يتداركه بمطابقة السلسلة (`[style*="color:#8A1538"]`) وتلك رُقعةٌ لا مبدأ.

وقوالبُ الورق — PDF والطباعة — تبقى على الرقم عمداً: مولّدُ الـPDF لا يحلّ
`var()`، فيسقط اللونُ كلُّه. فالحارسُ يقصر نفسَه على ما يرث قالبَ المنصّة.
"""

import pathlib
import re

ROOTS = [pathlib.Path("templates")] + sorted(pathlib.Path(".").glob("*/templates"))
EXTENDS_BASE = re.compile(r"""\{%\s*extends\s+["'](base\.html|base/base\.html)["']""")
INLINE_MAROON = re.compile(r"""style\s*=\s*["'][^"']*#8a1538""", re.I)


def _live_templates():
    for root in ROOTS:
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if EXTENDS_BASE.search(text):
                yield path, text


def test_live_pages_read_the_maroon_from_its_token():
    offenders = [
        f"  {path.as_posix()}:{text[: m.start()].count(chr(10)) + 1}"
        for path, text in _live_templates()
        for m in INLINE_MAROON.finditer(text)
    ]
    assert not offenders, (
        "العنّابيُّ مكتوبٌ رقماً في `style=` بصفحةٍ حيّة — استعمل `text-maroon` "
        "أو `var(--maroon-fg)`:\n" + "\n".join(offenders)
    )


def test_the_scan_reaches_the_live_pages():
    """مسحٌ لا يجد قوالبَ ينجح كاذباً."""
    assert sum(1 for _ in _live_templates()) >= 150


# ══════════════════════════════════════════════════════════════════
# الرسوم — Chart.js يرسم على canvas، وcanvas لا يحلّ `var()`
# ══════════════════════════════════════════════════════════════════
#
# كان خطُّ اتّجاه المخالفات في لوحة السلوك `borderColor:'var(--chart-1,#8A1538)'`
# — فرفضه canvas وبقي على لونه الافتراضيّ: رُسم أسودَ (قِيس بالبكسل يومَ
# 2026-09-13). والرقمُ المكتوبُ يُرسم، لكنّه لا ينقلب ليلاً ويتباعد عن
# لوحة الرموز (`--chart-4` عُمِّق إلى #A8801F والقوالبُ بقيت على #D4A843).
# فالرسومُ تقرأ الرموزَ بمساعدات رأس `base.html`: `chartColor` و`chartPalette`
# و`chartAlpha`.

SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
CHART_KEYS = r"(?:border|background|pointBackground|pointBorder|hoverBackground|hoverBorder)Color"
LITERAL_CHART_COLOUR = re.compile(CHART_KEYS + r"""\s*:\s*['"](?:#|rgba?\(|hsla?\(|var\()""")
LITERAL_PALETTE = re.compile(r"""\[\s*['"]#[0-9a-fA-F]{3,8}['"]\s*,""")
HELPER_CALL = re.compile(r"""chart(?:Color|Alpha)\(\s*['"]([a-z0-9-]+)['"]""")


def _chart_scripts():
    for path, text in _live_templates():
        for m in SCRIPT.finditer(text):
            if "new Chart(" in text:
                yield path, text, m


def test_charts_read_their_colours_from_the_tokens():
    offenders = []
    for path, text, m in _chart_scripts():
        body = m.group(1)
        for hit in list(LITERAL_CHART_COLOUR.finditer(body)) + list(LITERAL_PALETTE.finditer(body)):
            line = text[: m.start(1) + hit.start()].count("\n") + 1
            offenders.append(f"  {path.as_posix()}:{line}  {hit.group(0)[:48]}")
    assert not offenders, (
        "لونُ رسمٍ مكتوبٌ رقماً أو `var()` — canvas لا يحلّ `var()`، والرقمُ لا ينقلب. "
        "استعمل chartColor/chartPalette/chartAlpha:\n" + "\n".join(offenders)
    )


def test_every_chart_colour_names_a_real_token():
    """اسمٌ لا رمزَ له يُرجع سلسلةً فارغة — فيُرسم الشكلُ أسودَ بلا خطأ."""
    from tests.css_contrast import token_table

    light, _dark = token_table(pathlib.Path("static/css/custom.css").read_text(encoding="utf-8"))
    missing, used = [], 0
    for path, _text, m in _chart_scripts():
        for name in HELPER_CALL.findall(m.group(1)):
            used += 1
            if f"--{name}" not in light:
                missing.append(f"  {path.as_posix()}: --{name}")
    assert used >= 30, f"لم يُرَ إلّا {used} استدعاءً — المسحُ لم يبلغ الرسوم"
    assert not missing, "رموزُ رسمٍ غيرُ معرَّفة:\n" + "\n".join(sorted(set(missing)))
