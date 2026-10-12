"""شعارُ المدرسة «ش» في إطار الطباعة المركزيّ وورقتَي المعلّم والشعبة (W-20261012-012 المرحلة الثانية، قرار المالك D-404م).

الشعارُ في سطر المدرسة نفسِه من ترويسة الإطار، ضلعُه أقلُّ من ارتفاع ذلك السطر، فلا يزيد الترويسةَ ولا يدفع جدولَ الورقة:
حارسا «صفحةٌ واحدةٌ لأسوأ ورقة» و«الفراغُ تحت الترويسة < 12pt» في `test_weekly_teacher_sheet_fit.py` يبقيان أخضرَين بالشعار.
هنا: حضورُه في القالب، وفي كلّ صفحةٍ من PDF حقيقيّ (صورةٌ واحدةٌ هي الشعار)، وخطُّ Tajawal بلا DejaVu مقيساً على الملفّ.
"""

from __future__ import annotations

import io
import re

import pypdf
import pytest
from django.template import Context, Template

from tests.test_schedule_pages_parity import arts  # noqa: F401
from tests.test_weekly_teacher_sheet_fit import (  # noqa: F401
    _fonts,
    _pages,
    busiest_class,
    busiest_teacher,
)

pytestmark = pytest.mark.django_db


class _School:
    name = "مدرسةٌ تجريبيّة"
    vision = ""


@pytest.mark.parametrize("orient", ["portrait", "landscape"])
@pytest.mark.parametrize("paper", ["a4", "a3"])
def test_the_frame_header_puts_the_logo_before_the_school_name_in_the_same_line(paper, orient):
    html = Template(
        '{% load print_frame %}{% print_frame_header paper orient school "عنوان" %}'
    ).render(Context({"paper": paper, "orient": orient, "school": _School()}))

    line = re.search(r'<div class="pf-school">(.*?)</div>', html, re.S).group(1)
    assert "school-logo--inline" in line and "data:image/png;base64," in line
    assert line.index("school-logo") < line.index("مدرسةٌ تجريبيّة")


@pytest.mark.parametrize("variant", ["", "sheet"])
def test_the_logo_is_smaller_than_the_school_line_so_the_header_never_grows(variant):
    css = Template('{% load print_frame %}{% print_frame_css "a4" "landscape" variant %}').render(
        Context({"variant": variant})
    )

    line = float(re.findall(r"\.pf-school \{[^}]*line-height: ([\d.]+)mm", css)[-1])
    side = float(re.findall(r"\.school-logo \{[^}]*width: ([\d.]+)mm", css)[-1])
    assert side < line, (side, line)


@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("kind", ["teachers", "classes"])
def test_every_sheet_page_carries_exactly_the_logo_and_tajawal(
    school,
    busiest_teacher,
    busiest_class,
    kind,
    paper,  # noqa: F811
):
    _, pdf = _pages(school, kind, paper)

    pages = pypdf.PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) == 36
    assert all(len(page.images) == 1 for page in pages), "الشعارُ وحدَه صورةٌ في كلّ ورقة"
    fonts = _fonts(pdf)
    assert {"Tajawal", "Tajawal-Bold"} <= fonts and not any("DejaVu" in f for f in fonts), fonts
