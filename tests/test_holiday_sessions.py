"""إجازةُ الطلبة يومَ ثلاثاء لا تُولَّد لها حصص.

كان `ensure_sessions_for_date` يولّد الأسبوعَ كلَّه من الأحد إلى الخميس ولا يقرأ
التقويم، فالإجازةُ الرسميّةُ وسطَ الأسبوع تنال حصصَ جدولها كاملةً ما دام أحدٌ
فتح شاشةً في أسبوعها. والحكمُ هنا من `operations.school_days` وحدَه.

وما وُلّد قبل أن تُعلَن الإجازةُ يُحذف إن لم يمسّه أحد (قرار 2026-09-16) — حين
تُحفظ الإجازة، وفي المصالحة بالأمر وعند اعتماد الجدول.
"""

import datetime as dt
from datetime import date, timedelta

import pytest
from django.core.management import call_command

from core.models import AcademicYear, CalendarEvent, ClassGroup
from operations.models import (
    ClassExit,
    ScheduleSlot,
    Session,
    StudentAttendance,
    Subject,
)
from operations.services import ScheduleService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"
SUNDAY = date(2026, 11, 1)
TUESDAY = SUNDAY + timedelta(days=2)
THURSDAY = SUNDAY + timedelta(days=4)
WEEK = [SUNDAY + timedelta(days=i) for i in range(5)]


@pytest.fixture
def year(school):
    return AcademicYear.objects.create(
        school=school, name=YEAR, start_date=date(2026, 8, 23), end_date=date(2027, 6, 24)
    )


@pytest.fixture
def timetable(school):
    """حصّةٌ أولى كلَّ يومٍ من الأحد (0) إلى الخميس (4) — خمسُ جلساتٍ للأسبوع."""
    teacher = UserFactory(full_name="معلّمُ الأسبوع")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    cg = ClassGroup.objects.create(school=school, grade="G8", section="1", academic_year=YEAR)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات")
    for day in range(5):
        ScheduleSlot.objects.create(
            school=school,
            teacher=teacher,
            class_group=cg,
            subject=subject,
            day_of_week=day,
            period_number=1,
            start_time=dt.time(7, 10),
            end_time=dt.time(7, 55),
            academic_year=YEAR,
        )
    return cg


def _break(year, start, end=None, audience="both", name="إجازة رسميّة"):
    return CalendarEvent.objects.create(
        academic_year=year,
        event_type="break",
        name=name,
        start_date=start,
        end_date=end or start,
        audience=audience,
    )


def _dates(school):
    return sorted(set(Session.objects.filter(school=school).values_list("date", flat=True)))


@pytest.mark.django_db
class TestEnsureSkipsStudentHolidays:
    def test_holiday_tuesday_gets_no_sessions_and_the_rest_of_the_week_does(
        self, school, year, timetable
    ):
        _break(year, TUESDAY)

        created = ScheduleService.ensure_sessions_for_date(school, TUESDAY, academic_year=YEAR)

        assert created == 4
        assert _dates(school) == [d for d in WEEK if d != TUESDAY]

    @pytest.mark.parametrize("audience", ["both", "students"])
    def test_a_break_for_students_closes_the_day(self, school, year, timetable, audience):
        _break(year, TUESDAY, audience=audience)

        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert TUESDAY not in _dates(school)

    def test_a_staff_only_break_is_a_school_day_for_students(self, school, year, timetable):
        _break(year, TUESDAY, audience="staff", name="إجازة الموظفين")

        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert _dates(school) == WEEK

    def test_another_schools_holiday_does_not_close_this_school(self, school, year, timetable):
        from tests.conftest import SchoolFactory

        other = SchoolFactory()
        other_year = AcademicYear.objects.create(
            school=other, name=YEAR, start_date=year.start_date, end_date=year.end_date
        )
        _break(other_year, TUESDAY)

        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert TUESDAY in _dates(school)

    def test_a_break_across_the_weekend_closes_only_its_weekdays(self, school, year, timetable):
        # الأربعاءُ إلى الأحد التالي: الخميسُ داخلها، والأحدُ خارج أسبوعنا.
        _break(year, TUESDAY + timedelta(days=1), THURSDAY + timedelta(days=3))

        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert _dates(school) == WEEK[:3]

    def test_a_holiday_week_creates_nothing_and_never_reads_the_timetable(
        self, school, year, timetable, django_assert_num_queries
    ):
        _break(year, SUNDAY, THURSDAY, name="إجازة منتصف الفصل الأول")

        # الجلساتُ القائمة، ثمّ إجازاتُ الأسبوع — ولا حاجةَ بعدهما إلى الحصص.
        with django_assert_num_queries(2):
            created = ScheduleService.ensure_sessions_for_date(school, TUESDAY, academic_year=YEAR)

        assert created == 0
        assert _dates(school) == []

    def test_calling_again_creates_nothing_and_reads_the_calendar_once(
        self, school, year, timetable, django_assert_num_queries
    ):
        _break(year, TUESDAY)
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        # يومُ الإجازة لا يصير «موجوداً»، فالأسبوعُ يسأل التقويمَ مرّةً — لا يوماً يوماً.
        with django_assert_num_queries(2):
            again = ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert again == 0
        assert Session.objects.filter(school=school).count() == 4

    def test_a_week_without_holidays_that_is_complete_skips_the_calendar(
        self, school, year, timetable, django_assert_num_queries
    ):
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        with django_assert_num_queries(1):
            again = ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert again == 0

    def test_a_cancelled_holiday_is_filled_on_the_next_call(self, school, year, timetable):
        holiday = _break(year, TUESDAY)
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)
        holiday.delete()

        created = ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert created == 1
        assert _dates(school) == WEEK


