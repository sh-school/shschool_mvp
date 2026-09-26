"""[PRINT] الإطارُ المطبوعُ المركزيّ — ثوابتُ الترويسة والتذييل والهوامش وخطّةُ صفّ التذييل (`core/print_frame.py`).

المواصفة `docs/design/print_fit_spec.md` §٥ (قراراتُ المالك 2026-09-26): ترويسةٌ كاملةٌ ≈30 ملم، وتذييلٌ صفٌّ واحدٌ 8 ملم، وهوامشُ علويّةٌ
وسفليّةٌ 6 ملم؛ والرؤيةُ تنتقل إلى الترويسة على الورق العموديّ (D1). الدوالُّ نقيّةٌ فالاختباراتُ بلا قاعدة ولا متصفّح.
"""

import pytest

from core import print_frame as pf

# نصوصٌ بأطوال المواصفة (اسمُ المدرسة 40 حرفاً، الرؤية 49، الوزارة 38، الاتّصال 48).
SCHOOL = "م" * 40
VISION = "ر" * 49
MINISTRY = "و" * 38
CONTACT = "ا" * 48


def _plan(paper, orient, **kw):
    kw.setdefault("school", SCHOOL)
    kw.setdefault("vision", VISION)
    kw.setdefault("ministry", MINISTRY)
    kw.setdefault("contact", CONTACT)
    return pf.footer_plan(pf.frame(paper, orient), **kw)


# ══════════════════════ الثوابت ═════════════════════════════════════════


@pytest.mark.parametrize(
    ("paper", "orient", "header", "body_h"),
    [
        ("a4", "portrait", 35.0, 238.0),
        ("a4", "landscape", 30.0, 156.0),
        ("a3", "landscape", 30.0, 243.0),
        ("a3", "portrait", 35.0, 361.0),
    ],
)
def test_the_frame_constants_leave_this_body_height(paper, orient, header, body_h):
    fr = pf.frame(paper, orient)
    assert fr.header_h == header
    assert fr.footer_h == 8.0
    assert fr.body_height == body_h
    # ارتفاعُ الصفحة = هوامش + إطار + فواصل + المتن، لا فراغَ مجهول.
    assert fr.top_total + fr.body_height + fr.bottom_total == pytest.approx(fr.page_h)


def test_the_body_height_is_what_the_fit_engine_reads_not_a_guess():
    """`body_height` = الورق − الهوامش − الترويسة − التذييل − الفاصلين: ما تطرحه الملاءمةُ من ارتفاع الصفحة."""
    fr = pf.frame("a3", "landscape")
    assert fr.body_height == 297 - (6 + 30 + 2) - (6 + 8 + 2)
    assert fr.body_width == 420 - 2 * 9


def test_an_unknown_paper_fails_loudly():
    with pytest.raises(ValueError, match="غيرُ معروفة"):
        pf.frame("a5", "portrait")
    with pytest.raises(ValueError):
        pf.frame("a4", "sideways")


def test_the_vision_moves_to_the_header_only_on_portrait_paper():
    """D1: التذييلُ العموديُّ بـ10pt لا يسع الرؤيةَ مع الملزِم، فتنتقل إلى الترويسة (+5 ملم)؛ وتبقى في التذييل أفقيّاً وعلى A3."""
    assert pf.frame("a4", "portrait").vision_in_header
    assert not pf.frame("a4", "landscape").vision_in_header
    assert not pf.frame("a3", "landscape").vision_in_header
    assert pf.frame("a4", "portrait").header_h == pf.frame("a4", "landscape").header_h + 5


def test_the_page_css_carries_size_margins_and_the_two_running_boxes():
    css = pf.frame("a4", "portrait").page_css()
    assert "size: A4 portrait" in css
    assert "margin: 43mm 9mm 16mm 9mm" in css  # 6+35+2 علوّاً، 6+8+2 سفلاً
    assert "element(print-header)" in css and "element(print-footer)" in css
    assert "#" not in css, "هندسةٌ بلا ألوان — الألوانُ في قالب المكوّن من brand_color"


# ══════════════════════ خطّةُ صفّ التذييل ═════════════════════════════


def test_the_text_width_model_matches_the_spec_numbers():
    """الحرفُ 0.42em والرقمُ 0.55em: 40 حرفاً = 16.8، والتاريخ والوقت (16 محرفاً رقميّاً) = 8.8."""
    assert pf.text_em("م" * 40) == 16.8
    assert pf.text_em("2026/09/26 22:40") == pytest.approx(8.8 + 0.42 * 0 - 0, abs=0.3)


def test_the_mandatory_trio_fits_a4_portrait_at_10pt_and_nothing_optional_does():
    """الملزِمُ 34.5em ≤ السعة 53.9em؛ والرؤيةُ خارج التذييل (D1) والوزارةُ (16em) تسع: 34.5+1.5+16 = 52 ≤ 53.9."""
    plan = _plan("a4", "portrait")
    assert plan.capacity_em == pytest.approx(53.9, abs=0.2)
    assert plan.fits
    assert plan.items[:3] == ("school", "page", "date")
    assert "vision" not in plan.items


def test_a4_landscape_takes_vision_and_ministry_after_the_mandatory():
    """السعة 78.5em: الملزِم + الرؤية (20.6) + الوزارة (16) = 74.1 — ولا يسع الاتّصال (24) معها."""
    plan = _plan("a4", "landscape")
    assert plan.items == ("school", "page", "date", "vision", "ministry")
    assert "contact" in plan.dropped and plan.fits


def test_a3_takes_everything_that_the_priority_list_offers():
    plan = _plan("a3", "landscape")
    assert plan.items == pf.FOOTER_ITEMS and not plan.dropped


def test_an_item_that_does_not_fit_does_not_block_a_shorter_lower_priority_one():
    """A4 أفقيّ بـ9pt: الاتّصال لا يسع لكنّ SchoolOS-SAMM (أقصرُ منه) يُدرَج (المواصفة ٥-٢)."""
    plan = _plan("a4", "landscape", font_pt=9.0)
    assert "contact" in plan.dropped
    assert "samm" in plan.items


def test_a_school_name_longer_than_the_row_is_reported_not_silently_cut():
    plan = _plan("a4", "portrait", school="م" * 200)
    assert not plan.fits, "الملزِمُ لا يسعه الصفّ: الخطّةُ تُبلغ لا تقصّ"


def test_shortening_the_vision_brings_it_back_when_it_fits():
    """الرؤيةُ الأقصرُ تُدرَج حيث لم تسع الأطول (A4 أفقيّ بلا الوزارة)."""
    long_plan = _plan("a4", "landscape", vision="ر" * 120)
    short_plan = _plan("a4", "landscape", vision="ر" * 40)
    assert "vision" in long_plan.dropped
    assert "vision" in short_plan.items
