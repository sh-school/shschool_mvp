"""[DESIGN] «بلا تمرير» مشروطٌ بسعة النافذة (LAY-03، قرارُ المالك 2026-09-24).

صفحةُ `page-noscroll` تُمرِّر قوائمَها داخل بطاقاتها؛ فإن ضيّق ارتفاعُ النافذة منطقةً دون 15rem
نُزع الصنفُ فمُرِّرت الصفحةُ كلُّها. والقرارُ **قبل الرسم الأوّل** وإلّا قفزت الصفحة:
قيس CLS نحو 1.0 حين كان في base.js المؤجَّل، وعاد إلى مستواه (≤ 0.015) بعد نقله. فالحارسُ
يحفظ الترتيبَ الذي يجعله قبل الرسم، لا الشكلَ وحده.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = (ROOT / "templates/base/base.html").read_text(encoding="utf-8")
BASE_JS = (ROOT / "static/js/base.js").read_text(encoding="utf-8")


def test_the_decision_runs_inline_right_after_the_content():
    main_end = BASE.index("</main>")
    script = BASE.index("window.fitNoscroll = function", main_end)
    call = BASE.index("window.fitNoscroll();", script)
    # لا شيءَ بين المحتوى والقرار إلّا تعليقٌ ووسمُ السكربت.
    between = re.sub(r"\{#.*?#\}", "", BASE[main_end + len("</main>") : script], flags=re.S)
    assert between.strip().startswith('<script nonce="{{ request.csp_nonce }}">')
    assert call > script


def test_first_paint_waits_for_the_decision():
    """`blocking="render"` على علامةٍ بعد القرار — فلا يُرسم نصفُ صفحةٍ طويلةٍ ثمّ يقفز."""
    head = BASE[: BASE.index("</head>")]
    link = re.search(r'<link rel="expect" href="#([\w-]+)" blocking="render">', head)
    assert link, "رأسُ الصفحة بلا انتظارٍ لقرار «بلا تمرير»"
    marker = BASE.index(f'id="{link.group(1)}"')
    assert marker > BASE.index("window.fitNoscroll();")


def test_the_floor_is_fifteen_rem_and_counts_only_squeezed_regions():
    body = BASE[BASE.index("window.fitNoscroll = function") : BASE.index("window.fitNoscroll();")]
    assert "15 * parseFloat(getComputedStyle(document.documentElement).fontSize)" in body
    # المنطقةُ القصيرةُ بتصميمها لا تُحسب: يجب أن تطول حين يُنزع الصنف.
    assert "el.clientHeight > h[i] + 1 && h[i] < floor" in body


def test_base_js_redecides_on_resize_and_swaps_but_not_on_load():
    """إعادةُ القرار عند `load` كانت تُحدث قفزةً (CLS 0.94 في قائمة الطلاب) بعد الرسم."""
    block = BASE_JS[BASE_JS.index("«بلا تمرير» مشروطٌ بسعة النافذة") :]
    assert "addEventListener('resize', later)" in block
    assert "addEventListener('htmx:afterSwap', later)" in block
    assert "addEventListener('load'" not in block
