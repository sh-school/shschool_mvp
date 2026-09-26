"""[MOBILE] سلّمُ الخطوط (H-03) — راجع `tests/font_scale.py` للسبب والطريقة."""

from tests import font_scale as fs
from tests.css_source import read_css


def _found():
    return [(sel, decl, fs.allowed(sel)) for sel, decl, _, _ in fs.small_declarations(read_css())]


def test_no_readable_text_is_below_the_scale():
    bad = [f"{sel} → {decl}" for sel, decl, why in _found() if why is None]
    assert not bad, "خطٌّ دون 12px — اكتبه var(--text-xs):\n  " + "\n  ".join(bad)


def test_only_decorative_marks_stay_below_the_scale():
    """كانت 23 تصريحاً في شبكاتٍ كثيفةٍ استثناءً مؤقّتاً؛ رُفعت (H-03) — ولا تعود."""
    left = {why for *_, why in _found()}
    assert left <= {"decorative"}, left


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

    def test_decorative_is_named_and_the_dense_grids_are_not_exempt(self):
        assert fs.allowed(".nb .chv") == "decorative"
        assert fs.allowed(".exg-cell") is None
        assert fs.allowed(".hint") is None
