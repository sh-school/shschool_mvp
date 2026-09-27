"""[PRINT] الإطارُ المطبوع المركزيّ يُقاس **مرسوماً** بتخطيط WeasyPrint: تذييلٌ صفٌّ واحد، وترويسةٌ وتذييلٌ ضمن ثوابتهما، وخطٌّ ≥ حدّه.

الاختبارُ النصّيُّ (`test_print_frame_guard.py`) يقيس المُعلَن؛ وهذا يقيس ما يخرج على الورق — ما تقرؤه الملاءمةُ (`body_height`) يصحّ فقط إن كان
المرسومُ ≤ الثوابت. وثلاثُ صفحاتٍ لكلّ اختبار: عدّادُ «ص/ص» يُحسب لكلّ صفحة، وصفٌّ واحدٌ في كلّ منها.
"""

import pathlib
from types import SimpleNamespace

import pytest
from django.template import engines

from core import print_frame as pf

weasyprint = pytest.importorskip("weasyprint")
from weasyprint.formatting_structure import boxes  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MM_PX = 96 / 25.4
PT_PX = 96 / 72

SCHOOL_NAME = "م" * 40
DOC = """{% load print_frame %}<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
{% print_frame_css paper orient %}
<style>{{ fonts|safe }} body { font-family: 'Tajawal', sans-serif; direction: rtl; } p { font-size: 11pt; margin: 0 0 6mm; }</style></head><body>
{% print_frame_header paper orient school "الجدول العام" "العام الدراسي 2026-2027" True %}
{% print_frame_footer paper orient school %}
<p>الصفحة الأولى</p><p style="break-before: page">الصفحة الثانية</p><p style="break-before: page">الصفحة الثالثة</p>
</body></html>"""


def _render(paper, orient, school_name=SCHOOL_NAME):
    from core.pdf_utils import _font_face_css_weasyprint

    school = SimpleNamespace(name=school_name, phone="", email="", city="الشحانية", vision="")
    html = (
        engines["django"]
        .from_string(DOC)
        .render(
            {
                "paper": paper,
                "orient": orient,
                "school": school,
                "fonts": _font_face_css_weasyprint(),
            }
        )
    )
    return html, weasyprint.HTML(string=html, base_url=str(ROOT)).render()


def _margin_box(page, keyword):
    found = []

    def walk(box):
        if type(box).__name__ == "MarginBox" and box.at_keyword == keyword:
            found.append(box)
        for child in getattr(box, "children", ()):
            walk(child)

    walk(page._page_box)
    return found[0] if found else None


def _texts(box):
    out = []

    def walk(b):
        if isinstance(b, boxes.TextBox):
            out.append(b)
        for child in getattr(b, "children", ()):
            walk(child)

    walk(box)
    return out


CASES = [("a4", "portrait"), ("a4", "landscape"), ("a3", "landscape")]


@pytest.mark.parametrize(("paper", "orient"), CASES)
def test_the_frame_is_drawn_within_its_constants_on_every_page(paper, orient):
    fr = pf.frame(paper, orient)
    html, doc = _render(paper, orient)
    assert len(doc.pages) == 3
    for page in doc.pages:
        top, bottom = _margin_box(page, "@top-center"), _margin_box(page, "@bottom-center")
        # الترويسةُ تبدأ بحشوٍ علويٍّ (هامشُ الصفحة − 2 ملم) يقع داخل الهامش العلويّ لا في header_h.
        header_h = sum(c.margin_height() for c in top.children) - (fr.margin_top - 2) * MM_PX
        footer_h = sum(c.margin_height() for c in bottom.children)
        assert header_h <= fr.header_h * MM_PX + 1, (
            paper,
            orient,
            "الترويسةُ أطولُ من header_h",
            header_h / MM_PX,
        )
        assert footer_h <= fr.footer_h * MM_PX + 1, (
            paper,
            orient,
            "التذييلُ أطولُ من footer_h",
            footer_h / MM_PX,
        )


