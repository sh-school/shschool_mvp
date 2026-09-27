"""[QUALITY] استمارة الزيارة الصفّيّة على A4 بصفحةٍ واحدة، بمتنٍ 12pt ونصوصٍ حرّةٍ 11pt، **بلا قصّ** (قرارُ المالك 2026-09-26).

رفض المالكُ قصَّ النصّ الحرّ في المطبوع وقال إنّ 9.5 و8pt صغيرٌ جدّاً. فالتصميمُ: رؤوسُ التقدير أرقامٌ 1–5 بوسيلة إيضاحٍ (فيتّسع عمودُ
المعايير سطراً لكلّ معيار)، وتوصيةُ كلّ معيارٍ قائمةٌ مرقَّمةٌ في منطقة النصوص الحرّة، والتوقيعاتُ جدولٌ منفصل. وخطُّ المنطقة يتدرّج من 11pt
بنصف نقطةٍ إلى 10pt (`quality/pdf_layout.py::free_font`) — وما فوق السعة يُطبع كلُّه ويتمّ في صفحةٍ ثانية لا يُقصّ.

ونموذجُ السعة في `pdf_layout` **أوّليٌّ مؤقّت** إلى أن تحلّ محلَّه دالّةُ `capacity` في المحرّك المركزيّ. فهذا الملفُّ يحرسه على PDF حقيقيّ:
النموذجُ محافظٌ (لا يُقدّر أقلَّ من الارتفاع الفعليّ)، وما يسعه النموذجُ تسعه الصفحةُ وتحته فسحةُ أمان. والقياسُ بمسار الإنتاج نفسِه
(`render_pdf_bytes` بخطّ Noto Naskh المودَع)، وبياناتُه اصطناعيّة.
"""

import io
import re

import pytest

from quality import pdf_layout
from tests.test_observation_pdf_form import (  # noqa: F401 — أجهزةُ الاستمارة نفسُها
    _acknowledged,
    _html_of,
    _real_criteria,
    criteria,
    named,
    observation,
    source,
)

pytestmark = pytest.mark.django_db

#: A4 بالنقطة (210×297 مم)
A4_PT = (595.28, 841.89)
#: فسحةُ الأمان الدنيا تحت أيّ محتوًى ضمن السعة (النموذجُ نفسُه يحجز `SAFETY_PT` وهي أكبر)
MIN_ROOM_PT = 15

#: نصٌّ عربيّ طويل بلا رموزٍ لاتينيّة (يُقطَع لبلوغ الطول المطلوب)
FILLER = "توصيةٌ تفصيليّةٌ طويلةٌ تشرح المطلوبَ من المعلّم لتحسين الممارسة الصفّيّة وربطها بأهداف التعلّم "
TEXT = FILLER * 60


def _pdf_pages(html):
    from core.pdf_utils import render_pdf_bytes

    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("weasyprint")
    return pypdf.PdfReader(io.BytesIO(render_pdf_bytes(html))).pages


def _pdf_text(html):
    """نصُّ PDF كلِّه بـpdfium: يقرأ العربيّةَ المشكَّلة سليمةً، بخلاف `pypdf` الذي يُسقط حروفاً منها ويُضيع رموزاً لاتينيّةً في آخر السطر."""
    from core.pdf_utils import render_pdf_bytes

    pdfium = pytest.importorskip("pypdfium2")
    pytest.importorskip("weasyprint")
    document = pdfium.PdfDocument(render_pdf_bytes(html))
    return " ".join(page.get_textpage().get_text_range() for page in document)


def _room(html, margin_pt):
    """عددُ الصفحات حين نُضيف `margin_pt` نقطةً تحت التوقيعات — 1 يعني أنّ تحتها فسحةً بهذا القدر على الأقلّ."""
    probe = html.replace("</body>", f'<div style="height:{margin_pt}pt"></div></body>', 1)
    return len(_pdf_pages(probe))


