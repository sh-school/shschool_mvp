"""[PRINT] `fit()` النقيّة (E3): ترتيبُ الخطوات، ولا نزولَ دون الحدّ، وأسوأُ خليّةٍ، و`rows` معاملٌ، و«تتمّة» بلا قصّ، والفشلُ بصوتٍ عالٍ (المواصفة §٨-١).

بلا WeasyPrint: الحَكَمُ المرسومُ في `tests/test_print_fit_render.py`. هنا سلوكُ الخوارزميّة على تركيباتِ أسوأ المحتوى.
"""

import random

import pytest

from core.print_fit import capacity as cap
from core.print_fit import fit as fitmod
from core.print_fit.fit import (
    FitInputError,
    FitPrefs,
    FitZone,
    Layout,
    MissingAbbreviationError,
    NotFit,
    Page,
    abbreviate,
    fit,
)
from tests.print_fit_corpus import corpus

WORDS = [w for t in corpus(120) for w in t.split()]


def _para(rng: random.Random, n_words: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n_words))


def _text(key="recs", paragraphs=(), **kw) -> FitZone:
    base = {
        "key": key,
        "kind": "text",
        "width_mm": 180.0,
        "ideal_pt": 11.0,
        "line_height": 1.35,
        "numbered": True,
        "paragraph_gap_mm": 1.0,
        "pad_mm": 3.0,
        "min_pad_mm": 1.0,
        "continuable": True,
    }
    base.update(kw)
    return FitZone(paragraphs=tuple(paragraphs), **base)  # type: ignore[arg-type]


def _page(h: float, w: float = 192.0) -> Page:
    return Page(body_width_mm=w, body_height_mm=h, paper="a4", orient="portrait")


def _layout(result) -> Layout:
    assert isinstance(result, Layout), getattr(result, "reason", result)
    return result


def _heights(layout: Layout) -> float:
    return layout.used_mm


def test_short_content_takes_the_ideal_font_and_the_surplus_by_weight():
    zones = [
        FitZone(key="head", kind="fixed", height_mm=20.0),
        _text("notes", ["ملاحظة قصيرة"], flex_weight=1.0),
        _text("recs", ["توصية قصيرة"], flex_weight=1.5),
    ]
    layout = _layout(fit(zones, _page(200.0), 10.0))
    assert layout.report.steps_taken == (0, 1) and layout.report.ideal_used
    assert layout.zone("notes").font_pt == layout.zone("recs").font_pt == 11.0
    notes, recs = layout.zone("notes").extra_mm, layout.zone("recs").extra_mm
    assert notes > 0 and recs / notes == pytest.approx(1.5, rel=1e-3)
    assert layout.pages == 1 and not layout.continuation


def test_a_fill_zone_takes_all_the_surplus():
    zones = [_text("notes", ["س"]), FitZone(key="hand", kind="fill", height_mm=20.0)]
    layout = _layout(fit(zones, _page(150.0), 10.0))
    assert layout.zone("notes").extra_mm == 0 and layout.zone("hand").extra_mm > 0


def test_step2_whitespace_comes_before_shrinking_the_font():
    rng = random.Random(3)
    paras = [_para(rng, 14) for _ in range(6)]
    zone = _text("recs", paras)
    ideal_h = cap.used_height_mm(fitmod._cap_zone(zone), paras, 11.0) + 3.0
    # ضيّق الصفحةَ بقدر الحشو فقط: يكفي تخفيفُ الحشو والفاصل، فيبقى الخطُّ مثاليّاً
    zones = [FitZone(key="h", kind="fixed", height_mm=10.0), zone]
    page = _page(10.0 + 4.0 + ideal_h - 1.5)
    layout = _layout(fit(zones, page, 10.0, FitPrefs(gap_mm=4.0, min_gap_mm=2.0)))
    assert layout.report.steps_taken == (0, 1, 2)
    assert layout.zone("recs").font_pt == 11.0 and layout.gap_mm == 2.0


def test_step3_two_columns_for_lists_only():
    items = [f"بند {i}" for i in range(24)]
    zone = FitZone(
        key="keys",
        kind="text",
        width_mm=180.0,
        ideal_pt=10.0,
        line_height=1.2,
        columns_ok=True,
        paragraphs=tuple(items),
        pad_mm=1.0,
        min_pad_mm=1.0,
    )
    one_col_h = cap.used_height_mm(fitmod._cap_zone(zone), items, 10.0) + 1.0
    layout = _layout(fit([zone], _page(one_col_h * 0.7), 10.0))
    assert layout.report.steps_taken == (0, 1, 2, 3)
    assert layout.zone("keys").columns == 2 and layout.zone("keys").font_pt == 10.0