def _generated_week(school):
    """أسبوعٌ وُلّد قبل أن تُعلَن الإجازة — الحالُ التي يعالجها الحذف."""
    ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)
    assert _dates(school) == WEEK
    return Session.objects.get(school=school, date=TUESDAY)


def _touch_with_attendance(session):
    StudentAttendance.objects.create(
        session=session, student=UserFactory(), school=session.school, status="present"
    )


def _touch_with_class_exit(session):
    from django.utils import timezone

    ClassExit.objects.create(
        school=session.school, session=session, student=UserFactory(), left_at=timezone.now()
    )


def _touch_with_infraction(session):
    from tests.conftest import BehaviorInfractionFactory

    BehaviorInfractionFactory(school=session.school, session=session)


def _touch_with_swap(session):
    session.original_teacher = UserFactory()
    session.save(update_fields=["original_teacher"])


def _touch_with_status(session):
    session.status = "completed"
    session.save(update_fields=["status"])


TOUCHES = [
    _touch_with_attendance,
    _touch_with_class_exit,
    _touch_with_infraction,
    _touch_with_swap,
    _touch_with_status,
]


@pytest.mark.django_db
class TestSavingABreakClearsItsSessions:
    def test_an_untouched_holiday_session_is_deleted_when_the_break_is_saved(
        self, school, year, timetable
    ):
        _generated_week(school)

        _break(year, TUESDAY, name="إجازة طارئة")

        assert _dates(school) == [d for d in WEEK if d != TUESDAY]

    @pytest.mark.parametrize("touch", TOUCHES, ids=lambda f: f.__name__.removeprefix("_touch_"))
    def test_a_touched_holiday_session_is_kept(self, school, year, timetable, touch):
        session = _generated_week(school)
        touch(session)

        _break(year, TUESDAY)

        assert Session.objects.filter(id=session.id).exists()

    def test_the_rule_counts_what_it_keeps(self, school, year, timetable):
        session = _generated_week(school)
        _touch_with_attendance(session)
        # الإجازةُ في التقويم قبل الحذف: الحكمُ يقرأ المحفوظ.
        CalendarEvent.objects.bulk_create(
            [
                CalendarEvent(
                    academic_year=year,
                    event_type="break",
                    name="إجازة",
                    start_date=SUNDAY,
                    end_date=THURSDAY,
                )
            ]
        )

        result = ScheduleService.clear_holiday_sessions(school, SUNDAY, THURSDAY)

        assert result == {"deleted": 4, "kept": 1}
        assert list(Session.objects.filter(school=school)) == [session]

    def test_a_staff_only_break_deletes_nothing(self, school, year, timetable):
        _generated_week(school)

        _break(year, TUESDAY, audience="staff", name="إجازة الموظفين")

        assert _dates(school) == WEEK

    def test_another_kind_of_event_deletes_nothing(self, school, year, timetable):
        _generated_week(school)

        CalendarEvent.objects.create(
            academic_year=year,
            event_type="midterm_exam",
            name="اختبارات منتصف الفصل",
            start_date=TUESDAY,
            end_date=TUESDAY,
        )

        assert _dates(school) == WEEK

    def test_another_schools_sessions_are_not_touched(self, school, year, timetable):
        from tests.conftest import SchoolFactory

        _generated_week(school)
        other = SchoolFactory()
        other_year = AcademicYear.objects.create(
            school=other, name=YEAR, start_date=year.start_date, end_date=year.end_date
        )

        _break(other_year, TUESDAY)

        assert _dates(school) == WEEK

    def test_a_future_break_with_no_sessions_costs_one_query(
        self, school, year, django_assert_num_queries
    ):
        with django_assert_num_queries(1):
            result = ScheduleService.clear_holiday_sessions(school, TUESDAY, TUESDAY)

        assert result == {"deleted": 0, "kept": 0}

    def test_the_days_come_back_when_the_break_is_removed(self, school, year, timetable):
        _generated_week(school)
        holiday = _break(year, TUESDAY)
        assert TUESDAY not in _dates(school)

        holiday.delete()
        ScheduleService.ensure_sessions_for_date(school, SUNDAY, academic_year=YEAR)

        assert _dates(school) == WEEK


