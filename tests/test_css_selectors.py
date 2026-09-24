"""[CSS] لا محدِّدَ ناقصٌ — مركِّبٌ بلا مُحدِّدٍ على أحد جانبيه يُسقط القاعدةَ كلَّها بصمت.

كانت قاعدةُ انتقال الصفحات (`20-components.css`) بمحدِّدٍ ينتهي بـ`>` منذ #423 — سقط `*` من
`#main-content > .exec-dash > *` — فأسقطها المتصفّحُ كلَّها: لا تلاشيَ للصفحات ولا رسالةَ خطأ،
و`page-nav.js` يضيف `.is-leaving` وينتظر مدّةَ انتقالٍ لا أثرَ له. وسببُ الصمت أنّ CSS يُسقط
**القاعدةَ كلَّها** لا المحدِّدَ المعطوبَ وحدَه، فحتى `:not(.exec-dash)` الصحيحةُ في القائمة نفسها ضاعت.

الحارسُ يقرأ CSS المنصّة عبر `tests.css_source.read_css()` (فلا يتعطّل إن أُعيد تقسيمُ الملفّات)،
ويقرأ معها أوراقَ `static/css/*.css` الأخرى الخاصّةَ بالمنصّة (الإدارةُ ودليلُ الهويّة) — ويستثني
ما هو مولَّدٌ (`*.min.css`، أي Tailwind). والمحلِّلُ في `tests/css_selectors.py`.
"""

from __future__ import annotations

import pytest

from tests.css_selectors import check_list, scan
from tests.css_source import CSS_ROOT, read_css

#: حدٌّ أدنى لما يجب أن يراه الحارسُ — قيسَ 2594 قائمةَ محدِّدات في الحزمة يومَ كتابته. إن سقط العددُ
#: تحته فقد عطب القارئُ (`iter_rules`) فصار الحارسُ يمرّ بلا أن يفحص شيئاً؛ والفحصُ الذي لا يستطيع أن يفشل ليس فحصاً.
MIN_SELECTOR_LISTS = 1500


def _first_party_sheets():
    """أوراقُ `static/css/*.css` غيرُ المولَّدة وغيرُ حزمة `custom/` (تقرؤها `read_css`)."""
    return sorted(p for p in CSS_ROOT.parent.glob("*.css") if not p.name.endswith(".min.css"))


def _report(bad) -> str:
    lines = [
        f"  [{f.kind}] {f.selector[:90]}" + (f"   داخل: {where}" if where else "")
        for f, where in bad[:25]
    ]
    more = f"\n  … و{len(bad) - 25} غيرُها" if len(bad) > 25 else ""
    return "\n".join(lines) + more


HINT = (
    "المتصفّحُ يُسقط القاعدةَ كلَّها بما فيها المحدِّداتُ الصحيحةُ في قائمتها — والغالبُ أنّ `*` سقط "
    "من `> *`، أو بقيت فاصلةٌ في آخر القائمة."
)


def test_the_platform_stylesheet_has_no_dangling_selector():
    checked, bad = scan(read_css())
    assert checked >= MIN_SELECTOR_LISTS, (
        f"الحارسُ لم يفحص إلّا {checked} قائمةَ محدِّدات (الأدنى {MIN_SELECTOR_LISTS}) — "
        "القارئُ معطوبٌ فالحارسُ يمرّ صامتاً"
    )
    assert not bad, f"{len(bad)} محدِّداً ناقصاً في حزمة أنماط المنصّة. {HINT}\n{_report(bad)}"


@pytest.mark.parametrize("sheet", _first_party_sheets(), ids=lambda p: p.name)
def test_other_first_party_sheets_have_no_dangling_selector(sheet):
    _checked, bad = scan(sheet.read_text(encoding="utf-8"))
    assert not bad, f"{len(bad)} محدِّداً ناقصاً في {sheet.name}. {HINT}\n{_report(bad)}"


def test_there_is_a_first_party_sheet_besides_the_bundle():
    """لو نُقلت ورقةٌ أو أُعيدت تسميتُها فصار الفحصُ الثاني فارغاً (لا وسيطاتِ parametrize) لسقط هنا لا صامتاً."""
    assert _first_party_sheets(), "لا ورقةَ في static/css/*.css غيرَ المولَّدة — تحقّق من المسار"


