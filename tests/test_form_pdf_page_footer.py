"""[IDENTITY] تذييلُ نماذج السلوك PDF في أسفل كلّ صفحةٍ لا بعد آخر المحتوى (أمرُ المالك 2026-09-27).

كان `.doc-footer` عنصراً عاديّاً في التدفّق فيأتي **مرّةً واحدةً** بعد آخر سطرٍ من المحتوى (وسطَ الصفحة الأخيرة)، وتبقى الصفحاتُ قبلها
بلا رؤيةٍ ولا سطرِ مدرسة. صار عنصراً متكرّراً (`position: running(page-footer)`) في صندوق الهامش السفليّ كما في `reports/base_qatar_report.html`.

الشقّ الأوّل نصّيٌّ (يعمل بلا WeasyPrint)؛ والثاني يولّد PDF فعليّاً متعدّد الصفحات ويقيس أنّ الرؤيةَ ظاهرةٌ في أسفل كلّ صفحةٍ ولا تتراكب مع المحتوى.
"""

from __future__ import annotations

import io
import pathlib

import pytest
from django.template import engines

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = ROOT / "templates" / "behavior" / "pdf" / "base_form.html"
#: «دولة قطر» كما يستخرجها pdfplumber — ترتيبٌ بصريٌّ معكوس للعربيّة.
VISUAL_QATAR = "رطق"


def test_the_footer_is_a_running_element_in_the_bottom_margin_box():
    text = BASE.read_text(encoding="utf-8")
    assert "position: running(page-footer)" in text
    assert "@bottom-center { content: element(page-footer)" in text


def test_the_running_footer_is_defined_before_the_content():
    """العنصرُ المتكرّر يسري من الصفحة التي يرد فيها: فإن جاء بعد المحتوى خلت الصفحاتُ السابقةُ منه."""
    text = BASE.read_text(encoding="utf-8")
    assert text.index('class="doc-footer"') < text.index('class="page-wrapper"')
    assert text.index('class="doc-footer"') < text.index("{% block content %}")


@pytest.mark.django_db
def test_every_page_of_a_long_form_carries_the_vision_at_its_bottom(school):
    pdfplumber = pytest.importorskip("pdfplumber")
    from core import pdf_utils

    lines = "".join(f"<p>سطر {i} من المحتوى الطويل لاختبار التذييل</p>" for i in range(160))
    html = (
        engines["django"]
        .from_string(
            "{% extends 'behavior/pdf/base_form.html' %}{% block content %}"
            + lines
            + "{% endblock %}"
        )
        .render({"school": school})
    )
    pdf = pdf_utils._generate_pdf_bytes(html)
    if pdf_utils._WORKING_BACKEND != "weasyprint":
        pytest.skip("القياسُ على WeasyPrint وحدَه — العنصرُ المتكرّر من CSS Paged Media")
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        assert len(doc.pages) >= 3, "لا وثيقةَ متعدّدةُ الصفحات ليُقاس عليها"
        for number, page in enumerate(doc.pages, 1):
            words = page.extract_words()
            footer = [w for w in words if w["top"] > page.height * 0.90]
            assert any(
                VISUAL_QATAR in w["text"] for w in footer
            ), f"لا رؤيةَ في أسفل الصفحة {number}"
            body_bottom = max(w["bottom"] for w in words if w["top"] <= page.height * 0.90)
            assert body_bottom <= min(
                w["top"] for w in footer
            ), f"تراكبَ التذييلُ والمحتوى في الصفحة {number}"
