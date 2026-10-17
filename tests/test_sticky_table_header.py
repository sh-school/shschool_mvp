"""رأسُ الجدول الثابت عند التمرير الرأسي على كلّ جدول (قرارُ المالك 2026-10-13: «نعم، أمري — قاعدة وحارس للجديد»).

`.table-wrap` وحدَه يقصّ التمرير الرأسي (`overflow-y: hidden`) فيضيع الرأسُ اللاصق في جدولٍ طويل؛ و`table-wrap-scroll` هو
الذي يُمرِّر رأسياً (`max-height: 70vh`) فيبقى `thead th` لاصقاً. فكلُّ جدولٍ صفوفُه من حلقة `{% for %}` يُلفّ بـ`table-wrap-scroll`.

الحارسُ يمنع الجديدَ فقط: القوالبُ التي سبقته مسجَّلةٌ بعدد المواضع في `sticky_table_header_baseline.json` (دون ترحيل)،
لا يزيد عددٌ ولا يُضاف قالب، وتُنقَص الأعدادُ حين يُرحَّل موضع.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = json.loads(
    (ROOT / "tests" / "sticky_table_header_baseline.json").read_text(encoding="utf-8")
)["files"]

_WRAP = re.compile(r"""class\s*=\s*["'][^"']*(?<![\w-])table-wrap(?![\w-])[^"']*["']""")


def _violations(text: str) -> int:
    """أغلفةُ `table-wrap` بلا `table-wrap-scroll` يليها جدولٌ صفوفُه من حلقة."""
    count = 0
    for m in _WRAP.finditer(text):
        if "table-wrap-scroll" in m.group(0):
            continue
        tail = text[m.end() :]
        end = tail.find("</table>")
        if end != -1 and "{% for" in tail[:end] and "<table" in tail[:end]:
            count += 1
    return count


def _counts() -> dict[str, int]:
    out = {}
    for p in sorted((ROOT / "templates").rglob("*.html")):
        n = _violations(p.read_text(encoding="utf-8"))
        if n:
            out[p.relative_to(ROOT).as_posix()] = n
    return out


def test_new_long_tables_keep_a_sticky_header():
    over = {f: (n, BASELINE.get(f, 0)) for f, n in _counts().items() if n > BASELINE.get(f, 0)}
    assert not over, (
        "جدولٌ صفوفُه من حلقةٍ داخل `table-wrap` بلا `table-wrap-scroll` فيضيع رأسُه عند التمرير الرأسي؛ "
        f"اجعل غلافَه `table-wrap table-wrap-scroll`: {over}"
    )


def test_baseline_is_not_wider_than_reality():
    counts = _counts()
    stale = {f: n for f, n in BASELINE.items() if counts.get(f, 0) < n}
    assert not stale, f"رُحِّلت مواضع — أنقِص الأعداد في sticky_table_header_baseline.json: {stale}"


def test_the_detector_sees_the_bad_shape_and_accepts_the_good_one():
    bad = '<div class="table-wrap"><table><tbody>{% for r in rows %}<tr></tr>{% endfor %}</tbody></table></div>'
    good = bad.replace("table-wrap", "table-wrap table-wrap-scroll", 1)
    static = '<div class="table-wrap"><table><tbody><tr></tr></tbody></table></div>'
    assert _violations(bad) == 1 and _violations(good) == 0 and _violations(static) == 0