class TestTheAnalyser:
    """المحلِّلُ يحرس ما يقول: ما يُعدّ عطلاً، وما لا يُمسّ."""

    def kinds(self, selector_list: str) -> list[str]:
        return [f.kind for f in check_list(selector_list)]

    def test_the_exact_pair_that_shipped_broken_in_423(self):
        broken = "#main-content > :not(.exec-dash), #main-content > .exec-dash >"
        found = check_list(broken)
        assert [f.kind for f in found] == ["trailing"]
        assert found[0].selector == "#main-content > .exec-dash >"  # الثاني وحدَه — الأوّلُ سليم

    def test_the_fixed_pair_is_clean(self):
        assert self.kinds("#main-content > :not(.exec-dash), #main-content > .exec-dash > *") == []

    @pytest.mark.parametrize("combinator", [">", "+", "~"])
    def test_any_combinator_at_the_end_is_dangling(self, combinator):
        assert self.kinds(f".a {combinator}") == ["trailing"]
        assert self.kinds(f".a{combinator}") == ["trailing"]

    def test_a_combinator_at_the_start_is_dangling_outside_has(self):
        assert self.kinds("> .a") == ["leading"]
        assert self.kinds("+ .a, .b") == ["leading"]

    def test_two_adjacent_combinators_are_dangling(self):
        assert self.kinds(".a > > .b") == ["double"]
        assert self.kinds(".a > + .b") == ["double"]

    def test_an_empty_list_item_is_dangling(self):
        assert self.kinds(".a, , .b") == ["empty"]
        assert self.kinds(".a,") == ["empty"]

    def test_valid_selectors_are_not_touched(self):
        for ok in (
            ".a",
            ".a .b",
            ".a > .b",
            ".a + .b ~ .c",
            ".a>.b",
            "*",
            ".a > *",
            "html.dark .a > .b, .c",
            "a:hover > span::before",
            ".a:not(.b) > .c",
            "from",
            "0%, 100%",
        ):
            assert self.kinds(ok) == [], ok

    def test_combinator_characters_that_are_not_combinators_are_not_flagged(self):
        for ok in (
            '[data-x~="a"]',
            "[lang|=ar][title~=x]",
            '[data-x=">"]',
            "[data-x='+']",
            ".row:nth-child(2n+1)",
            ".row:nth-of-type(n + 3)",
            r".md\:flex",  # هروبُ Tailwind
            r".a\>b",  # `>` مُهرَّبةٌ اسمُ صنف
            r".a\~b > .c",
        ):
            assert self.kinds(ok) == [], ok

    def test_selector_list_functions_are_checked_recursively(self):
        assert self.kinds(".a:not(.b >)") == ["trailing"]
        assert self.kinds(".a:is(.b, .c >)") == ["trailing"]
        assert self.kinds(".a:where(.b > > .c)") == ["double"]
        assert self.kinds(".a:not(> .b)") == ["leading"]
        assert self.kinds(".a:is(.b > .c, .d) > .e") == []

    def test_has_takes_a_relative_selector(self):
        assert self.kinds(".a:has(> .b)") == []
        assert self.kinds(".a:has(+ .b, ~ .c)") == []
        assert self.kinds(".a:has(> .b >)") == ["trailing"]
        assert self.kinds(".a:has(>)") == ["trailing"]

    def test_an_empty_where_or_is_is_valid(self):
        assert self.kinds(".a:where()") == []
        assert self.kinds(".a:is()") == []

    def test_pseudo_class_names_do_not_swallow_their_neighbours(self):
        """`a:hover:not(.b >)` — الاسمُ يُقرأ `:not` لا `:hover:not`."""
        assert self.kinds("a:hover:not(.b >)") == ["trailing"]
        assert self.kinds("a:hover:not(.b > .c)") == []

    def test_scan_reports_the_containing_blocks(self):
        css = "@layer components { @media (max-width: 640px) { .a > .b > { color: red } } }"
        checked, bad = scan(css)
        assert checked == 1
        assert [f.kind for f, _ in bad] == ["trailing"]
        assert "@layer components" in bad[0][1] and "@media" in bad[0][1]

    def test_scan_ignores_at_rule_statements_and_keyframe_steps(self):
        css = "@layer a, b;\n@keyframes x { from { opacity: 0 } 50%, to { opacity: 1 } }\n.ok > .b { top: 0 }"
        checked, bad = scan(css)
        assert bad == []
        assert checked == 3  # from، 50%,to، .ok > .b