def _body_height(html):
    """ارتفاعُ متن الاستمارة كلِّه (pt) بلا قسمة صفحات: صفحةٌ طويلةٌ جدّاً ثمّ ارتفاعُ `<body>` من تخطيط WeasyPrint نفسِه."""
    weasyprint = pytest.importorskip("weasyprint")
    from core.pdf_utils import _inject_fonts

    tall = html.replace("size: A4;", "size: 210mm 4000pt;")
    page = weasyprint.HTML(string=_inject_fonts(tall)).render().pages[0]._page_box
    found = []

    def walk(box):
        element = getattr(box, "element", None)
        if element is not None and element.tag == "body" and not found:
            found.append(box.margin_height() * 0.75)
        for child in getattr(box, "children", ()):
            walk(child)

    walk(page)
    return found[0]


def _resize_zone(html, font=None, min_height=None):
    """يبدّل حجمَ خطّ منطقة النصوص وأدنى ارتفاعها في CSS المُخرَج (قاعدةُ `.zone`) — لقياس التخطيط الطبيعيّ عند خطٍّ معيَّن."""
    rule = re.search(r"\.zone \{[^}]*\}", html)
    assert rule, "قاعدةُ .zone"
    text = rule.group(0)
    if font is not None:
        text = re.sub(r"font-size: [\d.]+pt", f"font-size: {font}pt", text)
    if min_height is not None:
        text = re.sub(r"min-height: [\d.]+pt", f"min-height: {min_height}pt", text)
    return html.replace(rule.group(0), text, 1)


def _rate_all(school, obs, recs=(), notes=""):
    """المعايير الـ23 كلُّها مقدَّرةٌ (الحالةُ الفعليّة) والتوصياتُ للأرقام المذكورة [(رقم، نصّ)]، والملاحظاتُ العامّة، والختمان."""
    from quality.observation_models import ObservationCriterion, ObservationScore

    _real_criteria(school, 23)
    ObservationScore.objects.filter(observation=obs).delete()
    by_number = dict(recs)
    for number, criterion in enumerate(ObservationCriterion.objects.filter(school=school), start=1):
        ObservationScore.objects.create(
            observation=obs,
            criterion=criterion,
            rating="some",
            recommendation=by_number.get(number, ""),
        )
    obs.general_notes = notes
    obs.save()
    return _acknowledged(obs)


def _model_args(recs, notes):
    return [{"number": n, "text": t} for n, t in recs], notes


# ── الورق ─────────────────────────────────────────────────────────────


def test_the_page_is_a4_and_letter_never_returns(source):
    css = source.split("</style>", 1)[0]

    assert re.findall(r"(?<![\w-])size:\s*([^;]+);", css) == ["A4"]
    assert "8.5in" not in css and "11in" not in css


def test_the_real_pdf_is_a4(db, observation):
    pages = _pdf_pages(_html_of(observation))

    width, height = (float(v) for v in pages[0].mediabox[2:])
    assert (round(width, 1), round(height, 1)) == (round(A4_PT[0], 1), round(A4_PT[1], 1))


def test_the_header_and_footer_strips_take_the_a4_printable_width(source):
    """عرضُ الشريطين مطلقٌ (صندوقُ الهامش بلا عرض): عرضُ A4 ناقصَ الهامشين الجانبيّين — لا 7.5 بوصة Letter."""
    side_in = float(
        re.search(r"margin: [\d.]+(?:in|mm) ([\d.]+)in [\d.]+in [\d.]+in", source).group(1)
    )
    printable_mm = 210 - 2 * side_in * 25.4

    for strip in ("sheet-header", "sheet-footer"):
        width = float(re.search(rf"#{strip} \{{[^}}]*width: ([\d.]+)mm", source).group(1))
        assert printable_mm - 0.5 <= width <= printable_mm, (strip, width, printable_mm)
    assert "width: 7.5in" not in source


# ── التصميم: أرقامٌ بوسيلة إيضاح، وقائمةُ توصيات، وتوقيعاتٌ منفصلة ────────────────


def test_the_rating_heads_are_numbers_with_one_legend(db, school, named):
    from quality.observation_models import RATING_CHOICES

    html = _html_of(_rate_all(school, named))
    legend = html.split('<div class="legend">', 1)[1].split("</div>", 1)[0]

    for number, (_value, label) in enumerate(RATING_CHOICES, start=1):
        assert f'<span class="n">{number}</span> {label}' in legend
    grid_head = html.split('<table class="grid">', 1)[1].split("</tr>", 1)[0]
    assert grid_head.count('class="n"') == len(RATING_CHOICES)
    assert "c-rec" not in html, "لا عمودَ توصيات في الجدول: صارت قائمةً تحته"


