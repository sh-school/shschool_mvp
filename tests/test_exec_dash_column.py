"""غلافُ الصفحة `.exec-dash` له عمودٌ صريحٌ — لا `auto` الضمنيّ.

قياسُ ADR-0006 (2026-09-24) على 164 صفحةً بعرض 390px وجد أربعاً يفيض غلافُها:
`/notifications/` (701px في 366) و`parents/admin/links` (687) و`/wings/` (554) و`clinic/visits` (502).
والسببُ واحد: `.exec-dash` شبكةٌ بلا `grid-template-columns`، فعمودُها الضمنيّ `auto` يتّسع لأدنى
محتوى جدولٍ في أبنائه، فيمتدّ الغلافُ فوق عرض الصفحة، وتُقصّ بطاقاتُه من جانبٍ ويُمرَّر جانبيّاً.

هذا حارسٌ ساكنٌ على القاعدة التي أُصلحت (التخطيطُ نفسُه لا يُقاس إلّا في متصفّح): يمنع رجوعَ السبب لا
يكشف جديداً.
"""

import re

from tests.css_contrast import iter_rules
from tests.css_source import read_css


def _exec_dash_declarations():
    return [
        decls
        for sel, decls, ctx in iter_rules(read_css())
        if {" ".join(p.split()) for p in sel.split(",")} == {".exec-dash"}
        and not any(c.startswith("@media") for c in ctx)
        and decls.get("display") == "grid"
    ]


def test_the_wrapper_is_defined_once_as_a_grid():
    """تعريفٌ واحدٌ للغلاف (LAY-03) — ازدواجُه أعاد التباسَ الأعمدة."""
    assert len(_exec_dash_declarations()) == 1


def test_the_wrapper_column_can_shrink_below_its_content():
    """`minmax(0, 1fr)` وحدَه يسمح للعمود أن يضيق دون أدنى محتوى جدولٍ داخله؛ و`auto` أو `1fr` لا."""
    (decls,) = _exec_dash_declarations()
    columns = "".join(decls.get("grid-template-columns", "").split())
    assert re.fullmatch(r"minmax\(0(px)?,1fr\)", columns), (
        "`.exec-dash` بلا عمودٍ صريحٍ `minmax(0, 1fr)`: العمودُ الضمنيّ auto يتمدّد لأدنى محتوى جدولٍ "
        f"فيفيض الغلافُ على الهاتف (وُجد: {columns or 'لا شيء'!r})"
    )
