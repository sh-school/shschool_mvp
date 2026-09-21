"""[DESIGN] التباعدُ والتقوّسُ بالرموز — وقيمُ px الحرفيّة على السلّم ممنوعة (P3-4).

`var(--sp-2)` هي عينُ `8px` (معرَّفةٌ مرّةً في `:root`)، فالترحيلُ لا يغيّر شيئاً في الرسم؛
وقيمةٌ حرفيّةٌ تطابق درجةً في السلّم تعني أنّ كاتبها لم يعلم بالرمز، ثمّ يتباعد الاثنان
حين يُعدَّل السلّم. أمّا ما **خارج** السلّم (6 و10 و2 و14 و18…) فهو الأكثرُ استعمالاً فعلاً
(≈320 موضعاً — رُمِّزت بدرجاتٍ نصفيّة: 2·6·10·14·18) — وتحويلُه إلى أقرب درجةٍ تغييرٌ بصريٌّ لا ترحيل، فقرارُ تصميمٍ منفصل؛
وحتّى يُقرَّر تُثبَّت أعدادُه هنا كسقّاطة: لا تزيد، وإن نقصت فسجّل النقص.
"""

from tests import px_tokens as px
from tests.css_source import read_css

#: خارجَ السلّم يومَ الترحيل (2026-09-19). تُخفَّض ولا تُرفع.
OFF_SCALE_SPACING = 92
OFF_SCALE_RADIUS = 31


def test_no_spacing_or_radius_px_literal_matches_a_token():
    counts = px.count_literals(read_css())
    assert counts["spacing_on_scale"] == 0, (
        f"{counts['spacing_on_scale']} قيمةَ تباعدٍ حرفيّةً تطابق درجةً في السلّم — "
        "اكتب var(--sp-N) (4→sp-1، 8→sp-2، 12→sp-3، 16→sp-4، 20→sp-5، 24→sp-6، 32→sp-8…)"
    )
    assert counts["radius_on_scale"] == 0, (
        f"{counts['radius_on_scale']} قيمةَ تقوّسٍ حرفيّةً تطابق رمزاً — "
        "اكتب var(--radius-sm|md|lg|xl) (4·6·8·14·16)"
    )


def test_off_scale_literals_do_not_grow_and_a_drop_is_recorded():
    counts = px.count_literals(read_css())
    for key, ceiling in (
        ("spacing_off_scale", OFF_SCALE_SPACING),
        ("radius_off_scale", OFF_SCALE_RADIUS),
    ):
        assert counts[key] <= ceiling, (
            f"{key}: {counts[key]} > {ceiling} — قيمةُ px جديدةٌ خارج السلّم؛ استعمل رمزاً "
            "من السلّم، أو أضِف درجةً إليه بقرار"
        )
        assert counts[key] >= ceiling, (
            f"{key}: نقص إلى {counts[key]} — أحسنت؛ اخفض السقفَ في tests/test_px_tokens.py "
            "إلى الرقم الجديد كي لا يُستهلك الفرق لاحقاً"
        )


class TestTheMigrationItself:
    """المحلِّلُ يحرس ما يقول: ما يُرحَّل وما لا يُمسّ."""

    def test_an_on_scale_spacing_value_becomes_its_token(self):
        assert px.migrate(".a { margin: 8px 12px; }") == ".a { margin: var(--sp-2) var(--sp-3); }"

    def test_calc_keeps_its_shape(self):
        assert "calc(100% - var(--sp-2))" in px.migrate(
            ".a { width: 1px; padding: calc(100% - 8px); }"
        )

    def test_an_off_scale_value_is_left_alone(self):
        css = ".a { padding: 3px 5px; gap: 1px; }"
        assert px.migrate(css) == css

    def test_negative_and_decimal_values_are_left_alone(self):
        css = ".a { margin: -8px 0.5px 1.25px 8.5px; }"
        assert px.migrate(css) == css

    def test_radius_maps_to_its_own_tokens(self):
        out = px.migrate(".a { border-radius: 8px; border-top-left-radius: 14px; }")
        assert "var(--radius-md)" in out and "var(--radius-lg)" in out

    def test_font_size_and_size_properties_are_left_alone(self):
        css = ".a { font-size: 16px; width: 16px; height: 8px; top: 8px; }"
        assert px.migrate(css) == css

    def test_media_conditions_comments_strings_and_page_are_left_alone(self):
        css = (
            '/* margin: 8px */ @media (max-width: 640px) { .a { content: "padding: 8px"; } }\n'
            "@page { margin: 8px; }\n"
        )
        assert px.migrate(css) == css

    def test_custom_property_definitions_are_left_alone(self):
        css = ":root { --sp-2: 8px; --gap: 16px; }"
        assert px.migrate(css) == css

    def test_reverting_restores_exactly_what_was_written(self):
        css = ".a { padding: 8px 6px; margin: 16px; border-radius: 4px; }"
        assert px.revert(px.migrate(css)) == css

    def test_the_token_tables_match_the_root_definitions(self):
        css = read_css()
        for table in (px.SPACING_TOKENS, px.RADIUS_TOKENS):
            for value, token in table.items():
                assert f"{token}:" in css.replace(" ", "") or f"{token}: " in css, token
                import re

                assert re.search(
                    rf"{re.escape(token)}\s*:\s*{value}px", css
                ), f"{token} ≠ {value}px"
