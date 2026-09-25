"""[MOBILE] سلّمُ الخطوط (H-03) — راجع `tests/font_scale.py` للسبب والطريقة."""

from tests import font_scale as fs
from tests.css_source import read_css

#: عددُ تصريحات الشبكات الكثيفة المنتظِرة مراجعةَ المالك (2026-09-23) — ينقص ولا يزيد.
DENSE_PENDING_CEILING = 23


def _found():
    return [(sel, decl, fs.allowed(sel)) for sel, decl, _, _ in fs.small_declarations(read_css())]


def test_no_readable_text_is_below_the_scale():
    bad = [f"{sel} → {decl}" for sel, decl, why in _found() if why is None]
    assert not bad, "خطٌّ دون 12px — اكتبه var(--text-xs):\n  " + "\n  ".join(bad)


def test_the_dense_grid_exception_only_shrinks():
    pending = sum(1 for *_, why in _found() if why == "dense_pending")
    assert pending <= DENSE_PENDING_CEILING, (
        f"{pending} تصريحاً في استثناء الشبكات الكثيفة (السقف {DENSE_PENDING_CEILING}) — "
        "لا يُضاف إليه؛ ارفع الخطَّ أو اعرضه على المالك"
    )
    if pending < DENSE_PENDING_CEILING:
        raise AssertionError(
            f"نقص الاستثناءُ إلى {pending} — أحسنت؛ ثبّته بخفض DENSE_PENDING_CEILING في هذا الملفّ"
        )


class TestTheParserItself:
    def test_a_small_declaration_is_found_with_its_selector(self):
        found = list(fs.small_declarations(".a .b { color: red; font-size: 0.625rem; }"))
        assert [(sel, decl) for sel, decl, *_ in found] == [(".a .b", "font-size: 0.625rem")]

    def test_twelve_pixels_and_tokens_pass(self):
        css = ".a { font-size: 0.75rem } .b { font-size: var(--text-xs) } .c { font-size: 12px }"
        assert not list(fs.small_declarations(css))

    def test_px_is_converted(self):
        assert list(fs.small_declarations(".a { font-size: 11px }"))

    def test_comments_do_not_hide_or_invent_rules(self):
        css = "/* .x { font-size: 0.5rem } */ .a { font-size: 1rem }"
        assert not list(fs.small_declarations(css))

    def test_nested_rules_keep_their_own_selector(self):
        css = "@media (max-width: 640px) { .nav-item { font-size: 0.65rem } }"
        assert [sel for sel, *_ in fs.small_declarations(css)] == [".nav-item"]

    def test_decorative_and_dense_are_named(self):
        assert fs.allowed(".nb .chv") == "decorative"
        assert fs.allowed(".exg-cell") == "dense_pending"
        assert fs.allowed(".hint") is None