def test_each_criterion_is_numbered_and_its_recommendation_is_listed_under_that_number(
    db, school, named
):
    html = _html_of(
        _rate_all(
            school, named, recs=[(3, "توصيةٌ للمعيار الثالث"), (17, "توصيةٌ للمعيار السابع عشر")]
        )
    )

    assert html.count('<td class="crit"><span class="cn">') == 23
    zone = html.split('<div class="zone"', 1)[1]
    assert '<li><span class="cn">3</span> توصيةٌ للمعيار الثالث</li>' in zone
    assert '<li><span class="cn">17</span> توصيةٌ للمعيار السابع عشر</li>' in zone
    assert zone.count("<li>") == 2, "المعايير بلا توصيةٍ لا تُدرَج"


def test_the_signatures_are_a_separate_four_cell_table(db, school, named):
    html = _html_of(_rate_all(school, named))

    signs = html.split('<table class="signs">', 1)[1].split("</table>", 1)[0]
    assert signs.count("<td") == 4
    assert html.index('<div class="zone"') < html.index('<table class="signs">')
    assert "توقيعٌ إلكترونيّ داخل المنصّة" in signs


# ── الأحجام: لا صغيرَ جدّاً ─────────────────────────────────────────────


def test_the_font_sizes_meet_the_owners_minimums(db, observation):
    """متنٌ 12pt وأدنى ما فيه 10pt (رؤوسٌ ووسيلةُ إيضاح)، والنصوصُ الحرّةُ 11 إلى حدٍّ أدنى 10 — قال المالكُ إنّ 9.5 و8 صغيرٌ جدّاً.

    خارجَ الإطار المؤقّت (الترويسةُ والتذييل يملكهما المكوّنان المركزيّان). وخانةُ الختم 9pt لأنّها بيانٌ آليٌّ لا نصٌّ يُقرأ.
    والفحصُ على CSS المُخرَج (بعد حلّ وسوم الألوان).
    """
    css = re.sub(r"/\*.*?\*/", "", _html_of(observation).split("</style>", 1)[0], flags=re.S)
    css = re.sub(r"\.doc-header[^{]*\{[^}]*\}|\.running-footer[^{]*\{[^}]*\}", "", css)

    sizes = [float(v) for v in re.findall(r"font-size:\s*([\d.]+)pt", css)]
    assert min(sizes) >= 9, sorted(set(sizes))
    assert re.search(r"(?<![\w-])td \{[^}]*font-size: 12pt", css), "متنُ الجداول 12pt"
    assert pdf_layout.IDEAL_PT == 11.0 and pdf_layout.MIN_PT == 10.0 and pdf_layout.STEP_PT == 0.5


# ── النصُّ الحرّ لا يُقصّ ─────────────────────────────────────────────────


def test_nothing_in_the_template_cuts_the_free_text(source):
    css = re.sub(r"/\*.*?\*/", "", source.split("</style>", 1)[0], flags=re.S)

    assert "line-clamp" not in css and "max-height" not in css and "overflow: hidden" not in css
    assert "truncatechars" not in source and "truncatewords" not in source


def test_a_long_recommendation_and_long_notes_are_printed_in_full(db, school, named):
    """رمزا الرأس والذيل لاتينيّان ليُقرآ من نصّ PDF بلا التباسِ اتّجاه العربيّة — والذيلُ في نهاية نصٍّ يزيد عن أسطر."""
    html = _html_of(
        _rate_all(
            school,
            named,
            recs=[(5, f"HEADREC {TEXT[:150]} TAILREC")],
            notes=f"HEADNOTE {TEXT[:500]} TAILNOTE",
        )
    )

    text = _pdf_text(html)
    for token in ("HEADREC", "TAILREC", "HEADNOTE", "TAILNOTE"):
        assert token in text, token