@pytest.mark.parametrize(("paper", "orient"), CASES)
def test_the_footer_is_one_row_with_the_page_counter_per_page(paper, orient):
    _html, doc = _render(paper, orient)
    for number, page in enumerate(doc.pages, start=1):
        words = _texts(_margin_box(page, "@bottom-center"))
        tops = {round(w.position_y) for w in words}
        assert len(tops) == 1, (paper, orient, "التذييلُ يتوزّع على أكثر من سطر", tops)
        text = " ".join(w.text for w in words)
        assert f"{number} / 3" in text or f"3 / {number}" in text, (paper, orient, text)


@pytest.mark.parametrize(("paper", "orient"), CASES)
def test_the_drawn_font_never_drops_below_the_frames_minimums(paper, orient):
    """التذييلُ ≥ 9pt (حدُّه الصارم؛ المثاليّ 10) والترويسةُ ≥ 9pt."""
    _html, doc = _render(paper, orient)
    page = doc.pages[0]
    footer_min = min(
        w.style["font_size"] / PT_PX for w in _texts(_margin_box(page, "@bottom-center"))
    )
    header_min = min(w.style["font_size"] / PT_PX for w in _texts(_margin_box(page, "@top-center")))
    assert footer_min >= pf.FOOTER_MIN_PT - 0.05, footer_min
    assert header_min >= 9 - 0.05, header_min


def test_the_vision_is_a_header_line_on_portrait_and_a_footer_item_elsewhere():
    """D1: على A4 العموديّ سطرٌ في الترويسة بخطّ 10pt والتذييلُ بلا رؤية؛ وأفقيّاً وعلى A3 تبقى في التذييل."""
    portrait_html, _ = _render("a4", "portrait")
    landscape_html, _ = _render("a4", "landscape")
    assert 'class="pf-vision"' in portrait_html
    footer = portrait_html.split('id="print-footer"', 1)[1]
    assert "pf-item-vision" not in footer.split("</div>", 1)[0]
    assert 'class="pf-vision"' not in landscape_html
    assert "pf-item-vision" in landscape_html.split('id="print-footer"', 1)[1]


def test_a_school_name_too_long_for_the_row_is_flagged_not_cut():
    """الملزِمُ الذي لا يسع (اسمُ مدرسةٍ بمئتي حرف) يُعلَّم `data-overflow` ليقرّر المستهلكُ — لا قصَّ صامتاً."""
    html, _ = _render("a4", "portrait", school_name="م" * 200)
    assert 'data-overflow="1"' in html
    ok_html, _ = _render("a4", "portrait")
    assert "data-overflow" not in ok_html


STATS_DOC = DOC.replace(
    "{% print_frame_footer paper orient school %}",
    '{% print_frame_footer paper orient school stats="المعلّمون: 72 · الشُّعب: 25" %}',
)


def test_stats_is_drawn_in_the_footer_row_when_the_consumer_passes_it():
    """طلبُ «جدول · التشغيل» (2026-09-27): إحصاءٌ حرٌّ يُرسم فعلاً في صفّ التذييل — لا يسقط ولا يُثنّى سطراً."""
    from core.pdf_utils import _font_face_css_weasyprint

    school = SimpleNamespace(name=SCHOOL_NAME, phone="", email="", city="الشحانية", vision="")
    html = (
        engines["django"]
        .from_string(STATS_DOC)
        .render(
            {
                "paper": "a3",
                "orient": "landscape",
                "school": school,
                "fonts": _font_face_css_weasyprint(),
            }
        )
    )
    doc = weasyprint.HTML(string=html, base_url=str(ROOT)).render()
    footer = _margin_box(doc.pages[0], "@bottom-center")
    words = _texts(footer)
    joined = "".join(w.text for w in words)
    assert "المعلّمون: 72" in joined and "الشُّعب: 25" in joined
    assert len({round(w.position_y) for w in words}) == 1, "صفٌّ واحدٌ — لا سطرَ ثانٍ للإحصاء"