def test_columns_and_continuation_do_not_mix():
    with pytest.raises(FitInputError):
        fit([_text("x", ["a"], columns_ok=True, continuable=True)], _page(100.0), 10.0)


def test_gradient_steps_half_a_point_and_never_below_the_minimum():
    rng = random.Random(5)
    paras = [_para(rng, 22) for _ in range(7)]
    zone = _text("recs", paras, continuable=False)
    fixed = FitZone(key="h", kind="fixed", height_mm=10.0)
    at = lambda pt: cap.used_height_mm(fitmod._cap_zone(zone), paras, pt) + 1.0 + 10.0 + 2.0  # noqa: E731
    page = _page((at(10.5) + at(10.0)) / 2)  # يتّسع عند 10.0 ولا عند 10.5
    layout = _layout(fit([fixed, zone], page, 10.0))
    assert layout.report.steps_taken == (0, 1, 2, 4)
    pt = layout.zone("recs").font_pt
    assert pt is not None and 10.0 <= pt < 11.0 and (pt * 2) == int(pt * 2), pt


def test_free_text_shrinks_before_the_table():
    rng = random.Random(9)
    table = FitZone(
        key="t",
        kind="table",
        ideal_pt=10.0,
        cell_texts=("مادة 12.4",),
        cell_width_mm=18.0,
        rows=20,
        header_mm=6.0,
    )
    text = _text("recs", [_para(rng, 20) for _ in range(6)], continuable=False)
    zones = [table, text]
    ample = _layout(fit(zones, _page(500.0), 9.0))
    assert ample.report.ideal_used
    tight_h = ample.used_mm * 0.93
    layout = _layout(fit(zones, _page(tight_h), 9.0))
    assert layout.zone("t").font_pt == 10.0, "الجدولُ لا يتدرّج قبل النصوص الحرّة"
    assert layout.zone("recs").font_pt < 11.0


def test_rows_is_a_parameter_and_more_rows_need_more_room():
    table = FitZone(
        key="t",
        kind="table",
        ideal_pt=9.0,
        cell_texts=("رياضيات",),
        cell_width_mm=20.0,
        header_mm=8.0,
    )
    h25 = _layout(fit([table], _page(500.0), 6.0, rows=25)).used_mm
    h26 = _layout(fit([table], _page(500.0), 6.0, rows=26)).used_mm
    assert h26 > h25
    with pytest.raises(FitInputError, match="rows"):
        fit([table], _page(500.0), 6.0)


def test_the_worst_cell_of_the_displayed_week_sets_the_row_height():
    plain = FitZone(
        key="t",
        kind="table",
        ideal_pt=9.0,
        cell_texts=("رياضيات",),
        cell_width_mm=12.0,
        rows=25,
        header_mm=6.0,
    )
    split = FitZone(
        key="t",
        kind="table",
        ideal_pt=9.0,
        cell_texts=("رياضيات", "رياضيات 12.4 علوم 11.2 تعويض"),
        cell_width_mm=12.0,
        rows=25,
        header_mm=6.0,
    )
    a = _layout(fit([plain], _page(900.0), 6.0))
    b = _layout(fit([split], _page(900.0), 6.0))
    assert b.zone("t").lines > a.zone("t").lines and b.used_mm > a.used_mm
    small = _page(a.used_mm + 5)
    fa = _layout(fit([plain], small, 6.0)).zone("t").font_pt
    fb = fit([split], small, 6.0)
    assert fa == 9.0
    assert (
        isinstance(fb, NotFit) or (fb.zone("t").font_pt or 0) < fa
    ), "أسوأُ خليّةٍ تخفض الخطَّ أو تفشل — لا تُتجاهل"


def test_a_missing_abbreviation_fails_loudly_never_truncates():
    zone = FitZone(
        key="t",
        kind="table",
        ideal_pt=9.0,
        cell_texts=("ر",),
        cell_width_mm=12.0,
        rows=3,
        terms=("رياضيات", "مادّة جديدة"),
        abbreviations={"رياضيات": "رض"},
    )
    with pytest.raises(MissingAbbreviationError) as err:
        fit([zone], _page(300.0), 6.0)
    assert "مادّة جديدة" in str(err.value) and err.value.missing == ("مادّة جديدة",)
    assert abbreviate(["رياضيات", "رياضيات"], {"رياضيات": "رض"}) == {"رياضيات": "رض"}
    with pytest.raises(MissingAbbreviationError):
        abbreviate(["س"], {"س": ""})


