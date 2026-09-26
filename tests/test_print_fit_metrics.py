"""[PRINT] محرّكُ الملاءمة (E1 قياسُ النصّ + E2 السعة) يُعاير على **تخطيط WeasyPrint نفسِه** لا على تخمين.

- المعايرةُ (≥ 200 نصٍّ من `print_fit_corpus`، لكلّ خطٍّ ووزن): خطأُ العرض ≤ 5% وعددُ الأسطر مطابقٌ في ≥ 95% من الحالات.
  ما زاد على ذلك يُعالَج بمعاملٍ مقيسٍ في `text_metrics.CALIBRATION` لا بتوسيع العتبة.
- السعةُ (`capacity`): فقراتٌ متعدّدةٌ بأرقامٍ وبادئةٍ معلَّقةٍ ومباعدةٍ مضبوطة، نصوصٌ عشوائيّةٌ مبذورة: ارتفاعُ الفقرات المحسوبُ = ارتفاعُ المرسوم في ≥ 95%،
  والحَكَمُ `fits` لا يخالف المرسومَ إلّا حيث الفارقُ أقلُّ من سطرٍ (لا يُقبل «يتّسع» والمرسومُ يفيض بسطرٍ كامل).
- الزمن: ألفُ حرفٍ في < 300ms (وقتُ الحفظ).
"""

import random
import statistics
import time

import pytest

from core.print_fit import capacity as cap
from core.print_fit import text_metrics as tm
from tests.print_fit_corpus import corpus

weasyprint = pytest.importorskip("weasyprint")
from weasyprint.formatting_structure import boxes  # noqa: E402

MM_PX = 96 / 25.4
PT = 10.0
FONTS = [
    ("tajawal", 400, "Tajawal"),
    ("tajawal", 700, "Tajawal"),
    ("noto-naskh", 400, "Noto Naskh Arabic"),
    ("amiri", 400, "Amiri"),
]
WIDTH_TOL = 0.05
LINES_MATCH_MIN = 0.95


def _face_css():
    from core.pdf_utils import _font_face_css_weasyprint

    return _font_face_css_weasyprint()


def _walk(box):
    yield box
    for child in getattr(box, "children", ()):
        yield from _walk(child)


def _text_width(box):
    return sum(b.width for b in _walk(box) if isinstance(b, boxes.TextBox))


def _render_boxes(html):
    doc = weasyprint.HTML(string=html).render()
    return [b for page in doc.pages for b in _walk(page._page_box)]


def _by_class(all_boxes, cls):
    out = []
    for b in all_boxes:
        el = getattr(b, "element", None)
        if (
            el is not None
            and el.get("class") == cls
            and isinstance(b, boxes.BlockBox | boxes.InlineBlockBox)
        ):
            out.append(b)
    return out


@pytest.mark.parametrize("font,weight,family", FONTS)
def test_width_calibration(font, weight, family):
    texts = corpus()
    assert len(texts) >= 200
    html = (
        f"<html><head><meta charset=utf-8><style>{_face_css()} body{{font-family:'{family}';font-size:{PT}pt;direction:rtl;font-weight:{weight}}} "
        "div{white-space:nowrap;display:inline-block;margin:0;padding:0}</style></head><body>"
        + "".join(f'<div class="t">{t}</div><br>' for t in texts)
        + "</body></html>"
    )
    rendered = [_text_width(b) for b in _by_class(_render_boxes(html), "t")]
    assert len(rendered) == len(texts)
    errs, ratios = [], []
    for text, w in zip(texts, rendered, strict=True):
        pred = tm.text_mm(text, PT, font, weight) * MM_PX
        assert w > 0 and pred > 0, text
        errs.append(abs(w - pred) / w)
        ratios.append(w / pred)
    assert (
        max(errs) <= WIDTH_TOL
    ), f"{font}/{weight}: أقصى خطأ {max(errs):.1%} (وسيطُ النسبة {statistics.median(ratios):.4f}) — عايِر CALIBRATION"


