"""الجدولُ العامّ المطبوع على A3 عرضيّة = ت1 (قرارُ المالك 2026-09-26): ورقةٌ واحدةٌ بخطٍّ مقروء.

اثنان وسبعون معلّماً على صفحةٍ واحدةٍ بخطّ `A3_SHEET_PT` موحَّدٍ (استثناءٌ اختاره المالكُ لهذا الجدول بعد رؤية النماذج الأربعة). فالاختبارُ
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
from operations.templatetags.week_tags import (
    A3_SHEET_PT,
    a3_metrics,
    dept_row_height,
    name_column_mm,
)
from tests.conftest import ClassGroupFactory
from tests.pdf_geometry import median_center_offset_mm, missing_names, text_chunks
from tests.test_week_page import YEAR, _teacher, world  # noqa: F401

pytestmark = pytest.mark.django_db

#: أصغرُ خطٍّ يُقبل على ورقة A3 = خطُّ الورقة نفسُه (`A3_SHEET_PT`: 7.9 في ت1، ورُفع بقرار المالك 2026-09-27) بهامش تقريبٍ للنقطة العشريّة.
MIN_PT = A3_SHEET_PT - 0.05

#: أسماءٌ مصطنعةٌ عريضةُ الحروف — نواتجُ مقطعيها (الأوّل + الكنية) 16–17 حرفاً، أطولُ ما تحمله عمودُ الاسم.
FIRST = ["سعد", "ناصر", "فيصل", "طلال", "ماجد", "بدر", "راشد", "حمد"]
LAST = [
    "الكعبي",
    "المري",
    "الهاجري",
    "النعيمي",
    "السليطي",
    "العطية",
    "الدوسري",
    "الهتمي",
    "الكواري",
]
WIDE_NAMES = [
    "عبدالباسط خالد سعد الجاسمي",
    "عبدالعزيز علي سعد الشمراني",
    "عبدالمنعم محمد علي المحمدي",
    "عبدالرحمن يوسف عمر الحمداني",
]


def _synthetic_name(i: int) -> str:
    """اسمٌ مصطنعٌ فريدٌ بلا أرقامٍ ولا تشكيل (يُقرأ من نصّ الـPDF بلا التباسٍ بين الأرقام والحروف)."""
    if i < len(WIDE_NAMES):
        return WIDE_NAMES[i]
    return f"{FIRST[i % 8]} خالد {LAST[(i // 8) % 9]}"


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
        people = [_teacher(school, _synthetic_name(i)) for i in range(teachers)]
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


def _render(world, query="view=all_teachers&source=plan&paper=a3&orient=landscape", notes=None):  # noqa: F811
    ctx = schedule_print_payload(world["school"], world["principal"], QueryDict(query))
    if notes is not None:
        ctx["nav"] = {**ctx["nav"], "notes": notes}
    ctx["embed"] = True
    ctx["for_pdf"] = True
    html = render_to_string("schedule/print_schedule.html", ctx)
    pdf = render_pdf_bytes(html, paper_size="A3" if ctx.get("paper") == "a3" else "A4")
    return pdf, ctx


def _pdf(world, query="view=all_teachers&source=plan&paper=a3&orient=landscape") -> bytes:  # noqa: F811
    return _render(world, query)[0]


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
    def test_one_page_and_no_font_below_the_sheet_font(self, world, staff):  # noqa: F811
        staff(teachers=72, per_teacher=12)

        pages, smallest, _ = _facts(_pdf(world))

        assert pages == 1, "اثنان وسبعون معلّماً صفحةٌ واحدة (ت1)"
        assert smallest >= MIN_PT, f"أصغرُ خطٍّ مرسومٍ {smallest}pt دون {A3_SHEET_PT}"

    def test_what_the_reader_sees_names_whole_one_footer_row_and_centred_codes(
        self,
        world,
        staff,  # noqa: F811
    ):
        """رسمٌ حقيقيٌّ واحدٌ يُقاس عليه ما اشتكى منه المالك (2026-09-27): اسمٌ مقصوصٌ، وتذييلٌ بأكثر من سطر، ورمزٌ يعلو مركزَ خليّته."""
        staff(teachers=72, per_teacher=12)

        pdf, ctx = _render(world)

        # (٢) لا اسمَ مقصوصاً: كلُّ اسمِ عرضٍ (أطولُها 17 حرفاً عريضاً) بكامله في نصّ الـPDF المرسوم
        shown = [row["display_name"] for row in ctx["matrix"]]
        assert any(len(name) >= 16 for name in shown), "الحالةُ الأصعبُ غائبةٌ من العيّنة"
        assert missing_names(pdf, shown) == [], "أسماءٌ مقصوصةٌ بحدّ عمود الاسم"

        # (٣+٥) التذييلُ صفٌّ واحدٌ: الأعدادُ والرؤيةُ والتاريخُ والصفحةُ على خطٍّ أفقيٍّ واحد (±1pt)
        # عدّادُ الصفحة الآن أرقامٌ في CSS محضة («١ / ١» بلا كلمة «صفحة») من المكوّن المركزيّ — لا نصٌّ يُقاس هنا.
        keys = ("المعلّمون", "تاريخ الطباعة", "مُتَعَلِّمٌ")
        footer = [
            (text, y) for text, _x, y, _size in text_chunks(pdf) if any(k in text for k in keys)
        ]
        assert {k for k in keys if any(k in t for t, _ in footer)} == set(keys)
        ys = [y for _, y in footer]
        assert (
            max(ys) - min(ys) <= 1.0
        ), f"التذييلُ على أكثر من خطّ: {sorted({round(y, 1) for y in ys})}"

        # (٤) الرمزُ متوسّطٌ رأسيّاً في خليّته: وسيطُ الفرق ضمن ±0.2مم على الصفوف العاديّة
        offset = median_center_offset_mm(pdf)
        assert abs(offset) <= 0.2, f"الرمزُ يبعد {offset:.2f}مم عن مركز خليّته"

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

    def test_the_a3_sheet_has_the_full_header_and_the_footer_in_the_page_margins(
        self,
        world,
        staff,  # noqa: F811
    ):
        staff(teachers=10, per_teacher=6)
        ctx = schedule_print_payload(
            world["school"],
            world["principal"],
            QueryDict("view=all_teachers&source=plan&paper=a3&orient=landscape"),
        )

        html = render_to_string(
            "schedule/print_schedule.html", {**ctx, "embed": True, "for_pdf": True}
        )

        # الترويسةُ والتذييلُ من المكوّن المركزيّ (core/print_frame.py، طلبُ #705) لا مكتوبَين هنا.
        assert 'id="print-header"' in html and 'id="print-footer"' in html
        assert "matrix-foot3" not in html and 'class="matrix-foot"' not in html
        assert "mh-ministry" not in html and "mh-school" not in html, "الترويسةُ القديمةُ رُحِّلت"
        assert "size: A3 landscape" in html and "counter(pages)" in html

    def test_a_vision_with_quotes_or_tags_cannot_break_out(self, world, staff):  # noqa: F811
        """الرؤيةُ حقلٌ تحرّره الإدارةُ وتُعرض نصّاً في تذييل المكوّن المركزيّ — فيهرَّبها Django تلقائيّاً كسائر المتن."""
        staff(teachers=5, per_teacher=4)
        school = world["school"]
        school.vision = 'رؤية "x" </style><script>alert(1)</script> \\ & '
        school.save(update_fields=["vision"])
        ctx = schedule_print_payload(
            school,
            world["principal"],
            QueryDict("view=all_teachers&source=plan&paper=a3&orient=landscape"),
        )

        html = render_to_string(
            "schedule/print_schedule.html", {**ctx, "embed": True, "for_pdf": True}
        )

        assert "<script>alert(1)" not in html and "</style><script" not in html
        assert "lt;/style" in html and "lt;script" in html, "المحتوى مفقودٌ لا مهرَّبٌ فقط"


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


class TestTheNameColumnFollowsTheLongestName:
    @pytest.mark.parametrize(
        ("longest", "expected"),
        [(0, "26.0"), (10, "26.0"), (16, "28.8"), (17, "30.5"), (60, "36.0")],
    )
    def test_the_width_grows_with_the_longest_display_name_within_a_floor_and_a_cap(
        self, longest, expected
    ):
        rows = [{"display_name": "ا" * longest}, {"display_name": "قصير"}]

        assert name_column_mm(rows) == expected

    def test_rows_without_a_display_name_use_the_floor(self):
        assert name_column_mm([{}, {"display_name": None}]) == "26.0"
        assert name_column_mm(None) == "26.0"


#: أسوأُ أسبوعٍ فعليّ: الأسطرُ الثلاثةُ التي يكتبها `_week_notes` معاً بأطولِ ما تحمل (كلُّ الأيّام مغلقةٌ بسببٍ طويل، وكلُّ الأيّام من الخطّة، وحصصٌ بلا رقم).
WORST_NOTES = [
    "الأحد، الاثنين، الثلاثاء، الأربعاء، الخميس: إجازةُ منتصف الفصل الدراسيّ بقرار وزارة التربية والتعليم والتعليم العالي — لا حصص.",
    "لم تُولَّد حصصُ الأحد، الاثنين، الثلاثاء، الأربعاء، الخميس بعد، فتُعرض وفق الخطّة المعتمدة.",
    "137 حصّةً تاريخيّةً بلا رقمٍ (من جدولٍ سابق) لا تُعرض.",
]


class TestAWeekWithNotesStillFitsOnOneSheet:
    """قياسُ المايسترو 2026-09-27: عند A3_SHEET_PT لا يتّسع سطرُ ملاحظاتٍ فيسقط شرطُ «ورقةٌ واحدة» في أسابيع الإغلاق — فالخطُّ يُصغَّر بقدر ما يلزم."""

    def test_the_worst_week_is_one_page_at_the_scaled_font(self, world, staff):  # noqa: F811
        staff(teachers=72, per_teacher=12)

        pdf, _ctx = _render(world, notes=WORST_NOTES)
        pages, smallest, texts = _facts(pdf)

        expected = a3_metrics(len(WORST_NOTES))["pt"]
        assert pages == 1, f"أسوأُ أسبوعٍ ({len(WORST_NOTES)} ملاحظات) كسر الصفحةَ عند {expected}pt"
        assert smallest >= expected - 0.05
        assert all(note.split()[0] in texts[0] for note in WORST_NOTES), "الملاحظاتُ تُرسم كلُّها"

    def test_the_font_only_shrinks_when_notes_need_the_room(self):
        fonts = [a3_metrics(n)["pt"] for n in range(0, 4)]

        assert fonts[0] == A3_SHEET_PT, "بلا ملاحظاتٍ الخطُّ كاملاً"
        assert fonts == sorted(fonts, reverse=True), "كلُّ ملاحظةٍ تُصغّر ولا تكبّر"
        assert fonts[3] >= A3_SHEET_PT - 0.5, "التصغيرُ طفيفٌ حتّى في أسوأ أسبوع"

    def test_bad_input_keeps_the_full_font(self):
        assert a3_metrics(None)["pt"] == A3_SHEET_PT
        assert a3_metrics("x")["pt"] == A3_SHEET_PT
        assert a3_metrics(-2)["pt"] == A3_SHEET_PT