def test_continuation_carries_the_rest_whole_with_no_clipping():
    rng = random.Random(11)
    paras = [_para(rng, 28) for _ in range(14)]
    zones = [FitZone(key="h", kind="fixed", height_mm=40.0), _text("recs", paras)]
    page = _page(120.0)
    assert isinstance(fit(zones, page, 10.0, FitPrefs(allow_continuation=False)), NotFit)
    layout = _layout(fit(zones, page, 10.0, FitPrefs(allow_continuation=True)))
    assert (
        layout.report.steps_taken[-1] == 7 and layout.report.continuation_used and layout.pages >= 2
    )
    assert layout.zone("recs").font_pt == 10.0, "لا نزولَ دون الحدّ حتى في التتمّة"
    (carry,) = layout.continuation
    kept = layout.zone("recs").paragraphs
    original_words = " ".join(paras).split()
    got_words = " ".join(list(kept) + list(carry.paragraphs)).split()
    assert got_words == original_words, "ما بقي + ما حملته التتمّةُ = الأصلُ كاملاً بلا قصّ"
    assert carry.first_number >= 1 and "تتمّة" in carry.label and carry.lines > 0
    assert layout.used_mm <= page.body_height_mm + 1e-6


def test_not_fit_reports_the_limit_and_never_goes_below_min():
    rng = random.Random(13)
    zones = [
        FitZone(key="h", kind="fixed", height_mm=100.0),
        _text("recs", [_para(rng, 30) for _ in range(20)], continuable=False),
    ]
    result = fit(zones, _page(150.0), 10.0)
    assert isinstance(result, NotFit)
    assert (
        result.limit_mm == pytest.approx(48.0, abs=0.1)
        and result.deficit_mm > 0
        and result.needed_mm > result.limit_mm
    )
    assert result.report.fits is False and result.report.steps_taken[-1] == 8
    assert result.report.final_font_by_zone["recs"] == 10.0
    assert "لا يتّسع" in result.reason


def test_fixed_zones_alone_over_the_page_is_not_fit_even_with_continuation():
    zones = [FitZone(key="h", kind="fixed", height_mm=200.0), _text("recs", ["س ص ع"])]
    assert isinstance(fit(zones, _page(150.0), 10.0, FitPrefs(allow_continuation=True)), NotFit)


def test_capacity_and_fit_agree_no_continuation_when_capacity_accepts():
    """ما تقبله `capacity` عند الحدّ الأدنى تقبله `fit` بلا «تتمّة» (المواصفة §٨-١)."""
    rng = random.Random(21)
    for _ in range(40):
        paras = [_para(rng, rng.choice([3, 8, 15, 25])) for _ in range(rng.choice([1, 3, 6, 10]))]
        height = rng.choice([40.0, 70.0, 110.0, 160.0])
        zone = FitZone(
            key="recs",
            kind="text",
            width_mm=150.0,
            ideal_pt=12.0,
            line_height=1.35,
            numbered=True,
            paragraph_gap_mm=1.0,
            pad_mm=2.0,
            min_pad_mm=2.0,
            continuable=True,
            paragraphs=tuple(paras),
        )
        c = cap.capacity(
            cap.Zone(
                width_mm=150.0,
                height_mm=height - 2.0,
                line_height=1.35,
                paragraph_gap_mm=1.0,
                numbered=True,
            ),
            paras,
            10.0,
        )
        result = fit([zone], _page(height), 10.0, FitPrefs(allow_continuation=True))
        if c.fits:
            layout = _layout(result)
            assert not layout.continuation and (layout.zone("recs").font_pt or 0) >= 10.0
        elif isinstance(result, Layout):
            assert result.continuation, "فوق السعة عند الحدّ ⇒ لا يتّسع بلا تتمّة"


def test_pure_and_deterministic():
    rng = random.Random(1)
    zones = [_text("recs", [_para(rng, 20) for _ in range(5)])]
    a = fit(zones, _page(90.0), 10.0, FitPrefs(allow_continuation=True))
    b = fit(zones, _page(90.0), 10.0, FitPrefs(allow_continuation=True))
    assert a == b


def test_record_report_counts_and_warns_from_the_continuation_step(caplog):
    fitmod.COUNTERS.clear()
    rng = random.Random(2)
    zones = [
        FitZone(key="h", kind="fixed", height_mm=40.0),
        _text("recs", [_para(rng, 28) for _ in range(14)]),
    ]
    layout = _layout(
        fit(zones, _page(120.0), 10.0, FitPrefs(template="visit", allow_continuation=True))
    )
    with caplog.at_level("INFO", logger="schoolos.print_fit"):
        fitmod.record_report(layout.report)
    assert fitmod.COUNTERS["fit_continuation{template=visit}"] == 1
    assert fitmod.COUNTERS["fit_step{template=visit,step=7}"] == 1
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_page_reads_the_frame_constants():
    page = Page.from_frame("a3", "landscape")
    assert (page.body_width_mm, page.body_height_mm) == (402.0, 249.0) or page.body_height_mm > 200