@pytest.mark.django_db
class TestResyncOnAHoliday:
    def _silent_break(self, year, start, end=None):
        """إجازةٌ بلا مستقبِل — لتبقى جلساتُها حتى تبلغها المصالحة."""
        CalendarEvent.objects.bulk_create(
            [
                CalendarEvent(
                    academic_year=year,
                    event_type="break",
                    name="إجازة",
                    start_date=start,
                    end_date=end or start,
                )
            ]
        )

    def test_resync_creates_nothing_on_a_holiday(self, school, year, timetable):
        _break(year, TUESDAY)

        result = ScheduleService.resync_sessions_for_date(school, TUESDAY, academic_year=YEAR)

        assert result == {"deleted": 0, "created": 0, "kept": 0}
        assert _dates(school) == []

    def test_resync_deletes_untouched_holiday_sessions_and_keeps_the_rest(
        self, school, year, timetable
    ):
        session = _generated_week(school)
        teacher = session.teacher
        touched = Session.objects.create(
            school=school,
            teacher=teacher,
            class_group=session.class_group,
            subject=session.subject,
            date=TUESDAY,
            start_time=dt.time(8, 0),
            end_time=dt.time(8, 45),
        )
        _touch_with_attendance(touched)
        self._silent_break(year, TUESDAY)

        result = ScheduleService.resync_sessions_for_date(school, TUESDAY, academic_year=YEAR)

        assert result == {"deleted": 1, "created": 0, "kept": 1}
        assert list(Session.objects.filter(date=TUESDAY)) == [touched]

    def test_approving_a_schedule_reads_the_calendar_once_for_the_week(
        self, school, year, timetable, monkeypatch, django_assert_max_num_queries
    ):
        from django.utils import timezone

        monkeypatch.setattr(timezone, "localdate", lambda *a, **k: TUESDAY)
        _generated_week(school)
        self._silent_break(year, TUESDAY)

        with django_assert_max_num_queries(30) as captured:
            result = ScheduleService.resync_current_week(school, YEAR)

        calendar_reads = [q for q in captured.captured_queries if "core_calendarevent" in q["sql"]]
        assert len(calendar_reads) == 1
        assert result == {"deleted": 1, "created": 0, "kept": 0}
        assert _dates(school) == [d for d in WEEK if d != TUESDAY]

    def test_the_command_clears_a_holiday_and_dry_run_writes_nothing(self, school, year, timetable):
        from io import StringIO

        _generated_week(school)
        self._silent_break(year, TUESDAY)
        args = ("resync_sessions", "--from", str(SUNDAY), "--to", str(THURSDAY))

        call_command(*args, "--dry-run", stdout=StringIO())
        assert _dates(school) == WEEK

        out = StringIO()
        call_command(*args, stdout=out)
        assert f"{TUESDAY}: deleted=1 created=0 kept=0" in out.getvalue()
        assert _dates(school) == [d for d in WEEK if d != TUESDAY]