# ── الرؤيةُ في تذييل كلّ صفحة (أمرُ المالك 2026-09-27) ────────────────────────


def _vision_boxes(html, token):
    """(رقمُ الصفحة، حافّةُ النصّ العلويّةُ بالنقطة من أسفل الورقة) لكلّ ظهورٍ للرمز في PDF الحقيقيّ — من pdfium."""
    from core.pdf_utils import render_pdf_bytes

    pdfium = pytest.importorskip("pypdfium2")
    pytest.importorskip("weasyprint")
    found = []
    for number, page in enumerate(pdfium.PdfDocument(render_pdf_bytes(html)), start=1):
        textpage = page.get_textpage()
        searcher = textpage.search(token)
        while (hit := searcher.get_next()) is not None:
            _left, _bottom, _right, top = textpage.get_charbox(hit[0])
            found.append((number, top))
    return found


def test_the_vision_is_in_the_footer_line_on_every_page_below_the_body(db, school, named):
    """الرؤيةُ في **أسفل** كلّ صفحةٍ (داخل هامشها السفليّ 0.42in ≈ 30pt فوق حافّة الورق) لا في المتن ولا في الترويسة — صفحةٌ واحدةٌ وأخرى بصفحتين."""
    school.vision = "VISIONTOKEN رؤيةٌ اختباريّة"
    school.save(update_fields=["vision"])

    one = _vision_boxes(_html_of(_rate_all(school, named)), "VISIONTOKEN")
    assert [page for page, _top in one] == [1]
    assert all(top < 30 for _page, top in one), one


def test_the_vision_repeats_on_the_continuation_page(db, school, named):
    school.vision = "VISIONTOKEN رؤيةٌ اختباريّة"
    school.save(update_fields=["vision"])
    recs = [(n, TEXT[:100]) for n in range(1, 24)]

    two = _vision_boxes(
        _html_of(_rate_all(school, named, recs=recs, notes=TEXT[:600])), "VISIONTOKEN"
    )

    assert [page for page, _top in two] == [1, 2]
    assert all(top < 30 for _page, top in two), two


# ── السعةُ والصفحةُ الواحدة ───────────────────────────────────────────────


def test_a_blank_form_is_one_a4_page_that_fills_it(db, school, named):
    """الاستمارةُ الفارغةُ (المعايير كلُّها مقدَّرة، الختمان، لا نصوص) صفحةٌ واحدة، ومنطقةُ النصوص تملأ الصفحةَ (`min-height`) إلى فسحة الأمان:
    فلا بياضَ فوقها يزيد كثيراً (ولو ضاع أثرُ `zone_min_pt` عاد البياضُ ~100pt)."""
    html = _html_of(_rate_all(school, named))

    assert len(_pdf_pages(html)) == 1
    assert _room(html, MIN_ROOM_PT) == 1, f"أقلُّ من {MIN_ROOM_PT} نقطةً فسحةً تحت الاستمارة الفارغة"
    assert (
        _room(html, pdf_layout.SAFETY_PT + 20) == 2
    ), "بياضٌ زائدٌ تحت التوقيعات: أعِد ضبطَ `zone_min_pt`"


def test_the_measured_blank_height_matches_the_model(db, school, named):
    """`BLANK_BODY_PT` مقيسٌ لا مخمَّن: يحرسه هنا — انحرافُه (ترويسةٌ أطول، خطٌّ آخر) يُوجب إعادةَ معايرة النموذج والقالب."""
    html = _html_of(_rate_all(school, named))
    natural = _resize_zone(html, min_height="0")

    assert abs(_body_height(natural) - pdf_layout.BLANK_BODY_PT) < 3.0


