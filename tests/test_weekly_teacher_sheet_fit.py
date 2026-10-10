"""ورقةُ المعلّم الأسبوعيّة (صفحةٌ لكلّ معلّم) بخطٍّ مكبَّر: تبقى صفحةً واحدةً ولا تُقَصّ خليّةٌ — قياسٌ على رسم WeasyPrint حقيقيّ.

ملاحظةُ المالك 2026-10-10 (W-20261010-049): خطُّ الجدول الأسبوعيّ صغيرٌ في ورقةٍ فيها متّسع. فكُبِّر `WEEKLY_TEACHER_BOOST` بقدرٍ **مقيسٍ** على الأسوأ:
معلّمٌ بخمسٍ وثلاثين حصّةً (كلُّ خليّةٍ شعبةٌ ومادّةٌ طويلةُ الاسم وتوقيت). والحدُّ قياسُ صناديق الرسم نفسِه: ما يعلو ارتفاعَ الخليّة المحسوبَ بالملّيمتر
(`wg-fit` بـ`overflow: hidden`) يُقَصّ بصمت — فيُعدّ ذلك فشلاً. أسماءٌ ومعلّمون مصطنعون.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

import operations.schedule_selectors as selectors
from operations.models import ScheduleSlot, Subject
from operations.schedule_paper import WEEKLY_TEACHER_BOOST, paper_geometry
from tests.conftest import ClassGroupFactory
from tests.test_schedule_pages_parity import _register, arts  # noqa: F401

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def _fit(html: str) -> tuple[int, int, int]:
    """(عددُ الصفحات، خلايا الجسم، المقصوصةُ منها) من صناديق WeasyPrint — لا من نصٍّ ولا تقدير."""
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    from core.pdf_utils import _inject_fonts

    base = Path(settings.BASE_DIR).as_uri() + "/"
    doc = HTML(string=_inject_fonts(html), base_url=base).render(font_config=FontConfiguration())
    cells = clipped = 0

    def bottom(box) -> float:
        low = box.position_y + box.margin_height() if hasattr(box, "margin_height") else 0
        return max([low, *(bottom(c) for c in getattr(box, "children", None) or [])])

    def walk(box) -> None:
        nonlocal cells, clipped
        element = getattr(box, "element", None)
        classes = (element.get("class") if element is not None else "") or ""
        if "wg-fit" in classes.split() and type(box).__name__ == "BlockBox" and box.children:
            cells += 1
            need = max(bottom(c) for c in box.children) - box.content_box_y()
            clipped += need > box.height + 0.5
        for child in getattr(box, "children", None) or []:
            walk(child)

    for page in doc.pages:
        walk(page._page_box)
    return len(doc.pages), cells, clipped


@pytest.fixture
def busiest_teacher(school, teacher_user, arts):  # noqa: F811
    """معلّمٌ بخمسٍ وثلاثين حصّةً (7 × 5) بمادّةٍ طويلةِ الاسم — أسوأُ ورقةٍ أسبوعيّةٍ ممكنة."""
    _register(teacher_user, school, arts, "إدارة الأعمال")
    subject = Subject.objects.create(
        school=school, name_ar="التكنولوجيا وعلوم الحاسب الآلي", code="TEC"
    )
    n = 0
    for day in range(5):
        for period in range(1, 8):
            n += 1
            ScheduleSlot.objects.create(
                school=school,
                class_group=ClassGroupFactory(
                    school=school,
                    grade="G12",
                    section=str(n),
                    level_type="prep",
                    academic_year=YEAR,
                ),
                teacher=teacher_user,
                subject=subject,
                day_of_week=day,
                period_number=period,
                start_time=dt.time(7, 10),
                end_time=dt.time(7, 55),
                academic_year=YEAR,
                is_active=True,
            )
    return teacher_user


def _paper_html(client, principal_user, paper: str) -> str:
    client.force_login(principal_user)
    query = {"kind": "teachers", "year": YEAR, "paper": paper, "orient": "landscape"}
    return client.get(reverse("schedule_pages_paper"), query).content.decode()


@pytest.mark.parametrize("paper", ["a4", "a3"])
def test_the_busiest_teacher_stays_on_one_page_with_no_clipped_cell(
    client, principal_user, busiest_teacher, paper
):
    pages, cells, clipped = _fit(_paper_html(client, principal_user, paper))

    assert (pages, cells, clipped) == (1, 35, 0)


@pytest.mark.parametrize("paper", ["a4", "a3"])
def test_the_body_font_is_larger_than_before_and_breaks_stay_as_they_were(paper):
    plain = paper_geometry(paper, "landscape", with_who=True).css
    bigger = paper_geometry(paper, "landscape", with_who=True, teacher_sheet=True).css

    for key in ("subject_pt", "meta_pt", "time_pt", "day_pt", "head_pt"):
        assert float(bigger[key][:-2]) > float(plain[key][:-2]), key
    # عمودُ الفسحة ضيّقٌ بالملّيمتر والخليّةُ المشتركةُ ستّةُ أسطرٍ: خطُّهما كما كان
    for key in ("break_pt", "multi_subject_pt", "multi_pt"):
        assert bigger[key] == plain[key], key


def test_the_measurement_can_fail_a_boost_past_the_measured_limit(
    client, principal_user, busiest_teacher, monkeypatch
):
    """حارسُ الحارس: تكبيرٌ فوق الحدّ المقيس (1.45× على A4) يُظهر خليّةً مقصوصةً — فالاختبارُ أعلاه ليس فارغاً."""
    original = selectors.paper_geometry
    assert WEEKLY_TEACHER_BOOST["a4"] < 1.45

    def too_big(paper, orient, **kwargs):
        return dataclasses.replace(original(paper, orient, **kwargs), body_boost=1.45)

    monkeypatch.setattr(selectors, "paper_geometry", too_big)

    _, _, clipped = _fit(_paper_html(client, principal_user, "a4"))

    assert clipped > 0
