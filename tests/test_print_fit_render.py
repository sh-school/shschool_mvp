"""[PRINT] محرّكُ الملاءمة يُقاس **مرسوماً** بتخطيط WeasyPrint (المواصفة §٨-٢/٤): ما يقوله `fit()` هو ما يخرج على الورق.

تُرسم مناطقُ `fit` تحت الإطار المركزيّ الحقيقيّ على **أسوأ محتوى** (أقصى نصوص، معيارٌ بـ69 حرفاً، خليّةٌ منقسمةٌ، `rows=26`)، فيُقاس: `len(pages)` = المتوقّع،
وأصغرُ خطٍّ مرسومٍ ≥ حدّه، وارتفاعُ كلّ منطقةٍ لا يتجاوز ما حسبه المحرّك، وخطُّ الأساس `tests/pdf_fit_baseline.json` لا ينزل (خطٌّ) ولا يزيد (صفحاتٌ ومواضعُ قصّ).
مسحُ ارتفاعات الصفحة يكشف أيَّ تفاؤلٍ في النموذج قربَ الحدّ: لا يقول `fit` «يتّسع» والمرسومُ يفيض.
"""

import json
import random

import pytest

from core.print_fit import fit as fitmod
from core.print_fit.fit import FitPrefs, FitZone, Layout, NotFit, Page, fit
from tests import print_fit_ratchet as ratchet
from tests.print_fit_corpus import corpus
from tests.print_fit_render import frame_body_bottom_mm, measure, render

weasyprint = pytest.importorskip("weasyprint")

WORDS = [w for t in corpus(160) for w in t.split()]
TOL_MM = 0.6  # شعرةُ تقريب البكسل بين حسابٍ بالملّيمتر ورسمٍ بالبكسل


def _para(rng: random.Random, chars: int) -> str:
    out: list[str] = []
    while len(" ".join(out)) < chars:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:chars].rsplit(" ", 1)[0]


def _visit_zones(seed: int, notes: int, recs: int, rec_chars: int, comment: int) -> list[FitZone]:
    rng = random.Random(seed)
    text = {
        "kind": "text",
        "width_mm": 190.0,
        "ideal_pt": 11.0,
        "min_pt": 10.0,
        "line_height": 1.35,
        "paragraph_gap_mm": 1.0,
        "pad_mm": 3.0,
        "min_pad_mm": 1.0,
        "continuable": True,
    }
    return [
        FitZone(key="head", kind="fixed", height_mm=36.0),
        FitZone(
            key="criteria",
            kind="table",
            ideal_pt=11.0,
            min_pt=10.0,
            line_height=1.2,
            cell_texts=(_para(rng, 69),),
            cell_width_mm=135.0,
            rows=23,
            header_mm=8.0,
            row_pad_mm=0.8,
            min_row_pad_mm=0.8,
        ),
        FitZone(key="sign", kind="fixed", height_mm=22.0),
        FitZone(key="notes", paragraphs=(_para(rng, notes),), flex_weight=1.0, **text),
        FitZone(
            key="recs",
            paragraphs=tuple(_para(rng, rec_chars) for _ in range(recs)),
            numbered=True,
            flex_weight=1.5,
            **text,
        ),
        FitZone(key="comment", paragraphs=(_para(rng, comment),), flex_weight=1.0, **text),
    ]


def _schedule_zones(rows: int) -> list[FitZone]:
    # أسوأُ خليّةٍ في الأسبوع المعروض: خليّةٌ منقسمةٌ (إدخالان) مع علامة تعويض
    worst = "رياضيات علوم"
    return [
        FitZone(key="legend", kind="fixed", height_mm=5.0),
        FitZone(
            key="matrix",
            kind="table",
            ideal_pt=10.0,
            min_pt=6.0,
            line_height=1.2,
            cell_texts=("رياضيات", worst),
            cell_width_mm=11.1,
            header_mm=11.0,
            row_pad_mm=0.8,
            min_row_pad_mm=0.8,
        ),
    ]


