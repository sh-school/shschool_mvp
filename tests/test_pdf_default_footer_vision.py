"""[BRAND] رؤيةُ الوزارة في تذييل الصفحات التي لا تملك ترويستَها الخاصّة (قرارُ المالك 2026-09-27).

`core.pdf_utils._inject_wp_page_header_css` هو الإطارُ الافتراضيّ لأيّ قالب PDF لا يُعرِّف `doc-header` أو `data-pdf-own-page`
(قائمةُ الطلاب، تقاريرٌ متفرّقة…) — القوالبُ التي تملك ترويستَها (`STANDALONE_DOCS` في `tests/test_ministry_vision_footer.py`)
تحمل الرؤيةَ بالفعل عبر الجزئيّة المضمَّنة، فهذا الملفُّ يغطّي المسار الآخر وحدَه.

**الرؤيةُ سطرٌ واحدٌ دائماً لا سطران** (قرارُ المالك 2026-09-27، قاعدةٌ عامّةٌ لكلّ مخرَج) — تندمج مع عدّاد الصفحة في السطر نفسِه
(`عدّاد — رؤية`) بخطٍّ أصغر، لا بفاصل سطرٍ/`white-space: pre-line`. بلا لمس «SchoolOS v6» ولا التاريخ (طلبُ المايسترو).
"""

import pytest
from django.template.loader import render_to_string

from core.ministry_vision import ministry_vision_text
from core.pdf_utils import _inject_wp_page_header_css

weasyprint = pytest.importorskip("weasyprint")
from weasyprint.formatting_structure import boxes  # noqa: E402

VISION = "مُتَعَلِّمٌ رِيَادِيٌّ لِتَنْمِيَةٍ مُسْتَدَامَةٍ"
BASE_HTML = (
    "<html><head><meta charset='utf-8'><style></style></head><body><p>محتوى</p></body></html>"
)


def _footer_words(paper_size="A4"):
    """[(y, text)] لكلّ نصٍّ داخل صناديق هامش الصفحة (الترويسة والتذييل) بعد الحقن."""
    injected = _inject_wp_page_header_css(BASE_HTML, "مدرسة تجريبية", "عنوان تجريبيّ", paper_size)
    doc = weasyprint.HTML(string=injected).render()

    def walk(box, out, in_margin=False):
        if type(box).__name__ == "MarginBox":
            in_margin = True
        if isinstance(box, boxes.TextBox) and in_margin:
            out.append((round(box.position_y), box.text))
        for child in getattr(box, "children", ()):
            walk(child, out, in_margin)

    out = []
    walk(doc.pages[0]._page_box, out)
    return sorted(out)


def test_the_vision_text_matches_the_single_source_partial():
    import re

    assert ministry_vision_text() == VISION
    plain = re.sub(r"<[^>]+>", "", render_to_string("components/ministry_vision.html")).strip()
    assert VISION == plain


@pytest.mark.parametrize("paper_size", ["A4", "A3"])
def test_the_footer_carries_the_vision_merged_into_the_page_counters_single_line(paper_size):
    """الرؤيةُ لا تُثنّى سطرين — تندمج مع عدّاد الصفحة في نصٍّ واحدٍ بارتفاعٍ (سطرٍ) واحد."""
    words = _footer_words(paper_size)
    merged = [t for _y, t in words if VISION in t]
    assert len(merged) == 1, words
    assert (
        merged[0].count(" / ") == 1 and VISION in merged[0]
    ), "عدّادُ الصفحة والرؤيةُ في النصّ نفسِه — لا مربّعين منفصلين"


def test_samm_and_the_date_are_untouched():
    """لا لمسَ لـ«SchoolOS v6» ولا للتاريخ — أمرُ المايسترو الصريح؛ يبقيان كما كانا."""
    words = [t for _y, t in _footer_words()]
    assert "SchoolOS v6" in words
    assert any(t.count("/") == 2 for t in words), "تاريخُ اليوم (يوم/شهر/سنة) ما زال في مكانه"


def test_a_page_that_owns_its_header_is_left_alone():
    """قالبٌ فيه `doc-header` (ترويستُه الخاصّة) لا يمسّه هذا الإطارُ — لا رؤيةَ مضاعفة."""
    owned = "<html><body><div class='doc-header'>ترويسةٌ خاصّة</div></body></html>"
    assert _inject_wp_page_header_css(owned, "م", "ع") == owned


@pytest.mark.django_db
def test_the_real_student_list_pdf_carries_the_vision_in_its_footer(
    school, principal_user, seeded_calendar
):
    from core.academic_calendar import academic_year_for_school
    from core.export_utils import get_export_context_for
    from student_affairs.selectors import student_register

    year = academic_year_for_school(school)
    ctx = get_export_context_for(principal_user, "سجل الطلاب")
    from django.http import QueryDict

    students, enrollment_data = student_register(school, year, QueryDict())
    html = render_to_string(
        "student_affairs/student_list_pdf.html",
        {"rows": [], "total_students": 0, "for_pdf": True, **ctx},
    )
    injected = _inject_wp_page_header_css(html, ctx["school_name"], "سجل الطلاب", "A4")
    doc = weasyprint.HTML(string=injected).render()

    def walk(box, out, in_margin=False):
        if type(box).__name__ == "MarginBox":
            in_margin = True
        if isinstance(box, boxes.TextBox) and in_margin:
            out.append(box.text)
        for child in getattr(box, "children", ()):
            walk(child, out, in_margin)

    texts = []
    for page in doc.pages:
        walk(page._page_box, texts)
    assert VISION in texts
