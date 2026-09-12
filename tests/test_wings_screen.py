"""شاشةُ الأجنحة — طابقان، وجرسٌ يُقال بالساعة، وعددُ استعلاماتٍ لا يتبع الأجنحة.

الشاشةُ تعرض خمسةَ أجنحةٍ ولكلٍّ شُعبُه وطلابُه وجرسُه وموضعُه من الساعة.
وقراءةُ ذلك من النماذج مباشرةً تُنتج استعلاماً لكلّ جناحٍ لكلّ سؤال — فيُحرَس
العددُ هنا، لأنّ خللاً كهذا لا يظهر في شاشةٍ بخمسة صفوفٍ ويظهر في أربعين.
"""

import datetime as dt
import io

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.management.commands.seed_wings import WINGS
from core.models import TimeBand, Wing
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from wings.services import bell_tables, floors_overview

pytestmark = pytest.mark.django_db

ESE_SECTIONS = [("G8", "ESE"), ("G9", "ESE"), ("G10", "ESE")]
SUNDAY = dt.date(2026, 9, 13)
THURSDAY_DATE = dt.date(2026, 9, 17)
FRIDAY = dt.date(2026, 9, 18)


def _level(grade):
    return "prep" if grade in ("G7", "G8", "G9") else "sec"


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def built(school, year):
    """المدرسةُ مبذورةً: شُعبٌ وأجراسٌ وأجنحةٌ وطالبٌ في كلّ شعبة."""
    for grade, section in [pair for *_head, pairs in WINGS for pair in pairs] + ESE_SECTIONS:
        klass = ClassGroupFactory(
            school=school,
            grade=grade,
            section=section,
            level_type=_level(grade),
            academic_year=year,
            has_own_timetable=section == "ESE",
        )
        StudentEnrollmentFactory(student=UserFactory(), class_group=klass)
    call_command("seed_time_bands", "--assign", stdout=io.StringIO())
    call_command("seed_wings", "--assign", stdout=io.StringIO())
    return {wing.code: wing for wing in Wing.objects.filter(school=school, academic_year=year)}


@pytest.fixture
def leader(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="المدير", national_id="29000000041")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _at(day, hour, minute):
    return dt.datetime.combine(day, dt.time(hour, minute))


class TestTheFloorsAreTwo:
    def test_both_floors_appear_in_order(self, school, built, year):
        panels = floors_overview(school, year, _at(SUNDAY, 9, 45))

        assert [panel.code for panel in panels] == ["ground", "first"]

    def test_the_ground_floor_holds_two_wings_and_the_first_three(self, school, built, year):
        ground, first = floors_overview(school, year, _at(SUNDAY, 9, 45))

        assert [card.wing.code for card in ground.wings] == ["w1", "w2"]
        assert [card.wing.code for card in first.wings] == ["w3", "w4", "w5"]

    def test_each_floor_counts_its_own_sections_and_students(self, school, built, year):
        ground, first = floors_overview(school, year, _at(SUNDAY, 9, 45))

        assert (ground.section_count, first.section_count) == (10, 15)
        assert (ground.student_count, first.student_count) == (10, 15)

    def test_the_ground_floor_rings_one_bell_and_the_first_two(self, school, built, year):
        ground, first = floors_overview(school, year, _at(SUNDAY, 9, 45))

        assert [bell.band_code for bell in ground.bells] == ["ground"]
        assert [bell.band_code for bell in first.bells] == ["ninth", "secondary"]

    def test_the_special_education_sections_belong_to_no_floor(self, school, built, year):
        """ثلاثُ شُعبٍ خارجَ الأجنحة — فمجموعُ الطابقين 25 لا 28."""
        panels = floors_overview(school, year, _at(SUNDAY, 9, 45))

        assert sum(panel.section_count for panel in panels) == 25


