"""أعمدةُ الجداول مرنةٌ تتكيّف مع محتواها (قرارُ المالك 2026-10-13: «الأعمدة مرنة وتحتوي النصوص ... مرنة مرنة»).

يمنع عرضاً ثابتاً (`width: 40px`، `width="60"`) على `th`/`td`/`col` في CSS المنصّة وكتل `<style>`
والسمات في القوالب، فالعرضُ الثابتُ يقتطع الاسمَ أو يكسره أو يترك فراغاً. المسموح: `min-width`/`max-width`
ونسبٌ مئويّة و`auto`. الجردُ وقتَ كتابة الحارس صفر، فلا خطَّ أساسَ: أيُّ موضعٍ جديدٍ يُسقطه.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
_BLOCK = re.compile(r"([^{}@][^{}]*)\{([^{}]*)\}")
_CELL = re.compile(r"(?<![\w-])(th|td|col)(?![\w-])")
_FIXED = re.compile(r"(?<![\w-])width\s*:\s*[0-9.]+(px|rem|em|ch|mm|cm|pt)\b")
_ATTR = re.compile(
    r"""<(th|td|col)\b[^>]*?(?<![\w-])(width\s*=\s*["']?\d"""
    r"""|style\s*=\s*["'][^"']*(?<![\w-])width\s*:\s*[0-9.]+(px|rem|em|ch|mm|cm|pt))""",
    re.I,
)


def _css_hits(css: str) -> int:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return sum(
        1
        for m in _BLOCK.finditer(css)
        if any(_CELL.search(s) for s in m.group(1).split(",")) and _FIXED.search(m.group(2))
    )


def _template_hits(html: str) -> int:
    n = len(_ATTR.findall(html))
    for st in re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S):
        n += _css_hits(st)
    return n


def _all_hits() -> dict[str, int]:
    out = {}
    for p in (ROOT / "static" / "css" / "custom").glob("*.css"):
        n = _css_hits(p.read_text(encoding="utf-8"))
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    for p in (ROOT / "templates").rglob("*.html"):
        n = _template_hits(p.read_text(encoding="utf-8"))
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    return out


def test_no_fixed_width_on_table_columns():
    assert not _all_hits(), (
        "عرضٌ ثابتٌ على عمود جدولٍ يقتطع النصَّ أو يكسره؛ استعمل `min-width`/`max-width` أو نسبةً أو `auto` "
        f"(.claude/rules/design-system.md «أعمدةُ الجداول مرنة»): {_all_hits()}"
    )


def test_the_detector_sees_fixed_widths_and_accepts_flexible_ones():
    assert _css_hits("th.num { width: 40px; }") == 1
    assert _css_hits("td, .x { width: 3rem }") == 1
    assert _css_hits("th { min-width: 40px; max-width: 9rem; width: auto; }") == 0
    assert _css_hits(".card { width: 40px; }") == 0
    assert _template_hits('<th width="60">') == 1
    assert _template_hits('<col style="width: 20mm">') == 1
    assert _template_hits('<th style="min-width: 60px">') == 0
