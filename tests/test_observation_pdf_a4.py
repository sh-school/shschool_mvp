"""[QUALITY] استمارة الزيارة الصفّيّة على A4 — البنيةُ الأصليّةُ مُستعادة (قرارُ المالك 2026-09-28، W-20260928-003).

جرّب المالكُ التصميمَ المؤقّت «صفحةٌ واحدة» (#711: رؤوسُ تقديرٍ أرقامٌ، وتوصيةُ كلّ معيارٍ في قائمةٍ تحت الجدول، ومنطقةُ نصٍّ
حرٍّ تتدرّج) ثمّ رفضه بعد أربع تصييرات PDF فعليّة، وطلب العودةَ إلى بنية النموذج الورقيّ نفسِها: صفحتان بالمجال، ورؤوسُ تقديرٍ
خمسةٌ نصّيّة، وتوصيةٌ عمودٌ داخل صفّ كلّ معيار. فسقط نموذجُ السعة (`quality/pdf_layout.py`) بلا بديل: لا حاجةَ لتدرّج خطٍّ ولا
عدّادٍ حيٍّ — صندوقُ الملاحظات العامّة ثابتُ الحدّ الأدنى فقط، والنصُّ الطويل يمدّد صفَّه (لا قصَّ، قرارُ المالك 2026-09-26).

هذا الملفُّ يحرس البنيةَ المستعادةَ على PDF حقيقيّ (`render_pdf_bytes` بخطّ Noto Naskh المودَع)، وبياناتُه اصطناعيّة.
"""

import io
import re

import pytest

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


def _rate_all(school, obs, recs=(), notes=""):
    """المعايير الـ23 كلُّها مقدَّرةٌ (الحالةُ الفعليّة) والتوصياتُ للأرقام المذكورة [(رقم، نصّ)]، والملاحظاتُ العامّة، والختمان.

    الترقيمُ هنا ترتيبُ المعيار في قاعدة البيانات (1..23) — لا رقمَ في القالب بعد استعادة البنية؛ يُستعمل لاختيار أيّ معيارٍ
    يحمل توصيةً فقط.
    """
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


# ── الورق ─────────────────────────────────────────────────────────────


def test_the_page_is_a4_and_letter_never_returns(source):
    css = source.split("</style>", 1)[0]

    assert re.findall(r"(?<![\w-])size:\s*([^;]+);", css) == ["A4"]
    assert "8.5in" not in css and "11in" not in css


def test_the_real_pdf_is_a4(db, observation):
    pages = _pdf_pages(_html_of(observation))

    for page in pages:
        width, height = (float(v) for v in page.mediabox[2:])
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


# ── البنيةُ المستعادة: صفحتان، رؤوسٌ نصّيّة، توصيةٌ في الصفّ ──────────────────


def test_the_rating_heads_are_five_textual_labels_not_numbers(db, school, named):
    from quality.observation_models import RATING_CHOICES

    html = _html_of(_rate_all(school, named))

    grid_head = html.split('<table class="grid">', 1)[1].split("</tr>", 1)[0]
    for _value, label in RATING_CHOICES:
        assert label in grid_head, label
    assert 'class="legend"' not in html, "لا وسيلةَ إيضاحٍ: الرؤوسُ نصٌّ يُقرأ وحده"
    assert 'class="n"' not in html, "لا دوائرَ أرقامٍ: التصميمُ المؤقّت وحده كان يرقّم"


def test_each_row_carries_its_own_recommendation_column(db, school, named):
    """التوصيةُ عمودٌ في صفّ معياره — لا قائمةٌ مرقَّمةٌ تحت الجدول (استعادةُ البنية)."""
    html = _html_of(
        _rate_all(
            school, named, recs=[(3, "توصيةٌ للمعيار الثالث"), (17, "توصيةٌ للمعيار السابع عشر")]
        )
    )

    assert html.count('<td class="rec">') == 23, "توصيةٌ (فارغةٌ أو لا) لكلّ معيارٍ في صفّه"
    assert '<td class="rec">توصيةٌ للمعيار الثالث</td>' in html
    assert '<td class="rec">توصيةٌ للمعيار السابع عشر</td>' in html
    assert 'class="cn"' not in html, "لا ترقيمَ للمعيار: كان يربطه بقائمةٍ لم تعد موجودة"


