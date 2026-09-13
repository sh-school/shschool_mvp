"""[LEGAL] عدّادا التأخّر عن الحصّة — مرّاتٍ ودقائق، بالمادّة.

قرارُ المدرسة (2026-09-13): التأخّرُ عن الحصّة دخولٌ بعد **5 دقائق** من بدئها
(الدليلُ بلا رقم، ص5). والعدّادان يُحفظان بالمادّة لأنّهما يُربطان لاحقاً بالتحصيل.

الحرّاس:
- المرّةُ تُعدّ بعد الخمس لا عندها، والدقائقُ تُجمع ولو دونها.
- «متأخّر» بلا دقائق يُعدّ مرّةً ولا يُخترع له رقم.
- زوجُ الاختيار خانةٌ واحدة.
- الفصلُ والعامُ نافذتان منفصلتان.
"""

import datetime as dt

import pytest

from operations.absence_policy import PERIOD_RECORDING_GRACE_MINUTES, PERIOD_TARDY_AFTER_MINUTES
from operations.models import Session, StudentAttendance, Subject
from operations.tardiness import is_period_tardy, minutes_after_start, tardiness_for, tardiness_now

pytestmark = pytest.mark.django_db

DAY = dt.date(2026, 9, 14)


def test_the_school_decisions_are_five_minutes():
    assert PERIOD_TARDY_AFTER_MINUTES == 5
    assert PERIOD_RECORDING_GRACE_MINUTES == 5


@pytest.mark.parametrize(
    "minutes,tardy", [(None, False), (0, False), (5, False), (6, True), (30, True)]
)
def test_tardy_is_after_five_minutes_not_at_five(minutes, tardy):
    assert is_period_tardy(minutes) is tardy


def test_minutes_are_counted_from_the_start_of_the_period(school, class_group, teacher_user):
    session = Session(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        date=DAY,
        start_time=dt.time(9, 35),
        end_time=dt.time(10, 20),
    )
    assert minutes_after_start(session, dt.time(9, 47)) == 12
    assert minutes_after_start(session, dt.time(9, 30)) == 0, "لا دقائقَ سالبة"


@pytest.fixture
def math(school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def science(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


def _late(school, class_group, teacher, student, subject, at, minutes, day=DAY, elective=""):
    session = Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subject,
        date=day,
        start_time=at,
        end_time=(dt.datetime.combine(day, at) + dt.timedelta(minutes=45)).time(),
        status="scheduled",
        elective_group=elective,
    )
    StudentAttendance.objects.create(
        session=session, student=student, school=school, status="late", late_minutes=minutes
    )
    return session


def test_count_and_minutes_by_subject(
    school, class_group, teacher_user, student_user, math, science
):
    _late(school, class_group, teacher_user, student_user, math, dt.time(8, 0), 12)
    _late(school, class_group, teacher_user, student_user, math, dt.time(9, 0), 7)
    _late(school, class_group, teacher_user, student_user, science, dt.time(10, 0), 3)

    t = tardiness_for(student_user, school, DAY, DAY)

    assert (t.count, t.minutes, t.under_threshold) == (2, 22, 1)
    assert (t.by_subject["الرياضيات"].count, t.by_subject["الرياضيات"].minutes) == (2, 19)
    assert (t.by_subject["العلوم"].count, t.by_subject["العلوم"].minutes) == (0, 3)


def test_late_without_minutes_counts_once_and_adds_no_minutes(
    school, class_group, teacher_user, student_user, math
):
    _late(school, class_group, teacher_user, student_user, math, dt.time(8, 0), None)

    t = tardiness_for(student_user, school, DAY, DAY)

    assert (t.count, t.minutes, t.unmeasured) == (1, 0, 1)


def test_an_elective_pair_is_one_tardiness_not_two(
    school, class_group, teacher_user, student_user, math, science
):
    from tests.conftest import UserFactory

    other = UserFactory(full_name="معلّم الزوج")
    _late(
        school,
        class_group,
        teacher_user,
        student_user,
        math,
        dt.time(9, 35),
        9,
        elective="تكنولوجيا",
    )
    _late(school, class_group, other, student_user, science, dt.time(9, 35), 9, elective="فنون")

    t = tardiness_for(student_user, school, DAY, DAY)

    assert (t.count, t.minutes) == (1, 9)


def test_present_and_absent_records_are_not_tardiness(
    school, class_group, teacher_user, student_user, math
):
    session = _late(school, class_group, teacher_user, student_user, math, dt.time(8, 0), 20)
    StudentAttendance.objects.filter(session=session).update(status="present")

    assert tardiness_for(student_user, school, DAY, DAY).count == 0


def test_semester_and_year_are_separate_windows(
    school, seeded_calendar, class_group, teacher_user, student_user, math
):
    """تأخّرٌ في الفصل الأوّل وآخرُ في الثاني: الفصلُ يعدّ واحداً، والعامُ اثنين."""
    from core.academic_calendar import AcademicCalendar

    year = AcademicCalendar.current(school).year
    second = year.semesters.get(code="S2")
    in_second = second.start_date + dt.timedelta(days=5)
    in_first = second.start_date - dt.timedelta(days=3)
    _late(school, class_group, teacher_user, student_user, math, dt.time(8, 0), 10, day=in_first)
    _late(school, class_group, teacher_user, student_user, math, dt.time(8, 0), 8, day=in_second)

    counters = tardiness_now(student_user, school, in_second)

    assert (counters["semester"].count, counters["semester"].minutes) == (1, 8)
    assert (counters["year"].count, counters["year"].minutes) == (2, 18)
