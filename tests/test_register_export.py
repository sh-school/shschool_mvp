"""كشفُ الحصص مطبوعاً ومصدَّراً — كشفُ الشعبة وكشفُ الجناح.

قراراتُ 2026-09-13 التي تحرسها هذه الاختبارات:

- لا رقمَ شخصيّاً في الكشف، لا في الـPDF ولا في Excel.
- ثلاثةُ تواقيع بترتيبها: مشرفُ الجناح، والنائبُ الإداريّ، ومديرُ المدرسة.
- الكشفُ الجزئيُّ يُطبع موسوماً «كشفٌ جزئيٌّ حتى HH:MM»، لا يُمنع.
- ملفُّ Excel محميٌّ للقراءة، ولكشف الجناح ورقةُ ملخّصٍ ثمّ ورقةٌ لكلّ شعبة.
- المشرفُ لجناحه وحدَه، كصلاحيّة الرصد.

ومعها ثلاثُ علل في أدوات التصدير المشتركة أُصلحت مع الكشف.
"""

import io

import openpyxl
import pytest
from django.urls import reverse

from core.export_utils import get_export_context
from core.models import Wing
from core.pdf_utils import _content_disposition
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_period_register import (  # noqa: F401 — تجهيزاتُ الكشف نفسُها
    SUNDAY,
    _confirm,
    _periods,
    at,
    kids,
    klass,
    supervisor,
    teacher,
    year,
)
from wings.register import section_register, wing_register

pytestmark = pytest.mark.django_db


def _section_url(klass, fmt="html"):
    return (
        reverse("wings:section_register", args=[klass.id])
        + f"?date={SUNDAY.isoformat()}&format={fmt}"
    )


def _wing_url(code, fmt="html"):
    return reverse("wings:wing_register", args=[code]) + f"?date={SUNDAY.isoformat()}&format={fmt}"


@pytest.fixture
def leaders(school):
    """النائبُ الإداريّ والمدير — خانتا التوقيع الثانية والثالثة."""
    for name, role, nid in (
        ("النائب الإداري", "vice_admin", "29300000094"),
        ("مدير المدرسة", "principal", "29300000095"),
    ):
        MembershipFactory(
            user=UserFactory(full_name=name, national_id=nid),
            school=school,
            role=RoleFactory(school=school, name=role),
        )


# ══════════════════════════════════════════════════════════════════
# البيانات
# ══════════════════════════════════════════════════════════════════


class TestTheSectionRegister:
    def test_each_cell_says_the_status_and_the_minutes(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 3)
        _confirm(
            klass,
            periods[0],
            {
                kids[0]: "absent",
                kids[1]: "late",
                kids[2]: {"status": "absent", "whereabouts": "clinic"},
            },
            supervisor,
            now=at(7, 22),
        )

        register = section_register(klass, SUNDAY, now=at(9, 0))

        first, second, third = (row.marks[0] for row in register.rows[:3])
        assert (first.text, second.text, third.text) == ("غ", "م 12", "غ ع")
        assert register.rows[1].late_minutes == 12
        assert register.rows[3].marks[1].text == "·", "حصّةٌ لم تُثبَّت نقطة"

    def test_the_column_keeps_its_first_confirmation(
        self, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 2)
        _confirm(klass, periods[0], {}, supervisor, now=at(7, 20))
        _confirm(klass, periods[1], {}, supervisor, now=at(9, 30))

        register = section_register(klass, SUNDAY, now=at(10, 0))

        on_time, late = register.columns
        assert on_time.first_confirmed_at.strftime("%H:%M") == "07:20"
        assert (on_time.label, late.label) == ("مثبّتة", "ثُبّتت متأخّرة")
        assert on_time.confirmed_by == "مشرف الجناح"

    def test_a_day_with_unconfirmed_periods_is_partial(
        self, school, klass, kids, teacher, supervisor
    ):
        periods = _periods(school, klass, teacher, 2)
        _confirm(klass, periods[0], {}, supervisor)

        assert section_register(klass, SUNDAY).is_partial
        _confirm(klass, periods[1], {}, supervisor)
        assert not section_register(klass, SUNDAY).is_partial

    def test_three_signatures_in_their_order(
        self, school, klass, kids, teacher, supervisor, leaders
    ):
        register = section_register(klass, SUNDAY)

        assert [(s.title, s.name) for s in register.signatories] == [
            ("مشرف الجناح", "مشرف الجناح"),
            ("النائب الإداري", "النائب الإداري"),
            ("مدير المدرسة", "مدير المدرسة"),
        ]