def test_the_signatures_are_the_last_row_of_the_last_domain_table(db, school, named):
    """الأصل: التوقيعاتُ صفٌّ أخيرٌ في جدول المجالات الثاني — لا جدولٌ منفصل (خلافَ التصميم المؤقّت)."""
    html = _html_of(_rate_all(school, named))

    assert html.count('class="grid"') == 2, "جدولا معاييرَ — أحدُهما لكلّ صفحة"
    last_grid = html.rsplit('<table class="grid">', 1)[1]
    assert last_grid.count('<td class="sign"') == 2
    assert "توقيعٌ إلكترونيّ داخل المنصّة" in last_grid


# ── الأحجام: لا صغيرَ جدّاً، وقد كبرت بأمر المالك 2026-09-28 ────────────────


def test_the_font_sizes_meet_the_owners_new_minimums(db, observation):
    """متنٌ 13.5pt (بدل 12) وعنوانٌ 16pt (بدل 15) واسمُ مدرسةٍ 15pt (بدل 14) — تكبيرٌ عامّ بأمر المالك 2026-09-28.

    خارجَ الشعارِ والوزارة في الترويسة (8.5pt) وخانةِ الختم (9pt): بياناتٌ آليّةٌ لا نصٌّ يُقرأ. والفحصُ على CSS المُخرَج.
    """
    css = re.sub(r"/\*.*?\*/", "", _html_of(observation).split("</style>", 1)[0], flags=re.S)
    css_no_frame = re.sub(r"\.doc-header[^{]*\{[^}]*\}|\.pdf-footer-line[^{]*\{[^}]*\}", "", css)

    sizes = [float(v) for v in re.findall(r"font-size:\s*([\d.]+)pt", css_no_frame)]
    assert min(sizes) >= 9, sorted(set(sizes))
    assert re.search(r"(?<![\w-])td \{[^}]*font-size: 13.5pt", css), "متنُ الجداول 13.5pt"
    assert re.search(r"\.form-title \{[^}]*font-size: 16pt", css), "عنوانُ الاستمارة 16pt"
    assert re.search(
        r"\.doc-header \.school-name \{[^}]*font-size: 15pt", css
    ), "اسمُ المدرسة في الترويسة 15pt"


# ── النصُّ الحرّ لا يُقصّ ─────────────────────────────────────────────────


def test_nothing_in_the_template_cuts_the_free_text(source):
    css = re.sub(r"/\*.*?\*/", "", source.split("</style>", 1)[0], flags=re.S)

    assert "line-clamp" not in css and "max-height" not in css and "overflow: hidden" not in css
    assert "truncatechars" not in source and "truncatewords" not in source


def test_a_long_recommendation_and_long_notes_are_printed_in_full(db, school, named):
    """رمزا الرأس والذيل لاتينيّان ليُقرآ من نصّ PDF بلا التباسِ اتّجاه العربيّة."""
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


def test_notes_longer_than_the_box_grow_the_row_onto_a_further_page(db, school, named):
    """ملاحظاتٌ عامّةٌ طويلةٌ جدّاً لا تُقصّ: الصفُّ يمتدّ ويُتِمّ نفسَه في صفحةٍ ثالثة عند الحاجة."""
    html = _html_of(_rate_all(school, named, notes=f"HEADNOTE {TEXT} TAILNOTE"))

    pages = len(_pdf_pages(html))
    assert pages >= 2
    text = _pdf_text(html)
    assert "HEADNOTE" in text and "TAILNOTE" in text


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
    """الرؤيةُ في **أسفل** كلّ صفحةٍ (داخل هامشها السفليّ 0.42in ≈ 30pt فوق حافّة الورق) لا في المتن ولا في الترويسة."""
    school.vision = "VISIONTOKEN رؤيةٌ اختباريّة"
    school.save(update_fields=["vision"])

    boxes = _vision_boxes(_html_of(_rate_all(school, named)), "VISIONTOKEN")
    assert len(boxes) >= 2, "البنيةُ صفحتان على الأقلّ — الرؤيةُ تتكرّر في تذييل كلٍّ منهما"
    assert all(top < 30 for _page, top in boxes), boxes
