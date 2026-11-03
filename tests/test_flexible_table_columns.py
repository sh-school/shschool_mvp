"""أعمدةُ الجداول مرنةٌ تتكيّف مع محتواها (قرارُ المالك 2026-10-13: «الأعمدة مرنة وتحتوي النصوص ... مرنة مرنة»).

يمنع عرضاً ثابتاً (`width: 40px`، `width="60"`) على `th`/`td`/`col` في CSS المنصّة وكتل `<style>`
والسمات في القوالب، فالعرضُ الثابتُ يقتطع الاسمَ أو يكسره أو يترك فراغاً. المسموح: `min-width`/`max-width`
ونسبٌ مئويّة و`auto`. الجردُ وقتَ كتابة الحارس صفر، فلا خطَّ أساسَ: أيُّ موضعٍ جديدٍ يُسقطه.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
_BLOCK = re.compile(r"([^{}@][^{}]*)\{([^{}]*)\}")
_CELL = re.compile(r"(?<![\w-])(th|td|col)(?![\w-])|\.col-[\w-]+")
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
        f"(.claude/rules/tables.md «أعمدةُ الجداول مرنة»): {_all_hits()}"
    )


def test_the_detector_sees_fixed_widths_and_accepts_flexible_ones():
    assert _css_hits("th.num { width: 40px; }") == 1
    assert _css_hits("td, .x { width: 3rem }") == 1
    assert _css_hits("th { min-width: 40px; max-width: 9rem; width: auto; }") == 0
    assert _css_hits(".card { width: 40px; }") == 0
    assert _css_hits(".grid .col-name { width: 230px; }") == 1
    assert _css_hits(".grid .col-name { width: 22%; }") == 0
    assert _template_hits('<th width="60">') == 1
    assert _template_hits('<col style="width: 20mm">') == 1
    assert _template_hits('<th style="min-width: 60px">') == 0


# ── الاقتطاع بنقطتين في خلايا الجداول (W-20261013-025) ─────────────────────
# `text-overflow: ellipsis` على خليّة جدولٍ يُخفي بيانةً بلا وسيلةٍ لرؤيتها؛ الالتفافُ هو الأصل. القديمُ مسجَّلٌ
# بعدده لكلّ ملفّ ولا يزيد ولا يُضاف، ويُنقَص عند الترحيل. الاستثناءُ المقبول: تسميةٌ في شريط/بطاقة لا خليّةُ جدول.
_ELLIPSIS = re.compile(r"text-overflow\s*:\s*ellipsis")
_TABLE_SELECTOR = re.compile(
    r"(?<![\w-])(th|td)(?![\w-])|-table(?![\w-])|\.table-wrap|\.grid(?![\w-])"
)
# مصفوفةُ الجدول الدراسيّ (خليّةُ الاسم بتخطيطٍ ثابتٍ بنسبٍ) استثناءٌ مقصود.
ELLIPSIS_ON_CELLS_BASELINE: dict[str, int] = {"static/css/custom/32-modules-3.css": 1}


def _ellipsis_cell_hits(css: str) -> int:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return sum(
        1
        for m in _BLOCK.finditer(css)
        if _ELLIPSIS.search(m.group(2)) and _TABLE_SELECTOR.search(m.group(1))
    )


def _ellipsis_hits() -> dict[str, int]:
    out = {}
    for p in (ROOT / "static" / "css" / "custom").glob("*.css"):
        n = _ellipsis_cell_hits(p.read_text(encoding="utf-8"))
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    for p in (ROOT / "templates").rglob("*.html"):
        text = p.read_text(encoding="utf-8")
        n = sum(
            _ellipsis_cell_hits(st)
            for st in re.findall(r"<style[^>]*>(.*?)</style>", text, flags=re.S)
        )
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    return out


def test_ellipsis_on_table_cells_never_grows_past_its_baseline():
    now = _ellipsis_hits()
    worse = {
        f: (ELLIPSIS_ON_CELLS_BASELINE.get(f, 0), n)
        for f, n in now.items()
        if n > ELLIPSIS_ON_CELLS_BASELINE.get(f, 0)
    }
    assert not worse, (
        "اقتطاعٌ بنقطتين على خليّة جدول يُخفي النصَّ؛ دع النصَّ يلتفّ (`overflow-wrap`) "
        f"(.claude/rules/tables.md «أعمدةُ الجداول مرنة»): {worse}"
    )
    stale = {f: n for f, n in ELLIPSIS_ON_CELLS_BASELINE.items() if now.get(f, 0) < n}
    assert (
        not stale
    ), f"نقص الاقتطاعُ ولم يُنقَص الخطُّ الأساسيّ — أحسنت؛ حدِّث ELLIPSIS_ON_CELLS_BASELINE: {stale}"


def test_the_ellipsis_detector_sees_cells_not_labels():
    assert _ellipsis_cell_hits(".ev-table td { text-overflow: ellipsis; }") == 1
    assert _ellipsis_cell_hits("th.x, .y { overflow: hidden; text-overflow: ellipsis }") == 1
    assert _ellipsis_cell_hits(".nav-logo-text { text-overflow: ellipsis; }") == 0
    assert _ellipsis_cell_hits("/* td { text-overflow: ellipsis; } */") == 0
