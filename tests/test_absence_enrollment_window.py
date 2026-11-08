"""إحصاءُ الغياب يستبعد ما قبل القيد وما بعد المغادرة، ويعلّم الجديدَ والمنقول (W-20261108-015).

المصدرُ المركزيّ `StudentEnrollment.objects.on_roll(day)`؛ والعلامةُ من `student_affairs.enrolment_marks`.
"""

import datetime as dt

import pytest

from core.models import StudentEnrollment
from operations.models import Session, StudentAttendance
from student_affairs.enrolment_marks import MARK_MOVED, MARK_NEW, enrolment_marks
from student_affairs.services import StudentService
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import MONDAY, SUNDAY
from tests.conftest import StudentEnrollmentFactory, UserFactory
from wings.ministry_selectors import ministry_summary

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _absent_both(school, klass, teacher, student, day):
    """طالبٌ غائبٌ في الحصّتين الأولى والثانية من `day`."""
    for start, end in ((dt.time(7, 10), dt.time(7, 55)), (dt.time(8, 0), dt.time(8, 45))):
        session = Session.objects.get_or_create(
            school=school,
            class_group=klass,
            date=day,
            start_time=start,
            defaults={"teacher": teacher, "end_time": end, "status": "scheduled"},
        )[0]
        StudentAttendance.objects.create(
            school=school, session=session, student=student, status="absent"
        )


def _student(klass, national_id, enrolled_at, **extra):
    student = UserFactory(full_name=f"طالب {national_id[-1]}", national_id=national_id)
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=enrolled_at, **extra)
    return student


def test_student_enrolled_later_is_not_counted_on_earlier_days(school, klass, teacher):
    late = _student(klass, "29000009001", MONDAY)
    _absent_both(school, klass, teacher, late, SUNDAY)
    before = ministry_summary(school, SUNDAY)
    after = ministry_summary(school, MONDAY)
    assert before.total.enrolled == 0 and before.total.absent_both == 0
    assert after.total.enrolled == 1


def test_student_who_left_is_counted_up_to_last_day_only(school, klass, teacher):
    gone = _student(
        klass,
        "29000009002",
        dt.date(2026, 8, 1),
        is_active=False,
        left_at=SUNDAY,
    )
    _absent_both(school, klass, teacher, gone, SUNDAY)
    on_last_day = ministry_summary(school, SUNDAY)
    after = ministry_summary(school, MONDAY)
    assert (on_last_day.total.enrolled, on_last_day.total.absent_both) == (1, 1)
    assert after.total.enrolled == 0


def test_deactivating_a_student_stamps_the_last_day(school, klass, holder):
    kid = _student(klass, "29000009003", dt.date(2026, 8, 1))
    StudentService.deactivate_student(kid, school, holder)
    row = StudentEnrollment.objects.get(student=kid)
    assert row.is_active is False and row.left_at is not None


def test_new_and_moved_marks_sit_beside_the_name(school, klass, teacher):
    old = _student(klass, "29000009004", dt.date(2026, 8, 1))
    fresh = _student(klass, "29000009005", MONDAY)
    moved_in = _student(klass, "29000009006", MONDAY - dt.timedelta(days=3))
    StudentEnrollmentFactory(
        student=moved_in,
        class_group=klass,
        enrolled_at=dt.date(2026, 8, 1),
        is_active=False,
        left_at=MONDAY - dt.timedelta(days=4),
    )
    marks = enrolment_marks(school, [old.id, fresh.id, moved_in.id], MONDAY)
    assert old.id not in marks
    assert marks[fresh.id] == MARK_NEW
    assert marks[moved_in.id] == MARK_MOVED
    _absent_both(school, klass, teacher, fresh, MONDAY)
    item = ministry_summary(school, MONDAY).ministered[0]
    assert item.mark == MARK_NEW
