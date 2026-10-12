"""الورقةُ المفردة (صفحةٌ لكلّ معلّمٍ أو شعبة) بعد إعادة التنسيق (W-20261010-057، 2026-10-12): قياسٌ على PDF مولَّدٍ من **المسار الحقيقيّ**.

رفض المالكُ التنسيقَ السابق: «نوع الخط غير مناسب — البولد قويٌّ جدّاً»، والترويسةُ والتذييلُ نسختان محلّيّتان بفجوةٍ وتذييلٍ مكرَّر. فالمُلزِمُ الآن:

- **الخطُّ Tajawal مضمَّناً** (لا DejaVu): العرضُ نفسُه الذي يبنيه `build_schedule_pages_pdf` — `for_pdf` بلا `@font-face` فيحقنه `_inject_fonts` من القرص.
  (قياسٌ سابقٌ على HTMLِ الشاشة كان يسقط إلى DejaVu لأنّ `@font-face` النسبيّ لا يُحَلّ على القرص، فكانت الأرقامُ كاذبة.)
- **الأوزان:** المادّةُ 500، والتوقيتُ والشعبةُ 400، و700 للترويسة (ترويسةُ الجدول واسمُ المدرسة وعنوانُ الوثيقة) وحدَها.
- **الحدودُ الدنيا بالنقطة:** المادّةُ ≥ 10.5 على A4، والتوقيتُ والشعبةُ ≥ 9، والتذييلُ ≥ 9.
- **صفحةٌ واحدةٌ بلا قصٍّ** لأسوأ معلّمٍ (35 حصّةً) وأطول شعبةٍ، وعمودُ اليوم يتّسع لـ«الأربعاء» — بصناديق رسم WeasyPrint (`wg-fit` بـ`overflow: hidden` يقصّ بصمت، فيُعدّ ذلك فشلاً).
- **الإطارُ المركزيّ** (`print_frame_*`) لا ترويسةٌ ولا تذييلٌ محلّيّان، ولا نصَّ وزارةٍ مكتوباً في القالب (D-400م).

أسماءٌ ومعلّمون مصطنعون.
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import pypdf
import pytest
from django.conf import settings
from django.http import QueryDict
from django.template.loader import render_to_string

from core.pdf_utils import render_pdf_bytes
from operations.models import ScheduleSlot, Subject
from operations.schedule_paper import SINGLE_SHEET_A3_SCALE, SINGLE_SHEET_PT, paper_geometry
from operations.schedule_selectors import pages_payload
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory
from tests.pdf_geometry import text_chunks
from tests.test_schedule_pages_parity import _register, arts  # noqa: F401

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUBJECT = "التكنولوجيا وعلوم الحاسب الآلي"


def _fit(html: str) -> tuple[int, int, int, int]:
    """(عددُ الصفحات، خلايا الجسم، المقصوصةُ منها، أيّامٌ يفيض اسمُها عن عمودها) من صناديق WeasyPrint — لا من نصٍّ ولا تقدير."""
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    from core.pdf_utils import _inject_fonts

    base = Path(settings.BASE_DIR).as_uri() + "/"
    doc = HTML(string=_inject_fonts(html), base_url=base).render(font_config=FontConfiguration())
    cells = clipped = day_overflow = 0

    def bottom(box) -> float:
        low = box.position_y + box.margin_height() if hasattr(box, "margin_height") else 0
        return max([low, *(bottom(c) for c in getattr(box, "children", None) or [])])

    def widest(box) -> float:
        own = getattr(box, "width", 0) if type(box).__name__ == "TextBox" else 0
        return max([own, *(widest(c) for c in getattr(box, "children", None) or [])])

    def walk(box) -> None:
        nonlocal cells, clipped, day_overflow
        element = getattr(box, "element", None)
        classes = (element.get("class") if element is not None else "") or ""
        if "wg-fit" in classes.split() and type(box).__name__ == "BlockBox" and box.children:
            cells += 1
            need = max(bottom(c) for c in box.children) - box.content_box_y()
            clipped += need > box.height + 0.5
        if "wg-day" in classes.split() and type(box).__name__ == "TableCellBox":
            day_overflow += widest(box) > box.width + 0.5
        for child in getattr(box, "children", None) or []:
            walk(child)

    for page in doc.pages:
        walk(page._page_box)
    return len(doc.pages), cells, clipped, day_overflow


@pytest.fixture
def busiest_teacher(school, teacher_user, arts):  # noqa: F811
    """معلّمٌ بخمسٍ وثلاثين حصّةً (7 × 5) بمادّةٍ طويلةِ الاسم — أسوأُ ورقةٍ أسبوعيّةٍ ممكنة."""
    _register(teacher_user, school, arts, "إدارة الأعمال")
    subject = Subject.objects.create(school=school, name_ar=SUBJECT, code="TEC")
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


@pytest.fixture
def busiest_class(school, arts):  # noqa: F811
    """شعبةٌ بخمسٍ وثلاثين حصّةً (7 × 5) بمعلّمٍ باسمٍ طويلٍ ومادّةٍ طويلة — أسوأُ ورقةِ شعبةٍ ممكنة."""
    subject = Subject.objects.create(school=school, name_ar=SUBJECT, code="TEC2")
    group = ClassGroupFactory(
        school=school, grade="G12", section="99", level_type="prep", academic_year=YEAR
    )
    role = RoleFactory(school=school, name="teacher")
    for day in range(5):
        for period in range(1, 8):
            teacher = UserFactory(full_name="عبدالباسط الجاسم المنصوري")
            MembershipFactory(user=teacher, school=school, role=role)
            ScheduleSlot.objects.create(
                school=school,
                class_group=group,
                teacher=teacher,
                subject=subject,
                day_of_week=day,
                period_number=period,
                start_time=dt.time(7, 10),
                end_time=dt.time(7, 55),
                academic_year=YEAR,
                is_active=True,
            )
    return group


def _pages(school, kind: str, paper: str, orient: str = "landscape") -> tuple[str, bytes]:
    """(HTML، PDF) من المسار الحقيقيّ لتصدير صفحات المعلّمين/الشعب: `for_pdf` بلا `@font-face` ثمّ `render_pdf_bytes`."""
    ctx = pages_payload(school, QueryDict(f"kind={kind}&year={YEAR}&paper={paper}&orient={orient}"))
    ctx["embed"] = True
    ctx["for_pdf"] = True
    html = render_to_string("schedule/print_pages.html", ctx)
    return html, render_pdf_bytes(html, paper_size=paper.upper())


def _fonts(pdf: bytes) -> set[str]:
    names: set[str] = set()
    for page in pypdf.PdfReader(io.BytesIO(pdf)).pages:
        for font in (page["/Resources"].get("/Font") or {}).values():
            names.add(str(font.get_object().get("/BaseFont")).split("+")[-1])
    return names


@pytest.mark.parametrize("orient", ["landscape", "portrait"])
@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("kind", ["teachers", "classes"])
def test_the_worst_sheet_stays_on_one_page_with_no_clipped_cell_or_day(
    school,
    busiest_teacher,
    busiest_class,
    kind,
    paper,
    orient,  # noqa: F811
):
    html, _ = _pages(school, kind, paper, orient)

    pages, cells, clipped, day_overflow = _fit(html)

    # 36 ورقةً بالضبط (الأسوأُ + 35 من الجانب الآخر) = صفحةٌ لكلّ ورقة؛ وكلُّها 35 خليّةً.
    assert pages == 36
    assert cells == pages * 35
    assert (clipped, day_overflow) == (0, 0)


@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("kind", ["teachers", "classes"])
def test_the_pdf_embeds_tajawal_and_never_dejavu(
    school,
    busiest_teacher,
    busiest_class,
    kind,
    paper,  # noqa: F811
):
    """«نوعُ الخطّ غير مناسب» كان DejaVu Sans العريض؛ الهويّةُ Tajawal بأوزانها 400 و500 و700."""
    _, pdf = _pages(school, kind, paper)

    fonts = _fonts(pdf)

    # الوزنُ 400 يُسمّى في الملفّ «Tajawal» بلا لاحقة.
    assert {"Tajawal", "Tajawal-Medium", "Tajawal-Bold"} <= fonts, fonts
    assert not any("DejaVu" in name for name in fonts), fonts


@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("kind", ["teachers", "classes"])
def test_the_body_sizes_never_drop_below_the_owners_minimums(
    school,
    busiest_teacher,
    busiest_class,
    kind,
    paper,  # noqa: F811
):
    """حدودُ المالك الدنيا بالنقطة على الصفحة المرسومة لا على CSS: المادّةُ ≥ 10.5 والشعبة/المعلّمُ والتوقيتُ والتذييلُ ≥ 9 (وعلى A3 بنسبتها)."""
    _, pdf = _pages(school, kind, paper)
    scale = SINGLE_SHEET_A3_SCALE if paper == "a3" else 1.0

    chunks = text_chunks(pdf, 0)
    subject = max(size for text, _x, _y, size in chunks if "الحاسب" in text)
    time = min(size for text, _x, _y, size in chunks if "07:10" in text)

    assert subject >= 10.5 * scale - 0.1, subject
    assert time >= 9.0 * scale - 0.1, time
    # لا سطرَ في الصفحة (الشعبةُ والتوقيتُ والتذييلُ وما بينها) بأقلّ من 9pt: الحدُّ الأدنى المرسوم.
    assert min(size for _t, _x, _y, size in chunks) >= 8.9


def test_the_template_has_no_local_header_footer_and_no_literal_ministry_text():
    """إطارٌ مركزيٌّ واحد: لا `.page-header` ولا `.page-footer` محلّيّان، ولا نصَّ وزارةٍ مكتوباً حرفيّاً (D-400م — يُجمَّد من موضعٍ واحد)."""
    source = Path(settings.BASE_DIR, "templates/schedule/print_pages.html").read_text(
        encoding="utf-8"
    )

    assert "print_frame_header" in source and "print_frame_footer" in source
    assert "print_frame_css" in source
    assert "page-header" not in source and "page-footer" not in source
    assert "وزارة التربية" not in source


@pytest.mark.parametrize("paper", ["a4", "a3"])
def test_the_header_and_footer_come_from_the_frame_and_the_year_is_bidi_isolated(
    school,
    busiest_teacher,
    paper,  # noqa: F811
):
    html, pdf = _pages(school, "teachers", paper)

    assert html.count('id="print-header"') == html.count('id="print-footer"') >= 1
    # السنةُ بين عازلَي اتّجاه حقيقيَّين وحولها نصٌّ بمسافات: «العام الدراسي ⁦2026-2027⁩».
    assert f"العام الدراسي ⁦{YEAR}⁩" in html
    drawn = " ".join(text for text, _x, _y, _size in text_chunks(pdf, 0))
    assert "الشحانية" in drawn and "الجدول الأسبوعي للمعلّم" in drawn


def test_the_sizes_are_explicit_minimums_not_a_boost():
    for paper, scale in (("a4", 1.0), ("a3", SINGLE_SHEET_A3_SCALE)):
        css = paper_geometry(paper, "landscape", with_who=True, single_sheet=True).css
        assert float(css["subject_pt"][:-2]) == pytest.approx(
            SINGLE_SHEET_PT["subject_base"] * scale, abs=0.06
        )
        assert float(css["time_pt"][:-2]) == pytest.approx(
            SINGLE_SHEET_PT["time_base"] * scale, abs=0.06
        )
    # التوقيتُ أصغرُ من المادّة بنحو 1.5pt
    assert 1.2 <= SINGLE_SHEET_PT["subject_base"] - SINGLE_SHEET_PT["time_base"] <= 1.8


@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
def test_the_framed_geometry_takes_what_the_frame_leaves(paper, orient):
    """الورقةُ المفردة تأخذ من المتن ما يتركه الإطارُ لا ما كانت تتركه الترويسةُ القديمة: لا فجوةَ ولا تذييلَ مكرَّراً."""
    from core.print_frame import frame

    geo = paper_geometry(paper, orient, with_who=True, single_sheet=True)
    fr = frame(paper, orient)

    assert geo.framed and geo.header_h == 0 and geo.footer_h == 0
    assert geo.content_h == pytest.approx(fr.body_height, abs=0.05)
    assert geo.bands_h + geo.row_h * geo.rows <= geo.content_h + 0.5


@pytest.mark.parametrize("paper", ["a4", "a3"])
def test_the_actual_week_strip_takes_rows_and_still_fits(paper):
    bare = paper_geometry(paper, "landscape", with_who=False, single_sheet=True)
    keyed = paper_geometry(paper, "landscape", with_who=False, strip_lines=4, single_sheet=True)

    assert keyed.row_h < bare.row_h
    assert keyed.bands_h + keyed.row_h * keyed.rows <= keyed.content_h + 0.5


def test_the_old_geometry_is_untouched_without_single_sheet():
    """الأسلوبُ القديم (بترويسته المحلّيّة وأحجامه الأصليّة) يبقى لمن لا يطلب `single_sheet`."""
    old = paper_geometry("a4", "landscape", with_who=False)

    assert not old.framed and (old.header_h, old.footer_h, old.margin_top) == (29, 10, 8)
    assert old.css["subject_pt"] == "8.5pt" and old.css["day_col_w"] == "16.0mm"
