"""[IDENTITY] أدوارُ الألوان والخطوط (قرارُ المالك D-15، 2026-09-25) — VI-02 وVI-19.

**الذهبيُّ لونُ تمييزٍ لا لونَ نصّ.** كان في الأنماط خمسةُ مواضعَ تكتب `color: var(--gold)` (V-K12): أربعٌ منها أيقوناتٌ
على شريطٍ عنّابيٍّ أو رأس نافذةٍ عنّابيّ — وهو دورُه المشروع — وخامسةٌ نصٌّ فعليٌّ (`html.dark .staff-name`، اسمُ الموظّف
ليلاً). وعلى السطح الفاتح تباينُه 2.1:1 فلا يُقرأ نصّاً ولا تُرى به أيقونةٌ. فصار للدور رمزٌ (`--gold-mark`) تُكتب به
الأيقوناتُ على العنّابيّ والداكن، وصار الحارسُ يمنع أن يُكتب أيُّ لونٍ من ألوان العلامة الخام (`gold`، `palm`، `sea`،
`maroon-light`) لوناً للنصّ — فالنصُّ يقرأ رموزَ `-fg` و`--text-*` التي تنقلب ليلاً وتُقاس تبايناً. وحدُّ التباين لرمز الدور
على أسطحه في `test_contrast_ratios.py::SHAPE_PAIRS`.

**Amiri للـPDF وحدَه.** كانت جداولُ الجودة على الويب بـAmiri (`--q-font-data`) ولا خطَّ غيرَه يحمل تشكيلاً على المنصّة
سوى Tajawal؛ فوُحِّدت على Tajawal، وحُذف ملفّا woff2 (≈741KB) وكتلتا `@font-face` والرمز. وتبقى ملفّاتُ TTF لأنّ
`core/pdf_utils.py` يسجّلها في ReportLab لـPDF — فالحارسُ يمنع Amiri على الويب ويُثبت بقاءَ ما يحتاجه PDF.
"""

from __future__ import annotations

import pathlib
import re

from tests.css_contrast import iter_rules, strip_noise, token_table
from tests.css_source import CSS_ROOT, read_css

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "static" / "fonts"
STYLEGUIDE = ROOT / "templates" / "styleguide" / "components.html"

#: ألوانُ العلامة الخام — لا يُكتب أيٌّ منها لوناً للنصّ. (`-fg` و`--text-*` هما ما يُكتب به النصّ.)
RAW_BRAND = ("gold", "palm", "sea", "maroon-light")
RAW_TEXT_RE = re.compile(rf"var\(\s*--({'|'.join(RAW_BRAND)})\s*\)")

#: أقلُّ ما يجب أن يراه الحارس من القواعد — قيسَ نحو 2,600 قاعدةٍ يومَ كتابته.
MIN_RULES = 1500


def first_party_sheets() -> list[pathlib.Path]:
    """كلُّ ورقةِ أنماطٍ لنا على الويب: حزمةُ المنصّة والإدارةُ ودليلُ الهويّة (لا `*.min.css` المولَّدة)."""
    return sorted(p for p in CSS_ROOT.parent.glob("*.css") if not p.name.endswith(".min.css"))


def raw_text_colours(css: str) -> list[tuple[str, str]]:
    """(المُحدِّد، القيمة) لكلّ `color:` يكتب لونَ علامةٍ خاماً."""
    found = []
    for selector, decls, _ in iter_rules(css):
        if selector.startswith("@"):
            continue
        value = decls.get("color", "")
        if RAW_TEXT_RE.search(value):
            found.append((selector, value))
    return found


def test_no_brand_colour_is_written_as_a_text_colour():
    sheets = {
        "custom": read_css(),
        **{p.name: p.read_text(encoding="utf-8") for p in first_party_sheets()},
    }
    bad = [
        f"{name}: {sel} → color: {value}"
        for name, css in sheets.items()
        for sel, value in raw_text_colours(css)
    ]
    assert not bad, (
        "لونُ علامةٍ خامٌ يُكتب لونَ نصّ (D-15) — الأيقونةُ على العنّابيّ/الداكن `var(--gold-mark)`، والنصُّ "
        "`var(--maroon-fg)` أو `var(--text-*)`:\n  " + "\n  ".join(bad)
    )


def test_the_guard_reads_enough_rules_to_mean_something():
    assert sum(1 for head, _, _ in iter_rules(read_css()) if not head.startswith("@")) >= MIN_RULES


def test_the_gold_role_token_points_at_gold_and_is_documented():
    light, _ = token_table(read_css())
    assert (
        light.get("--gold-mark", "").replace(" ", "") == "var(--gold)"
    ), "رمزُ الدور --gold-mark يجب أن يشير إلى --gold"
    guide = STYLEGUIDE.read_text(encoding="utf-8")
    assert (
        "--gold-mark" in guide
    ), "دورُ الذهبيّ يجب أن يُوثَّق في دليل الهويّة (templates/styleguide/components.html)"


def test_amiri_is_never_loaded_by_the_web_stylesheets():
    problems = []
    for name, css in {
        "custom": read_css(),
        **{p.name: p.read_text(encoding="utf-8") for p in first_party_sheets()},
    }.items():
        code = strip_noise(css)
        for needle in ("Amiri", "--q-font-data"):
            if needle in code:
                problems.append(f"{name}: يذكر {needle}")
    problems += [
        f"static/fonts/{p.name}: خطٌّ للويب لا يُحمَّل" for p in sorted(FONTS.glob("Amiri-*.woff2"))
    ]
    assert not problems, "Amiri للـPDF وحدَه (D-15) — جداولُ الويب على Tajawal:\n  " + "\n  ".join(
        problems
    )


def test_the_pdf_still_finds_the_amiri_files_it_registers():
    pdf = (ROOT / "core" / "pdf_utils.py").read_text(encoding="utf-8")
    for name in ("Amiri-Regular.ttf", "Amiri-Bold.ttf"):
        assert (
            name in pdf
        ), f"core/pdf_utils.py لم يعد يسجّل {name} — إن أُزيل Amiri من PDF فاحذف الملفَّ وهذا الفحص معاً"
        assert (FONTS / name).exists(), f"static/fonts/{name} يحتاجه PDF — لا يُحذف مع woff2"


class TestTheDetectorItself:
    def test_a_raw_brand_text_colour_is_found_but_borders_and_role_tokens_are_not(self):
        css = """
        .a { color: var(--gold); }
        .b { border-color: var(--gold); }
        .c { color: var(--gold-mark); }
        .d { color: var( --sea ); }
        .e { background: var(--palm); }
        .f { color: var(--maroon-fg); }
        .g { color: var(--maroon-light); }
        """
        assert [sel for sel, _ in raw_text_colours(css)] == [".a", ".d", ".g"]

    def test_a_comment_that_mentions_the_bad_form_is_ignored(self):
        assert raw_text_colours("/* color: var(--gold) */ .a { color: var(--text-primary); }") == []