class TestTheWingRegister:
    def test_the_matrix_pads_a_shorter_day(self, school, year, klass, kids, teacher, supervisor):
        from tests.conftest import ClassGroupFactory

        short = ClassGroupFactory(
            school=school, grade="G7", section="2", level_type="prep", academic_year=year
        )
        short.wing = klass.wing
        short.save(update_fields=["wing"])
        _periods(school, klass, teacher, 3)
        _periods(school, short, UserFactory(national_id="29300000096"), 2, at_hour=12)

        register = wing_register(klass.wing, SUNDAY)

        assert register.width == 3
        assert [len(cells) for _section, cells in register.matrix] == [3, 3]
        assert register.matrix[1][1][-1] is None


# ══════════════════════════════════════════════════════════════════
# المخارج
# ══════════════════════════════════════════════════════════════════


class TestTheExports:
    def test_the_print_view_has_no_national_id(
        self, client_as, school, klass, kids, teacher, supervisor, leaders
    ):
        _confirm(klass, _periods(school, klass, teacher, 2)[0], {kids[0]: "absent"}, supervisor)

        body = client_as(supervisor).get(_section_url(klass)).content.decode()

        assert "كشفٌ جزئيٌّ حتى" in body
        assert "طالب 0" in body
        for kid in kids:
            assert kid.national_id not in body, "لا رقمَ شخصيّاً في الكشف"
        assert body.count('class="sig-item"') == 3

    def test_the_excel_is_protected_and_has_no_national_id(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _confirm(klass, _periods(school, klass, teacher, 2)[0], {}, supervisor)

        response = client_as(supervisor).get(_section_url(klass, "xlsx"))

        assert response.status_code == 200
        assert response["Content-Disposition"].isascii()
        book = openpyxl.load_workbook(io.BytesIO(response.content))
        sheet = book.active
        assert sheet.protection.sheet
        assert sheet.sheet_view.rightToLeft
        values = " ".join(str(c.value) for row in sheet.iter_rows() for c in row if c.value)
        assert "طالب 0" in values
        for kid in kids:
            assert kid.national_id not in values

    def test_the_wing_workbook_is_a_summary_then_a_sheet_per_section(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 2)

        response = client_as(supervisor).get(_wing_url(klass.wing.code, "xlsx"))

        book = openpyxl.load_workbook(io.BytesIO(response.content))
        assert book.sheetnames == ["ملخّص الجناح", klass.short_code]
        assert all(sheet.protection.sheet for sheet in book.worksheets)

    def test_the_pdf_downloads(self, client_as, school, klass, kids, teacher, supervisor):
        _periods(school, klass, teacher, 1)

        response = client_as(supervisor).get(_section_url(klass, "pdf"))

        assert response.status_code in (200, 503), "503 حين لا تتوفّر خدمةُ التوليد"
        if response.status_code == 200:
            assert response["Content-Type"] == "application/pdf"
            assert response["Content-Disposition"].startswith("attachment;")


class TestTheOrientation:
    """أفقيٌّ افتراضاً، وعموديٌّ بالاختيار — صفحةٌ واحدةٌ لكلّ فصل (قرارُ 2026-09-13)."""

    def test_the_print_view_follows_the_chosen_orientation(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 2)
        client = client_as(supervisor)

        assert "size: A4 landscape" in client.get(_section_url(klass)).content.decode()
        portrait = client.get(_section_url(klass) + "&orient=portrait").content.decode()
        assert "size: A4 portrait" in portrait
        assert "page-break-inside: avoid" in portrait, "العموديُّ صفحةٌ واحدةٌ للفصل"

    def test_a_portrait_excel_fits_each_sheet_on_one_page(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 2)

        response = client_as(supervisor).get(
            _wing_url(klass.wing.code, "xlsx") + "&orient=portrait"
        )

        book = openpyxl.load_workbook(io.BytesIO(response.content))
        for sheet in book.worksheets:
            assert sheet.page_setup.orientation == "portrait"
            assert (sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight) == (1, 1)


class TestTheFooter:
    """الذيلُ في المخارج الثلاثة — كان في الـPDF وحدَه (ملاحظةُ 2026-09-13)."""

    def test_the_print_view_ends_each_class_page_with_the_footer(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 2)

        body = client_as(supervisor).get(_wing_url(klass.wing.code)).content.decode()

        assert body.count('class="sheet-footer"') == 2, "ملخّصُ الجناح وكشفُ الشعبة"
        assert "مُتَعَلِّمٌ رِيَادِيٌّ لِتَنْمِيَةٍ مُسْتَدَامَةٍ" in body

    def test_every_excel_sheet_ends_with_the_footer_inside_its_print_area(
        self, client_as, school, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 2)

        response = client_as(supervisor).get(_wing_url(klass.wing.code, "xlsx"))

        book = openpyxl.load_workbook(io.BytesIO(response.content))
        for sheet in book.worksheets:
            last = sheet.cell(row=sheet.max_row, column=1).value or ""
            assert "وزارة التربية والتعليم" in last
            assert sheet.print_area.endswith(f"${sheet.max_row}")


class TestOnlyHisOwnWing:
    def test_another_wings_supervisor_is_turned_away(
        self, client_as, school, year, klass, kids, teacher, supervisor
    ):
        other = UserFactory(full_name="مشرف جناح آخر", national_id="29300000093")
        MembershipFactory(
            user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
        )
        Wing.objects.create(
            school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
        )

        assert client_as(other).get(_section_url(klass, "xlsx")).status_code == 404
        assert client_as(other).get(_wing_url(klass.wing.code, "xlsx")).status_code == 404
        assert client_as(other).get(_wing_url("w2", "xlsx")).status_code == 200

    def test_a_teacher_is_refused(self, client_as, school, klass, teacher, supervisor):
        response = client_as(teacher).get(_section_url(klass))

        assert response.status_code in (302, 403)


# ══════════════════════════════════════════════════════════════════
# علل الأدوات المشتركة
# ══════════════════════════════════════════════════════════════════


class TestTheSharedExportTools:
    def test_the_exporter_role_is_written_in_arabic(self, rf, school, supervisor):
        request = rf.get("/")
        request.user = supervisor

        context = get_export_context(request, "كشف")

        assert context["exporter_role"] == "مشرف إداري"
        assert context["exporter_role_code"] == "admin_supervisor"

    @pytest.mark.parametrize(
        ("filename", "fallback"),
        [("كشف_الجناح.xlsx", "document.xlsx"), ("register_11-5.xlsx", "register_11-5.xlsx")],
    )
    def test_an_excel_name_keeps_its_extension(self, filename, fallback):
        header = _content_disposition(filename, True)

        assert header.isascii()
        assert f'filename="{fallback}"' in header

    def test_the_printed_page_header_is_the_schools_own_name(self):
        from reports.services import ExcelService

        book, sheet, _styles = ExcelService._make_workbook("ورقة")
        ExcelService._add_professional_header(sheet, "مدرسة التجربة", "تقرير", "2026-2027", 3)
        ExcelService._setup_print(sheet, 3, 1)

        assert sheet.oddHeader.center.text.endswith("مدرسة التجربة")
