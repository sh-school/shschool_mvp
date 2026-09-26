"""الجدولُ العامّ المطبوع على A3 عرضيّة = ت1 (قرارُ المالك 2026-09-26): ورقةٌ واحدةٌ بخطٍّ مقروء.

اثنان وسبعون معلّماً على صفحةٍ واحدةٍ بخطٍّ 7.9pt موحَّدٍ (استثناءٌ اختاره المالكُ لهذا الجدول بعد رؤية النماذج الأربعة). فالاختبارُ
**رسمٌ حقيقيّ** بـWeasyPrint لا نصٌّ: عددُ الصفحات وأصغرُ خطٍّ مرسومٍ في الملفّ يُقرآن من الـPDF نفسِه. وسلوكُ الفائض يبقى: من زاد
معلّموه عن السعة انتقل الباقي إلى ورقةٍ ثانيةٍ بترويسة الجدول نفسِها. وA4 لا يُمَسّ. أسماءٌ ومعلّمون مصطنعون.
"""

import datetime as dt
import io

import pypdf
import pytest
from django.http import QueryDict
from django.template import Context, Template
from django.template.loader import render_to_string

from core.pdf_utils import render_pdf_bytes
from operations.models import ScheduleSlot
from operations.schedule_selectors import schedule_print_payload
from operations.templatetags.week_tags import dept_row_height
from tests.conftest import ClassGroupFactory
from tests.test_week_page import YEAR, _teacher, world  # noqa: F401

pytestmark = pytest.mark.django_db

#: أصغرُ خطٍّ يُقبل على ورقة A3 (7.9pt) بهامش تقريبٍ للنقطة العشريّة.
MIN_PT = 7.9 - 0.05


@pytest.fixture
def staff(world):  # noqa: F811
    """`n` معلّماً بلا تعارضٍ: خلايا (الشعبة × اليوم × الحصّة) تُوزَّع دورةً على المعلّمين فلا يحجز أحدٌ خليّتين متطابقتين."""

    def build(teachers: int, per_teacher: int) -> None:
        school = world["school"]
        classes = [
            ClassGroupFactory(
                school=school,
                grade=f"G{7 + i // 5}",
                section=str(1 + i % 5),
                level_type="prep",
                academic_year=YEAR,
            )
            for i in range(25)
        ]
        people = [_teacher(school, f"معلّمٌ رقم {i}") for i in range(teachers)]
        subjects = [world["math"], world["science"]]
        # خلايا (اليوم × الحصّة) = 35؛ لكلٍّ منها 25 شعبةً على الأكثر، ولا يحجز معلّمٌ خليّتين متطابقتين ولا شعبةٌ خليّةً مرّتين.
        load = [0] * 35
        slots = []
        for t, teacher in enumerate(people):
            taken: set[int] = set()
            for m in range(per_teacher):
                for k in range(35):
                    cell = (t + 3 * m + k) % 35
                    if cell not in taken and load[cell] < 25:
                        break
                taken.add(cell)
                klass = classes[load[cell]]
                load[cell] += 1
                slots.append(
                    ScheduleSlot(
                        school=school,
                        teacher=teacher,
                        class_group=klass,
                        subject=subjects[t % 2],
                        day_of_week=cell // 7,
                        period_number=1 + cell % 7,
                        start_time=dt.time(7, 10),
                        end_time=dt.time(7, 55),
                        academic_year=YEAR,
                    )
                )
        ScheduleSlot.objects.bulk_create(slots)

    return build


def _pdf(world, query="view=all_teachers&source=plan&paper=a3&orient=landscape") -> bytes:  # noqa: F811
    ctx = schedule_print_payload(world["school"], world["principal"], QueryDict(query))
    ctx["embed"] = True
    ctx["for_pdf"] = True
    html = render_to_string("schedule/print_schedule.html", ctx)
    return render_pdf_bytes(html, paper_size="A3" if ctx.get("paper") == "a3" else "A4")


def _facts(pdf: bytes) -> tuple[int, float, list[str]]:
    """(عددُ الصفحات، أصغرُ خطٍّ مرسوم بالنقطة، نصُّ كلّ صفحة)."""
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    smallest = 1000.0
    texts = []
    for page in reader.pages:

        def visit(text, cm, tm, font, size):
            nonlocal smallest
            if text.strip():
                smallest = min(smallest, abs(size * tm[3] * cm[3]))

        texts.append(page.extract_text(visitor_text=visit))
    return len(reader.pages), smallest, texts


