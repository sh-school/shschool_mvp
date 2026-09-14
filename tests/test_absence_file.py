"""ملفُّ غياب الطالب يوماً بيوم، والبحثُ عنه في جناحي (قرارُ 2026-09-14: أقلُّ النقرات).

- الملفُّ يعرض أيّامَ الغياب وحدها، الأحدثُ أوّلاً، بحكمها كما يعدّه الحرمان.
- العذرُ من سطر اليوم يشمل أيّامَ الغياب المتّصلة — والجمعةُ والسبتُ لا تقطعها.
- «اتّصلتُ» ضغطةٌ بالنتيجة، و«عذر» ضغطةٌ بالنوع — ولا تاريخَ يُكتب.
- البحثُ في طلاب أجنحتي وحدها، ونتيجةٌ واحدةٌ تفتح الملفَّ مباشرةً.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import Wing
from operations.absence_file import absence_days
from operations.excuses import grant_excuse
from operations.guardian_contact import log_contact
from operations.models import AbsenceExcuse, GuardianContact
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_absence_excuses import (  # noqa: F401 — التجهيزاتُ نفسُها
    MONDAY,
    _absent_day,
    _back,
    _report,
)
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

YEAR_START = dt.date(2026, 8, 30)
WEDNESDAY = SUNDAY + dt.timedelta(days=3)
THURSDAY = SUNDAY + dt.timedelta(days=4)
NEXT_SUNDAY = SUNDAY + dt.timedelta(days=7)


class TestTheDays:
    def test_only_absence_days_newest_first_with_their_verdict(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor, day=SUNDAY)
        _back(school, klass, teacher, supervisor, MONDAY)
        _absent_day(school, klass, kids[0], teacher, supervisor, day=WEDNESDAY)

        days = absence_days(kids[0], school, YEAR_START, THURSDAY)

        assert [(d.date, d.verdict) for d in days] == [
            (WEDNESDAY, "absent_unexcused"),
            (SUNDAY, "absent_unexcused"),
        ]
        assert (days[0].absent_periods, days[0].scheduled_periods) == (7, 7)

    def test_the_weekend_does_not_break_a_run_but_a_present_day_does(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        """غاب الأربعاءَ والخميسَ والأحدَ التالي: سلسلةٌ واحدة. والأحدُ الأوّلُ قبل حضورٍ منفصل."""
        _absent_day(school, klass, kids[0], teacher, supervisor, day=SUNDAY)
        _back(school, klass, teacher, supervisor, MONDAY)
        for day in (WEDNESDAY, THURSDAY, NEXT_SUNDAY):
            _absent_day(school, klass, kids[0], teacher, supervisor, day=day)

        days = {d.date: d for d in absence_days(kids[0], school, YEAR_START, NEXT_SUNDAY)}

        assert (days[THURSDAY].run_from, days[THURSDAY].run_to) == (WEDNESDAY, NEXT_SUNDAY)
        assert (days[SUNDAY].run_from, days[SUNDAY].run_to) == (SUNDAY, SUNDAY)

    def test_each_day_carries_its_call_excuse_and_deadline(
        self, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor, day=SUNDAY)
        _back(school, klass, teacher, supervisor, MONDAY)
        _absent_day(school, klass, kids[0], teacher, supervisor, day=WEDNESDAY)
        log_contact(
            student=kids[0], school=school, absence_date=SUNDAY, outcome="no_answer", by=supervisor
        )
        grant_excuse(
            student=kids[0],
            school=school,
            date_from=WEDNESDAY,
            date_to=WEDNESDAY,
            kind="bereavement",
            notes="الجدّ",
            by=supervisor,
            today=THURSDAY,
        )

        days = {d.date: d for d in absence_days(kids[0], school, YEAR_START, THURSDAY)}

        assert days[SUNDAY].contact.outcome == "no_answer"
        assert days[SUNDAY].deadline == WEDNESDAY and days[SUNDAY].late
        assert days[WEDNESDAY].verdict == "absent_excused" and days[WEDNESDAY].excuse
        assert not days[WEDNESDAY].may_excuse


@pytest.fixture
def stranger_wing(school, year):
    """جناحٌ آخرُ بمشرفه وطالبه — لا شأنَ لمشرفنا به."""
    other = UserFactory(full_name="مشرفٌ آخر", national_id="29300000095")
    MembershipFactory(
        user=other, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
    )
    klass2 = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year, wing=wing
    )
    outsider = UserFactory(full_name="أحمد الغريب", national_id="29300000099")
    StudentEnrollmentFactory(student=outsider, class_group=klass2)
    return outsider


class TestTheSearch:
    def test_one_match_opens_the_file_directly_whatever_the_hamza(
        self, client_as, school, seeded_calendar, klass, supervisor
    ):
        ahmad = UserFactory(full_name="أحمد سالم", national_id="29300000097")
        StudentEnrollmentFactory(student=ahmad, class_group=klass)

        response = client_as(supervisor).get(reverse("wings:student_search"), {"q": "احمد"})

        assert response.status_code == 302
        assert response.url == reverse("wings:absence_file", args=[ahmad.id])

    def test_several_matches_are_listed_and_other_wings_are_not(
        self, client_as, school, seeded_calendar, klass, kids, supervisor, stranger_wing
    ):
        response = client_as(supervisor).get(reverse("wings:student_search"), {"q": "طالب"})

        body = response.content.decode()
        assert response.status_code == 200
        assert all(kid.full_name in body for kid in kids)
        assert stranger_wing.full_name not in body

    def test_a_student_of_another_wing_is_not_found_even_by_his_number(
        self, client_as, school, seeded_calendar, klass, supervisor, stranger_wing
    ):
        body = (
            client_as(supervisor)
            .get(reverse("wings:student_search"), {"q": "29300000099"})
            .content.decode()
        )

        assert "لا طالبَ بهذا الاسم في أجنحتك" in body

    def test_the_supervisors_dashboard_carries_the_search(
        self, client_as, school, seeded_calendar, klass, supervisor
    ):
        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert reverse("wings:student_search") in body


class TestTheFileScreen:
    def test_the_file_lists_the_day_with_its_two_buttons(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)

        body = (
            client_as(supervisor)
            .get(reverse("wings:absence_file", args=[kids[0].id]))
            .content.decode()
        )

        assert 'id="day-2026-09-13"' in body
        assert "غائبٌ بلا عذر" in body
        assert "اتّصلتُ" in body and "عذر" in body
        assert 'name="kind" value="medical"' in body

    def test_a_supervisor_of_another_wing_is_turned_away(
        self, client_as, school, seeded_calendar, klass, supervisor, stranger_wing
    ):
        response = client_as(supervisor).get(reverse("wings:absence_file", args=[stranger_wing.id]))

        assert response.status_code == 404

    def test_one_press_on_an_outcome_logs_the_call_for_that_day(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        _absent_day(school, klass, kids[0], teacher, supervisor)

        response = client_as(supervisor).post(
            reverse("wings:absence_file_contact", args=[kids[0].id]),
            {"absence_date": SUNDAY.isoformat(), "outcome": "will_excuse"},
        )

        assert response.status_code == 302 and response.url.endswith("#day-2026-09-13")
        contact = GuardianContact.objects.get(student=kids[0])
        assert (contact.absence_date, contact.outcome, contact.channel) == (
            SUNDAY,
            "will_excuse",
            "phone",
        )

    def test_one_press_on_a_kind_excuses_the_whole_run(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        for day in (WEDNESDAY, THURSDAY, NEXT_SUNDAY):
            _absent_day(school, klass, kids[0], teacher, supervisor, day=day)

        client_as(supervisor).post(
            reverse("wings:absence_file_excuse", args=[kids[0].id]),
            {
                "date_from": WEDNESDAY.isoformat(),
                "date_to": NEXT_SUNDAY.isoformat(),
                "kind": "medical",
                "document": _report(),
            },
        )

        excuse = AbsenceExcuse.objects.get(student=kids[0])
        assert (excuse.date_from, excuse.date_to, excuse.status) == (
            WEDNESDAY,
            NEXT_SUNDAY,
            "accepted",
        )
        assert excuse.rows.count() == 21

    def test_the_register_opens_the_file_from_the_name(
        self, client_as, school, seeded_calendar, klass, kids, teacher, supervisor
    ):
        from tests.test_period_register import _periods

        _periods(school, klass, teacher, 7)

        body = (
            client_as(supervisor)
            .get(reverse("wings:record_section", args=[klass.id]) + f"?date={SUNDAY.isoformat()}")
            .content.decode()
        )

        assert reverse("wings:absence_file", args=[kids[0].id]) in body