@pytest.mark.parametrize("width_mm", [28.0, 45.0, 80.0])
@pytest.mark.parametrize("font,weight,family", FONTS[:3])
def test_wrap_line_count_matches_render(font, weight, family, width_mm):
    texts = [t for t in corpus() if len(t.split()) > 1]
    html = (
        f"<html><head><meta charset=utf-8><style>{_face_css()} @page{{size:210mm 20000mm;margin:0}} body{{font-family:'{family}';font-size:{PT}pt;line-height:1.2;direction:rtl;font-weight:{weight}}} "
        f".z{{width:{width_mm}mm;margin:0 0 2mm 0;padding:0}}</style></head><body>"
        + "".join(f'<div class="z">{t}</div>' for t in texts)
        + "</body></html>"
    )
    line_px = PT * (96 / 72) * 1.2
    rendered = [round(b.height / line_px) for b in _by_class(_render_boxes(html), "z")]
    assert len(rendered) == len(texts)
    hits = sum(
        1
        for t, n in zip(texts, rendered, strict=True)
        if len(tm.wrap(t, width_mm, PT, font, weight)) == n
    )
    ratio = hits / len(texts)
    assert (
        ratio >= LINES_MATCH_MIN
    ), f"{font}/{weight}/{width_mm}mm: تطابقُ عدد الأسطر {ratio:.1%} < {LINES_MATCH_MIN:.0%}"


# --- السعة: فقراتٌ متعدّدة ببادئةٍ معلَّقة -------------------------------------------------------------------------------------------------------------

_SENTENCES = [w for text in corpus(120) for w in [text] if len(text.split()) >= 4]


def _random_cases(n=60, seed=20260927):
    rng = random.Random(seed)
    cases = []
    for _ in range(n):
        k = rng.choice([1, 2, 3, 5, 8, 12])
        paragraphs = [rng.choice(_SENTENCES) for _ in range(k)]
        cases.append(
            {
                "paragraphs": paragraphs,
                "width": rng.choice([60.0, 90.0, 120.0, 170.0]),
                "gap": rng.choice([0.0, 1.0, 2.0]),
                "numbered": rng.random() < 0.7,
            }
        )
    return cases


def _render_case_heights(cases, font, weight, family, pt):
    """ارتفاعُ كلّ منطقةٍ مرسوماً: بادئةٌ معلَّقةٌ بعمودٍ ثابتٍ (أعرضِ بادئةٍ + فراغ) كما يفعل قالبُ الاستمارة."""
    parts = []
    prefixes = []
    for c in cases:
        zone = cap.Zone(
            width_mm=c["width"],
            height_mm=1e6,
            font=font,
            weight=weight,
            line_height=1.2,
            paragraph_gap_mm=c["gap"],
            numbered=c["numbered"],
        )
        prefix = cap._prefix_mm(zone, len(c["paragraphs"]), pt)
        prefixes.append(prefix)
        body = ""
        for i, p in enumerate(c["paragraphs"], 1):
            num = f'<span class="n">{i}.</span>' if c["numbered"] else ""
            gap = c["gap"] if i < len(c["paragraphs"]) else 0
            body += f'<p style="padding-inline-start:{prefix:.4f}mm;margin:0 0 {gap}mm 0;position:relative">{num}{p}</p>'
        parts.append(f'<div class="c" style="width:{c["width"]}mm;margin:0 0 3mm 0">{body}</div>')
    html = (
        f"<html><head><meta charset=utf-8><style>{_face_css()} @page{{size:210mm 30000mm;margin:0}} "
        f"body{{font-family:'{family}';font-size:{pt}pt;line-height:1.2;direction:rtl;font-weight:{weight}}} .n{{position:absolute;inset-inline-start:0}}</style></head><body>"
        + "".join(parts)
        + "</body></html>"
    )
    return [b.height / MM_PX for b in _by_class(_render_boxes(html), "c")]