class TestTheSeventyTwoTeachersFitOneSheet:
    def test_one_page_and_no_font_below_7_9pt(self, world, staff):  # noqa: F811
        staff(teachers=72, per_teacher=12)

        pages, smallest, _ = _facts(_pdf(world))

        assert pages == 1, "اثنان وسبعون معلّماً صفحةٌ واحدة (ت1)"
        assert smallest >= MIN_PT, f"أصغرُ خطٍّ مرسومٍ {smallest}pt دون 7.9"

    def test_an_overflow_moves_the_rest_to_a_second_sheet_with_the_same_table_header(
        self,
        world,
        staff,  # noqa: F811
    ):
        """سلوكُ الفائض يبقى: ثمانون معلّماً لا تسعهم ورقةٌ فيمضي الباقي إلى ثانيةٍ بترويسة الأيّام نفسِها."""
        staff(teachers=80, per_teacher=10)

        pages, smallest, texts = _facts(_pdf(world))

        assert pages == 2
        assert (
            "الخميس" in texts[1] and "الأحد" in texts[1]
        ), "ترويسةُ الجدول تتكرّر على الورقة الثانية"
        assert smallest >= MIN_PT


class TestTheOtherPapersAreUntouched:
    def test_a4_keeps_the_old_layout(self, world, staff):  # noqa: F811
        staff(teachers=10, per_teacher=6)
        ctx = schedule_print_payload(
            world["school"],
            world["principal"],
            QueryDict("view=all_teachers&source=plan&paper=a4&orient=landscape"),
        )

        html = render_to_string(
            "schedule/print_schedule.html", {**ctx, "embed": True, "for_pdf": True}
        )

        assert "matrix-foot3" not in html and "mh-school" not in html
        assert 'class="matrix-foot"' in html and "--row-h" not in html

    def test_the_a3_sheet_has_the_full_header_and_a_single_footer_row(self, world, staff):  # noqa: F811
        staff(teachers=10, per_teacher=6)
        ctx = schedule_print_payload(
            world["school"],
            world["principal"],
            QueryDict("view=all_teachers&source=plan&paper=a3&orient=landscape"),
        )

        html = render_to_string(
            "schedule/print_schedule.html", {**ctx, "embed": True, "for_pdf": True}
        )

        assert html.count('class="matrix-foot3"') == 1 and 'class="matrix-foot"' not in html
        assert all(cls in html for cls in ("mh-ministry", "mh-school", "mh-year"))
        assert "size: A3 landscape" in html


class TestTheNarrowDepartmentRule:
    @pytest.mark.parametrize(
        ("name", "rows", "expected"),
        [
            ("المهارات الحياتية والمهنية", 2, "4.54mm"),  # ثلاثُ كلمات في صفّين ⇒ يرتفعان
            ("المهارات الحياتية والمهنية", 3, ""),  # ثلاثةُ صفوفٍ تسع الأسطر
            ("الكيمياء", 2, ""),  # كلمةٌ واحدة
            ("التكنولوجيا وعلوم الحاسب", 5, ""),
            ("التربية الإسلامية", 1, "6.15mm"),  # صفٌّ واحد بسطرين
        ],
    )
    def test_the_rows_grow_only_when_the_words_do_not_fit(self, name, rows, expected):
        assert dept_row_height(name, rows, 7.9) == expected

    def test_bad_input_adds_no_padding(self):
        assert dept_row_height("قسم", "x", 7.9) == ""
        assert dept_row_height("قسم", 0, 7.9) == ""
        assert dept_row_height("قسم", 2, 0) == ""


class TestTheExemptionDotOnPaper:
    def test_the_a3_dot_has_no_letter_but_the_screen_keeps_it(self):
        template = Template("{% load exemption_tags %}{% exempt_dot m 0 1 %}")
        found = {(0, 1): ("ministry", "قرارُ وزارة")}

        on_paper = template.render(Context({"m": found, "pad_pt": 7.9}))
        on_screen = template.render(Context({"m": found}))

        assert "m-exempt-dot" in on_paper and "></span>" in on_paper
        assert "m-exempt-dot" in on_screen and "></span>" not in on_screen