class TestTheWingCardSaysWhatMatters:
    def test_only_the_split_wing_is_marked_split(self, school, built, year):
        panels = floors_overview(school, year, _at(SUNDAY, 9, 45))
        split = {card.wing.code for panel in panels for card in panel.wings if card.is_split}

        assert split == {"w3"}

    def test_the_split_wing_shows_two_positions(self, school, built, year):
        card = _card(floors_overview(school, year, _at(THURSDAY_DATE, 9, 45)), "w3")

        assert len(card.positions) == 2
        assert {p.running.label for p in card.positions} == {"الفسحة", "الحصّة 4"}

    def test_a_plain_wing_shows_one(self, school, built, year):
        card = _card(floors_overview(school, year, _at(SUNDAY, 9, 45)), "w1")

        assert len(card.positions) == 1
        assert card.positions[0].says == "الفسحة · حتّى 09:55"

    def test_a_wing_on_a_foreign_bell_is_flagged(self, school, built, year):
        upper = TimeBand.objects.get(school=school, code="secondary")
        built["w1"].class_groups.filter(grade="G7", section="1").update(time_band=upper)

        card = _card(floors_overview(school, year, _at(SUNDAY, 9, 45)), "w1")

        assert [band.code for band in card.off_floor] == ["secondary"]

    def test_a_coherent_wing_flags_nothing(self, school, built, year):
        for panel in floors_overview(school, year, _at(SUNDAY, 9, 45)):
            for card in panel.wings:
                assert card.off_floor == []

    def test_the_weekend_leaves_the_positions_empty(self, school, built, year):
        panels = floors_overview(school, year, _at(FRIDAY, 9, 45))

        assert all(card.positions == [] for panel in panels for card in panel.wings)
        assert all(panel.bells == [] for panel in panels)

    def test_the_split_wing_is_still_split_on_a_day_off(self, school, built, year):
        """«جرسان» صفةُ ممرٍّ لا حالةُ يوم — ولو اشتُقّت من أجراس اليوم لاختفت
        يومَ الجمعة، فقرأها القارئُ إصلاحاً لجناحٍ لم يتغيّر."""
        card = _card(floors_overview(school, year, _at(FRIDAY, 9, 45)), "w3")

        assert card.is_split is True
        assert card.bells == []


def _card(panels, code):
    return next(card for panel in panels for card in panel.wings if card.wing.code == code)


class TestTheDayTables:
    def test_there_are_two_tables_one_per_day_kind(self, school, built):
        assert [table.label for table in bell_tables(school)] == ["الأحد – الأربعاء", "الخميس"]

    def test_a_row_holds_one_cell_per_bell(self, school, built):
        regular = bell_tables(school)[0]

        assert len(regular.bells) == 3
        assert all(len(row) == 3 for row in regular.rows)

    def test_the_table_is_as_deep_as_the_longest_bell(self, school, built):
        """الخميسُ يوماه مختلفا الطول — والأقصرُ يُملأ بفراغٍ لا يُقصّ الجدول."""
        thursday = bell_tables(school)[1]
        depth = max(len(bell.slots) for bell in thursday.bells)

        assert len(thursday.rows) == depth
        assert any(cell is None for row in thursday.rows for cell in row)

    def test_the_ground_column_puts_prayer_before_the_seventh(self, school, built):
        regular = bell_tables(school)[0]
        column = [row[0].label for row in regular.rows if row[0]]

        assert column.index("الصلاة") < column.index("الحصّة 7")


class TestThePageRenders:
    def test_a_leader_sees_the_five_wings(self, client_as, school, built, leader):
        body = client_as(leader).get(reverse("wings:floors")).content.decode()

        for code in ("جناح 1", "جناح 2", "جناح 3", "جناح 4", "جناح 5"):
            assert code in body

    def test_both_floors_are_named(self, client_as, school, built, leader):
        body = client_as(leader).get(reverse("wings:floors")).content.decode()

        assert "الطابق الأرضيّ" in body
        assert "الطابق الأوّل" in body

    def test_the_split_badge_appears_once(self, client_as, school, built, leader):
        """شارةُ «جرسان» لجناحٍ واحدٍ — وظهورُها في اثنين يعني خللاً في البيانات."""
        body = client_as(leader).get(reverse("wings:floors")).content.decode()

        assert body.count(">جرسان<") == 1

    def test_a_teacher_is_turned_away(self, client_as, school, built, teacher_user):
        response = client_as(teacher_user).get(reverse("wings:floors"))

        assert response.status_code in (302, 403)

    def test_the_page_costs_a_fixed_number_of_queries(
        self, client_as, school, built, leader, django_assert_max_num_queries
    ):
        """خمسةُ أجنحةٍ لا تعني خمسةَ استعلامات — والعددُ لا يتبعها."""
        client = client_as(leader)
        client.get(reverse("wings:floors"))  # يُسخّن الجلسةَ والصلاحيّات

        with django_assert_max_num_queries(25):
            client.get(reverse("wings:floors"))