SCENARIOS = {
    "visit_form a4/portrait": {
        "zones": lambda: _visit_zones(1, 160, 4, 110, 110),
        "paper": ("a4", "portrait"),
        "min_pt": 10.0,
        "rows": None,
        "prefs": FitPrefs(template="visit_form"),
    },
    "visit_form_legacy_overflow a4/portrait": {
        "zones": lambda: _visit_zones(2, 420, 14, 240, 500),
        "paper": ("a4", "portrait"),
        "min_pt": 10.0,
        "rows": None,
        "prefs": FitPrefs(template="visit_form_legacy", allow_continuation=True),
    },
    "general_schedule rows25 a3/landscape": {
        "zones": lambda: _schedule_zones(25),
        "paper": ("a3", "landscape"),
        "min_pt": 6.0,
        "rows": 25,
        "prefs": FitPrefs(template="general_schedule"),
    },
    "general_schedule rows26 a3/landscape": {
        "zones": lambda: _schedule_zones(26),
        "paper": ("a3", "landscape"),
        "min_pt": 6.0,
        "rows": 26,
        "prefs": FitPrefs(template="general_schedule"),
    },
}


def _baseline() -> dict:
    return ratchet.baseline()


def _run(name: str):
    sc = SCENARIOS[name]
    zones = sc["zones"]()
    page = Page.from_frame(*sc["paper"])
    result = fit(zones, page, sc["min_pt"], sc["prefs"], rows=sc["rows"])
    return zones, page, result, sc


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_drawn_document_matches_the_engine(name):
    zones, page, layout, sc = _run(name)
    assert isinstance(layout, Layout), getattr(layout, "reason", layout)
    doc = render(zones, layout, page, sc["rows"])
    m = measure(doc)
    expected_pages = layout.pages
    assert m.pages == expected_pages, (
        name,
        "عددُ الصفحات المرسوم",
        m.pages,
        "المتوقّع",
        expected_pages,
    )
    floor = min(z.floor_pt(sc["min_pt"]) for z in zones if z.has_font)
    assert m.min_font_pt >= floor - 0.05, (name, "أصغرُ خطٍّ مرسوم", m.min_font_pt, "الحدّ", floor)
    for zl in layout.zones:
        drawn = m.zone_heights_mm.get(zl.key)
        assert drawn is not None, (name, zl.key)
        if zl.kind in ("text", "table"):
            assert drawn <= zl.height_mm - zl.extra_mm + TOL_MM, (
                name,
                zl.key,
                "ارتفاعٌ مرسومٌ أكبرُ مما حسبه المحرّك",
                drawn,
                zl.height_mm,
            )
    assert m.last_bottom_mm <= frame_body_bottom_mm(*sc["paper"]) + TOL_MM, (
        name,
        "المتنُ يتجاوز حدَّه",
        m.last_bottom_mm,
    )


def test_continuation_is_drawn_as_a_second_page_with_the_carried_text():
    zones, page, layout, _ = _run("visit_form_legacy_overflow a4/portrait")
    assert isinstance(layout, Layout) and layout.continuation and layout.report.continuation_used
    doc = render(zones, layout, page)
    assert len(doc.pages) == layout.pages >= 2
    body_text = " ".join(t for p in doc.pages for t in _page_words(p))
    assert "تتمّة" in body_text
    for c in layout.continuation:
        assert c.paragraphs and c.first_number >= 1


def _page_words(page):
    from tests.print_fit_render import _walk

    for box, in_margin in _walk(page._page_box):
        if not in_margin and hasattr(box, "text") and box.text:
            yield box.text