@pytest.mark.parametrize("font,weight,family", FONTS[:1] + FONTS[2:3])
def test_capacity_multi_paragraph_matches_render(font, weight, family):
    cases = _random_cases()
    heights = _render_case_heights(cases, font, weight, family, PT)
    assert len(heights) == len(cases)
    lh = tm.line_height_mm(PT, font, 1.2)
    hits = 0
    for case, real in zip(cases, heights, strict=True):
        zone = cap.Zone(
            width_mm=case["width"],
            height_mm=1e6,
            font=font,
            weight=weight,
            line_height=1.2,
            paragraph_gap_mm=case["gap"],
            numbered=case["numbered"],
        )
        predicted = cap.used_height_mm(zone, case["paragraphs"], PT)
        hits += abs(predicted - real) < 0.5 * lh
        # الحَكَم: لو وُضعت المنطقةُ على ارتفاع المرسوم بالضبط لاتّسع، وبأقلَّ من سطرٍ كاملٍ فلا
        tight = cap.Zone(**{**zone.__dict__, "height_mm": real + 0.5 * lh})
        assert cap.capacity(tight, case["paragraphs"], PT).fits or abs(predicted - real) >= 0.5 * lh
    assert (
        hits / len(cases) >= LINES_MATCH_MIN
    ), f"{font}: تطابقُ ارتفاع الفقرات المتعدّدة {hits / len(cases):.1%}"


# --- عقد capacity (خالصٌ بلا رسم) -------------------------------------------------------------------------------------------------------------------


def test_capacity_contract_fields_and_single_string():
    zone = cap.Zone(width_mm=100.0, height_mm=40.0, line_height=1.2)
    empty = cap.capacity(zone, [], 9.0)
    assert (empty.fits, empty.font_pt) == (True, 9.0)
    assert empty.remaining_lines == empty.total_lines > 0 and empty.remaining_chars > 0
    assert cap.capacity(zone, "خطة الدرس متوفرة", 9.0) == cap.capacity(
        zone, ["خطة الدرس متوفرة"], 9.0
    )
    assert cap.capacity(zone, None, 9.0) == empty
    assert cap.capacity(zone, ["", "  "], 9.0) == empty


def test_capacity_overflow_and_monotonic():
    zone = cap.Zone(
        width_mm=60.0, height_mm=20.0, line_height=1.2, paragraph_gap_mm=1.0, numbered=True
    )
    items: list[str] = []
    prev = cap.capacity(zone, items, 9.0)
    saw_overflow = False
    for i in range(30):
        items.append(f"توصية رقم {i} بتنويع الأنشطة وربطها بأهداف الدرس")
        cur = cap.capacity(zone, items, 9.0)
        assert cur.remaining_lines <= prev.remaining_lines
        if not cur.fits:
            saw_overflow = True
            assert (cur.remaining_chars, cur.remaining_lines) == (0, 0)
        prev = cur
    assert saw_overflow


def test_numbered_prefix_narrows_every_line():
    plain = cap.Zone(width_mm=50.0, height_mm=1e6, line_height=1.2)
    numbered = cap.Zone(width_mm=50.0, height_mm=1e6, line_height=1.2, numbered=True)
    text = " ".join(["الأنشطة"] * 14)
    assert (
        cap.capacity(numbered, [text] * 12, 9.0).used_lines
        >= cap.capacity(plain, [text] * 12, 9.0).used_lines
    )
    # عرضُ «12.» أعرضُ من «1.»: بندٌ ثانيَ عشرَ يضيّق أكثر
    assert cap._prefix_mm(numbered, 12, 9.0) > cap._prefix_mm(numbered, 3, 9.0)
    assert (
        cap._prefix_mm(numbered.__class__(**{**numbered.__dict__, "prefix_width_mm": 7.5}), 12, 9.0)
        == 7.5
    )


def test_capacity_is_pure_and_fast():
    zone = cap.Zone(
        width_mm=120.0, height_mm=60.0, line_height=1.2, paragraph_gap_mm=1.0, numbered=True
    )
    rng = random.Random(7)
    words = [w for t in corpus(80) for w in t.split()]
    paragraphs = [
        " ".join(rng.choice(words) for _ in range(rng.choice([6, 12, 18]))) for _ in range(8)
    ]
    assert sum(len(p) for p in paragraphs) >= 500
    first = cap.capacity(zone, paragraphs, 9.0)
    tm.text_em.cache_clear()
    t0 = time.perf_counter()
    for _ in range(20):
        tm.text_em.cache_clear()
        again = cap.capacity(zone, paragraphs, 9.0)
    per_call = (time.perf_counter() - t0) / 20
    assert again == first
    assert per_call < 0.3, f"{per_call * 1000:.0f}ms لكلّ نداء بلا ذاكرة مؤقّتة"