@pytest.mark.parametrize(
    ("recs", "notes"),
    [
        ([], TEXT[:300]),
        ([], TEXT[:800]),
        ([(n, TEXT[:80]) for n in (2, 7, 11, 15, 20)], ""),
        ([(n, TEXT[:100]) for n in range(1, 11)], TEXT[:200]),
    ],
    ids=["notes-300", "notes-800", "recs-5x80", "recs-10x100+notes-200"],
)
def test_the_model_never_underestimates_the_real_layout(db, school, named, recs, notes):
    """النموذجُ محافظ: ما تزيده النصوصُ على الجسم الفارغ ≤ تقديرُه عند كلّ خطٍّ في التدرّج — فما يسعه يسعه الفعليُّ."""
    html = _html_of(_rate_all(school, named, recs=recs, notes=notes))
    model_recs, model_notes = _model_args(recs, notes)
    for pt in pdf_layout.font_steps():
        sized = _resize_zone(html, font=f"{pt:g}", min_height="0")
        real_extra = _body_height(sized) - pdf_layout.BLANK_BODY_PT
        assert pdf_layout.extra_height(model_recs, model_notes, pt) >= real_extra - 0.5, (
            pt,
            real_extra,
        )


def test_content_at_the_capacity_is_one_page_with_room(db, school, named):
    """القبول: نصٌّ يملأ السعةَ (ما يقرؤه العدّادُ بأدنى خطٍّ يكاد ينفد) صفحةٌ واحدة وتحتها فسحة — بخطٍّ من التدرّج لا بقصّ."""
    recs = [(n, TEXT[:90]) for n in (2, 5, 9, 13)]
    model_recs, _ = _model_args(recs, "")
    left = pdf_layout.remaining_chars(model_recs, "")
    assert left > 200, "بعد أربع توصياتٍ يبقى للملاحظات سعةٌ يُبنى عليها الاختبار"
    notes = f"HEADNOTE {TEXT[: left - 40]} TAILNOTE"
    assert pdf_layout.fits(model_recs, notes)

    html = _html_of(_rate_all(school, named, recs=recs, notes=notes))

    assert len(_pdf_pages(html)) == 1
    assert _room(html, MIN_ROOM_PT) == 1
    assert "TAILNOTE" in _pdf_text(html), "الملاحظاتُ مطبوعةٌ كلُّها: لا قصّ"


def test_above_the_capacity_the_text_continues_on_a_second_page_and_nothing_is_lost(
    db, school, named
):
    """بياناتٌ قديمةٌ فوق السعة: أدنى خطٍّ ثمّ صفحةٌ ثانية — لا قصٌّ ولا صفحةٌ ثالثة."""
    recs = [(n, f"REC{n:02d} {TEXT[:150]} END{n:02d}") for n in range(1, 24)]
    notes = f"NOTES {TEXT[:900]} NOTESEND"
    model_recs, _ = _model_args(recs, notes)
    assert not pdf_layout.fits(model_recs, notes)
    assert pdf_layout.free_font(model_recs, notes) == pdf_layout.MIN_PT

    html = _html_of(_rate_all(school, named, recs=recs, notes=notes))

    assert len(_pdf_pages(html)) == 2
    text = _pdf_text(html)
    for token in ("REC01", "END01", "REC23", "END23", "NOTES", "NOTESEND"):
        assert token in text, token


# ── نموذجُ السعة (نقيّ) ───────────────────────────────────────────────────


def test_the_free_font_steps_down_by_half_points_to_the_minimum():
    sizes = [pdf_layout.free_font([], TEXT[:chars]) for chars in range(0, 3000, 20)]

    assert sizes[0] == 11.0 and sizes[-1] == pdf_layout.MIN_PT
    assert sizes == sorted(sizes, reverse=True), "لا يكبر الخطُّ بزيادة النصّ"
    assert set(sizes) <= {11.0, 10.5, 10.0}
    assert 10.5 in sizes, "تدرّجٌ بنصف نقطةٍ لا قفزةٌ من 11 إلى 10"


def test_the_remaining_chars_counter_crosses_zero_where_the_text_stops_fitting():
    fitting = 0
    for chars in range(0, 4000, 25):
        left = pdf_layout.remaining_chars([], TEXT[:chars])
        if pdf_layout.fits([], TEXT[:chars]):
            assert left >= 0, chars
            fitting = chars
        else:
            assert left < 0, chars
    assert 1000 <= fitting <= 2000, fitting


def test_the_font_is_a_string_so_the_decimal_separator_never_localises():
    assert pdf_layout.format_pt(11.0) == "11" and pdf_layout.format_pt(10.5) == "10.5"