def test_a_sweep_of_page_heights_never_finds_the_engine_optimistic():
    """قربَ الحدّ: كلُّ ما يقول عنه `fit` «يتّسع بلا تتمّة» يُرسم في صفحةٍ واحدةٍ بحدّ الخطّ فما فوق."""
    base_page = Page.from_frame("a4", "portrait")
    optimistic = []
    seen_layouts = 0
    for delta in range(0, 60, 5):
        page = Page(base_page.body_width_mm, base_page.body_height_mm - delta, "a4", "portrait")
        zones = _visit_zones(4, 120, 3, 90, 80)
        result = fit(zones, page, 10.0, FitPrefs(template="sweep"))
        if not isinstance(result, Layout):
            assert isinstance(result, NotFit) and result.deficit_mm > 0
            continue
        seen_layouts += 1
        m = measure(render(zones, result, page))
        if m.pages != 1 or m.min_font_pt < 10.0 - 0.05:
            optimistic.append((delta, m.pages, m.min_font_pt))
    assert seen_layouts >= 3
    assert not optimistic, f"`fit` قال «يتّسع» والمرسومُ يخالف: {optimistic}"


def test_not_fit_is_returned_when_the_fixed_zones_leave_no_room():
    zones = _visit_zones(5, 160, 4, 110, 110)
    zones[0] = FitZone(key="head", kind="fixed", height_mm=190.0)
    result = fit(zones, Page.from_frame("a4", "portrait"), 10.0, FitPrefs(template="x"))
    assert (
        isinstance(result, NotFit)
        and result.report.steps_taken[-1] == fitmod.STEP_FAIL
        and result.deficit_mm > 0
    )


# ── خطُّ الأساس: tests/pdf_fit_baseline.json ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_baseline_does_not_regress_for_the_engine_scenarios(name):
    """`min_font_pt` لا ينزل، و`pages` لا تزيد، و«التتمّة» مسموحةٌ للبيانات القديمة وحدَها (§٨-٤)."""
    entry = _baseline()["engine"][name]
    zones, page, layout, sc = _run(name)
    assert isinstance(layout, Layout), getattr(layout, "reason", layout)
    m = measure(render(zones, layout, page, sc["rows"]))
    assert m.min_font_pt >= entry["min_font_pt"] - 0.05, (
        name,
        "نزل الخطُّ عن خطّ الأساس",
        m.min_font_pt,
        entry["min_font_pt"],
    )
    assert m.pages <= entry["pages"], (name, "زادت الصفحاتُ", m.pages, entry["pages"])
    assert layout.report.continuation_used <= entry["continuation_used"], (
        name,
        "«تتمّة» لبياناتٍ غيرِ قديمة",
    )


def test_the_baseline_file_has_the_legacy_floors_measured_on_2026_09_26():
    """قيمُ القوالب القديمة (قياسُ 2026-09-26، المواصفة ١-٢) تدخل بأرقامها الحاليّة فلا يسقط شيء، وتُرفع عند كلّ ترحيل."""
    legacy = _baseline()["legacy"]
    assert legacy["general_schedule a3"]["min_font_pt"] == 5.2
    assert legacy["visit_form"]["min_font_pt"] == 7.2
    for name, entry in legacy.items():
        assert entry["min_font_pt"] > 0 and entry["pages"] >= 1, name


def test_the_clipping_sites_ratchet_never_grows():
    grew, _ = ratchet.compare()
    assert not grew, f"قصٌّ جديدٌ في قوالب PDF (truncatechars/text-overflow/line-clamp/overflow:hidden) — استعمل المحرّكَ (تتمّة أو فشلٌ صريح)، لا القصّ الصامت: {grew}"


def test_a_clipping_drop_is_recorded_so_it_is_not_spent_later():
    _, dropped = ratchet.compare()
    assert not dropped, f"نقصت مواضعُ قصٍّ ({dropped}) — أحسنت؛ سجِّلها بـ`python -m tests.print_fit_ratchet --update` في هذا الطلب"


def test_the_baseline_json_is_well_formed():
    data = json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))
    assert set(data) >= {"clipping_sites", "engine", "legacy"}
    for name in SCENARIOS:
        assert name in data["engine"], name
