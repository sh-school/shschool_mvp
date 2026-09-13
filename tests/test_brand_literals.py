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
