"""يومُ الإجازة ليس يومَ دوام — ولو وقع ثلاثاءً.

كانت لوحةُ مشرف الجناح وفهرسُ الرصد وشاشةُ الطوابق تسأل الأسبوعَ وحدَه
(`bells.day_type_for`)، ومهلةُ العذر تسأل تقويمَ الوزارة. فإجازةٌ رسميّةٌ يومَ ثلاثاء
عُرضت يومَ دوامٍ بشُعبها كلِّها «لم تُرصد»، وجرسُها يرنّ في شاشة الطوابق.
والسؤالُ الآن واحدٌ في `operations.school_days`، ومهلةُ العذر تسأله هو أيضاً.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import AcademicYear, CalendarEvent, WingCoverage
from operations.absence_file import _SchoolDays
from operations.excuses import _grace_after
from operations.school_days import (
    NOT_YET_OPEN,
    WEEKEND,
    SchoolDays,
    is_school_day,
    school_day,
    student_grade,
)
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _periods,
    kids,
    klass,
    supervisor,
    teacher,
    year,
)
from tests.test_wings_screen import built, leader  # noqa: F401
from wings.services import floors_overview

pytestmark = pytest.mark.django_db

MONDAY = SUNDAY + dt.timedelta(days=1)
TUESDAY = SUNDAY + dt.timedelta(days=2)
WEDNESDAY = SUNDAY + dt.timedelta(days=3)
THURSDAY = SUNDAY + dt.timedelta(days=4)
FRIDAY = SUNDAY + dt.timedelta(days=5)
HOLIDAY = "إجازةٌ رسميّةٌ للاختبار"


@pytest.fixture(autouse=True)
def on_tuesday(monkeypatch):
    """الساعةُ 9:45 من الثلاثاء بتوقيت المدرسة — قبل أيّ تجهيزٍ يسأل عن العام."""
    frozen = timezone.make_aware(dt.datetime.combine(TUESDAY, dt.time(9, 45)))
    monkeypatch.setattr("django.utils.timezone.now", lambda: frozen)


def _break(school, name=HOLIDAY, audience="both", day=TUESDAY, grade_scope="all"):
    academic_year = AcademicYear.objects.get(school=school, start_date__lte=day, end_date__gte=day)
    return CalendarEvent.objects.create(
        academic_year=academic_year,
        event_type="break",
        name=name,
        start_date=day,
        end_date=day,
        audience=audience,
        grade_scope=grade_scope,
    )


@pytest.fixture
def holiday(school, seeded_calendar):
    return _break(school)


class TestTheDay:
    def test_a_tuesday_holiday_is_not_a_school_day(self, school, holiday):
        day = school_day(school, TUESDAY)

        assert day.day_type == "regular", "الأسبوعُ وحدَه يراه يومَ دوام"
        assert not day.is_open
        assert day.holiday == HOLIDAY
        assert day.closed_reason == HOLIDAY
        assert day.bell_day_type == ""
        assert not is_school_day(school, TUESDAY)

    def test_the_days_around_it_stay_open(self, school, holiday):
        assert school_day(school, MONDAY).is_open
        assert is_school_day(school, WEDNESDAY)

    def test_a_staff_only_break_keeps_the_students_in_class(self, school, seeded_calendar):
        _break(school, name="إجازةُ الموظفين", audience="staff")

        assert school_day(school, TUESDAY).is_open
        assert is_school_day(school, TUESDAY)

    def test_the_weekend_is_closed_without_a_holiday(self, school, seeded_calendar):
        day = school_day(school, FRIDAY)

        assert not day.is_open
        assert day.holiday == ""
        assert day.closed_reason == WEEKEND

    def test_the_excuse_grace_and_the_absence_file_skip_the_same_holiday(self, school, holiday):
        """مهلةُ العذر يومان دراسيّان بعد العودة: عودةُ الإثنين تُغلق الخميسَ لا الأربعاء."""
        assert _grace_after(school, MONDAY) == THURSDAY
        assert _SchoolDays(school, SUNDAY, FRIDAY).grace_after(MONDAY) == THURSDAY


class TestTheSupervisorScreens:
    def test_the_supervisors_home_page_names_the_holiday_and_lists_no_section(
        self, client_as, school, holiday, klass, kids, teacher, supervisor
    ):
        # حصصُ الثلاثاء موجودة — تُولَّد للأسبوع كلِّه دفعةً واحدة.
        _periods(school, klass, teacher, 7, day=TUESDAY)

        body = client_as(supervisor).get(reverse("dashboard")).content.decode()

        assert f"اليوم — {HOLIDAY}: لا دوامَ فيه، فلا رصد." in body
        assert reverse("wings:record_section", args=[klass.id]) not in body
        assert 'class="per-dot' not in body
        assert "لا جناحَ مُسنَدٌ إليك" not in body

    def test_the_record_index_names_the_holiday_on_its_date_only(
        self, client_as, school, holiday, klass, kids, teacher, supervisor
    ):
        _periods(school, klass, teacher, 7, day=WEDNESDAY)
        client = client_as(supervisor)
        index = reverse("wings:record_index")
        section = reverse("wings:record_section", args=[klass.id])

        closed = client.get(f"{index}?date={TUESDAY.isoformat()}").content.decode()
        opened = client.get(f"{index}?date={WEDNESDAY.isoformat()}").content.decode()

        assert HOLIDAY in closed
        assert section not in closed
        assert HOLIDAY not in opened
        assert section in opened
        assert opened.count('class="per-dot') == 7

    def test_the_substitutes_home_page_names_the_holiday(
        self, client_as, school, holiday, klass, supervisor
    ):
        substitute = UserFactory(full_name="ملاحظ الطلبة", national_id="29300000093")
        MembershipFactory(
            user=substitute,
            school=school,
            role=RoleFactory(school=school, name="student_observer"),
        )
        WingCoverage.objects.create(
            wing=klass.wing, substitute=substitute, assigned_by=supervisor, start_date=TUESDAY
        )

        body = client_as(substitute).get(reverse("dashboard")).content.decode()

        assert "رصد الغياب — جناحي اليوم" in body
        assert HOLIDAY in body
        assert reverse("wings:record_section", args=[klass.id]) not in body


class TestTheFloors:
    def test_no_bell_rings_on_the_holiday(self, school, year, built, holiday):
        panels = floors_overview(school, year, timezone.localtime())

        assert all(panel.bells == [] for panel in panels)
        assert all(card.positions == [] for panel in panels for card in panel.wings)

    def test_the_bells_ring_the_day_after(self, school, year, built, holiday):
        after = timezone.make_aware(dt.datetime.combine(WEDNESDAY, dt.time(9, 45)))

        panels = floors_overview(school, year, after)

        assert any(card.positions for panel in panels for card in panel.wings)

    def test_the_page_names_the_holiday_and_shows_no_clock(
        self, client_as, school, built, leader, holiday
    ):
        body = client_as(leader).get(reverse("wings:floors")).content.decode()

        assert HOLIDAY in body
        assert "لا جرسَ يرنّ" in body
        assert "الساعة 09:45" not in body


class TestTheGradeScopeNarrowsTheBreak:
    """إجازةٌ نطاقُها صفٌّ بعينه لا تُغلق يومَ طالبٍ في صفٍّ آخر. ولوحةُ الجناح — بلا صفٍّ
    واحد تسندها — تبقى تُغلق بأيّ نطاق، كما كانت."""

    def test_a_twelfth_grade_break_closes_only_for_that_grade(self, school, seeded_calendar):
        _break(school, name="اختبارُ قبولٍ — الثاني عشر", grade_scope="g12")

        assert not school_day(school, TUESDAY, grade="G12").is_open
        assert school_day(school, TUESDAY, grade="G7").is_open
        assert not is_school_day(school, TUESDAY, grade="G12")
        assert is_school_day(school, TUESDAY, grade="G7")

    def test_the_wing_dashboard_still_closes_for_any_scope(self, school, seeded_calendar):
        """جناحٌ فيه تاسعٌ وعاشر معاً — فإجازةُ صفٍّ واحدٍ منهما تُغلقه، لا تُقسّمه."""
        _break(school, name="اختبارُ قبولٍ — الثاني عشر", grade_scope="g12")

        assert not school_day(school, TUESDAY).is_open


class TestStudentGradeResolvesTheEnrollment:
    def test_an_enrolled_student_carries_his_class_grade(self, school, year):
        klass = ClassGroupFactory(school=school, grade="G9", section="1", academic_year=year)
        student = UserFactory(full_name="طالبٌ في التاسع")
        StudentEnrollmentFactory(student=student, class_group=klass)

        assert student_grade(student, school) == "G9"

    def test_an_unenrolled_user_has_no_grade(self, school):
        stranger = UserFactory(full_name="بلا قيد")

        assert student_grade(stranger, school) is None


class TestTheExcuseDeadlineRespectsTheGradeScope:
    """مهلةُ العذر يومان دراسيّان — وإجازةُ صفٍّ واحدٍ لا تمدّها لطالبٍ في صفٍّ آخر."""

    def test_a_twelfth_grade_break_extends_the_deadline_only_for_that_grade(
        self, school, seeded_calendar, year
    ):
        _break(school, name="اختبارُ قبولٍ — الثاني عشر", grade_scope="g12", day=WEDNESDAY)

        g12 = ClassGroupFactory(school=school, grade="G12", section="1", academic_year=year)
        g7 = ClassGroupFactory(school=school, grade="G7", section="1", academic_year=year)
        senior = UserFactory(full_name="طالبٌ في الثاني عشر")
        junior = UserFactory(full_name="طالبٌ في السابع")
        StudentEnrollmentFactory(student=senior, class_group=g12)
        StudentEnrollmentFactory(student=junior, class_group=g7)

        # الاثنينُ يومُ العودة: الثلاثاءُ دراسيٌّ للاثنين، والأربعاءُ — إجازةُ الثاني عشر
        # وحده — دراسيٌّ للسابع فقط. فمهلةُ السابع تُغلق الأربعاءَ ومهلةُ الثاني عشر
        # تتخطّاه إلى الخميس.
        senior_grade = student_grade(senior, school)
        junior_grade = student_grade(junior, school)

        assert _grace_after(school, MONDAY, junior_grade) == WEDNESDAY
        assert _grace_after(school, MONDAY, senior_grade) == THURSDAY


class TestBeforeStudentsStart:
    """أسبوعُ الدور الثاني وبدء دوام الموظفين — قبل `students_start` فلا دوامَ طلبةٍ فيهما.

    تقويمُ 2026-2027 المبذور: `staff_start` و`second_round` في 2026-08-23،
    و`students_start` في 2026-08-30 — أحدٌ يفتح الأسبوع."""

    SECOND_ROUND_TUESDAY = dt.date(2026, 8, 25)
    STUDENTS_START = dt.date(2026, 8, 30)

    def test_the_second_round_week_is_not_a_school_day(self, school, seeded_calendar):
        day = school_day(school, self.SECOND_ROUND_TUESDAY)

        assert day.day_type == "regular", "الأسبوعُ وحدَه يراه يومَ دوام"
        assert not day.is_open
        assert day.holiday == NOT_YET_OPEN
        assert day.closed_reason == NOT_YET_OPEN
        assert day.bell_day_type == ""
        assert not is_school_day(school, self.SECOND_ROUND_TUESDAY)

    def test_students_start_day_is_open(self, school, seeded_calendar):
        assert school_day(school, self.STUDENTS_START).is_open
        assert is_school_day(school, self.STUDENTS_START)

    def test_the_school_days_window_agrees(self, school, seeded_calendar):
        days = SchoolDays(school, dt.date(2026, 8, 23), dt.date(2026, 9, 3))

        assert self.SECOND_ROUND_TUESDAY not in days
        assert self.STUDENTS_START in days

    def test_a_holiday_reason_wins_over_not_yet_open(self, school, seeded_calendar):
        """لو وقعت إجازةٌ في الأسبوع نفسه فاسمُها هو السبب — لا «لم يبدأ الدوام»."""
        academic_year = AcademicYear.objects.get(
            school=school,
            start_date__lte=self.SECOND_ROUND_TUESDAY,
            end_date__gte=self.SECOND_ROUND_TUESDAY,
        )
        CalendarEvent.objects.create(
            academic_year=academic_year,
            event_type="break",
            name=HOLIDAY,
            start_date=self.SECOND_ROUND_TUESDAY,
            end_date=self.SECOND_ROUND_TUESDAY,
            audience="both",
        )

        assert school_day(school, self.SECOND_ROUND_TUESDAY).holiday == HOLIDAY
