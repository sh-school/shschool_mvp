"""قيدُ الطالب مدّةٌ: نقلُ منتصف الفصل لا يفقد غيابَ الطالب في أيٍّ من الشعبتين (W-20261004-027، D-201م).

«نقل الطالب يرحل معه كلّ شيء»: الغيابُ والمجاميعُ والتنبيهاتُ تتبع الطالبَ إلى شعبته الجديدة، وحصصُه القديمةُ تبقى
بشعبتها التاريخيّة، ولا سجلَّ يتيمٌ ولا مكرَّرٌ ولا محذوف. والقاعدةُ في `StudentEnrollment.objects.on_roll(day)`.
"""

import datetime as dt

import pytest

from core.models import StudentEnrollment
from operations.absence_standing import standing_for, unexcused_days_for_class
from operations.guardian_contact import awaiting_contact
from operations.models import Session, StudentAttendance
from operations.services.class_grid import GridNotFoundError, _roster_student
from student_affairs.internal_transfer import complete_internal
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, MONDAY, SUNDAY
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory
from wings.ministry_selectors import ministry_summary

pytestmark = pytest.mark.django_db

TUESDAY = MONDAY + dt.timedelta(days=1)


@pytest.fixture
def klass2(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


def _periods(school, klass, teacher, day):
    return [
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=day,
            start_time=start,
            end_time=end,
            status="scheduled",
        )
        for start, end in ((dt.time(7, 10), dt.time(7, 55)), (dt.time(8, 0), dt.time(8, 45)))
    ]


def _transfer(school, kid, target, actor, date=MONDAY):
    transfer = StudentTransfer.objects.create(
        school=school,
        student=kid,
        direction="internal",
        other_school_name=school.name,
        to_class_group=target,
        transfer_date=date,
        status="approved",
        academic_year="2026-2027",
        created_by=actor,
        updated_by=actor,
    )
    complete_internal(transfer, actor)
    return transfer


@pytest.fixture
def moved(school, kid, klass, klass2, teacher, other_teacher, holder, monkeypatch):
    """طالبٌ غاب الحصّتين بلا عذرٍ في الأحد من شعبته الأولى ثمّ انتقل إلى الثانية يوم الإثنين."""
    # أيّامُ الفرضيّة ثابتة في الماضي، فنرفع نافذة الرجوع هنا — والنافذةُ نفسُها مُختبَرةٌ في test_internal_transfer.
    monkeypatch.setattr("student_affairs.internal_transfer.MAX_BACKDATE_DAYS", 100_000)
    sunday_a = _periods(school, klass, teacher, SUNDAY)
    _periods(school, klass2, other_teacher, SUNDAY)
    monday_b = _periods(school, klass2, other_teacher, MONDAY)
    marks = [
        StudentAttendance.objects.create(school=school, session=s, student=kid, status="absent")
        for s in sunday_a
    ]
    _transfer(school, kid, klass2, holder)
    marks += [
        StudentAttendance.objects.create(school=school, session=s, student=kid, status="present")
        for s in monday_b
    ]
    return kid, marks


# ── القارئ: مدّةٌ لا حالة ──


def test_the_enrollment_reader_follows_the_boundary_day(school, moved, klass, klass2):
    """اليومُ الحدّيّ: آخرُ يومٍ في القديمة (الأحد = left_at) وأوّلُ يومٍ في الجديدة (الإثنين = يوم النقل)."""
    kid, _ = moved

    def classes_on(day):
        return set(
            StudentEnrollment.objects.filter(student=kid)
            .on_roll(day)
            .values_list("class_group_id", flat=True)
        )

    assert classes_on(SUNDAY) == {klass.pk}
    assert classes_on(MONDAY) == {klass2.pk}
    assert classes_on(TUESDAY) == {klass2.pk}
    assert classes_on(SUNDAY - dt.timedelta(days=1)) == {klass.pk}


def test_the_transfer_closes_the_old_enrollment_and_deletes_nothing(school, moved, klass, klass2):
    kid, _ = moved

    old = StudentEnrollment.objects.get(student=kid, class_group=klass)
    new = StudentEnrollment.objects.get(student=kid, class_group=klass2)
    assert (old.is_active, old.left_at) == (False, SUNDAY)
    assert (new.is_active, new.left_at, new.enrolled_at) == (True, None, MONDAY)
    assert StudentEnrollment.objects.filter(student=kid).count() == 2


def test_a_closed_enrollment_without_a_known_end_is_outside_any_day(school, klass, klass2):
    """مغلقٌ بلا `left_at` لا يُخمَّن مدّتُه فلا يسري على يومٍ بعينه (دلالة `on_roll`)."""
    gone = UserFactory(full_name="مغلقٌ قديم", national_id="29000001078")
    StudentEnrollmentFactory(
        student=gone, class_group=klass2, is_active=False, enrolled_at=ENROLLED
    )

    ids = set(StudentEnrollment.objects.on_roll(SUNDAY).values_list("student_id", flat=True))

    assert gone.pk not in ids


# ── القبول: ما يرحل مع الطالب ──


def test_the_new_section_sees_the_whole_absence_record_of_the_moved_student(
    school, seeded_calendar, moved, klass, klass2
):
    kid, _ = moved

    assert unexcused_days_for_class(klass2, school, TUESDAY).get(kid.pk) == 1
    assert unexcused_days_for_class(klass, school, TUESDAY).get(kid.pk) is None
    assert standing_for(kid, school, "G7", on=TUESDAY).unexcused_days == 1


def test_the_guardian_notice_follows_the_student_to_the_new_section(
    school, seeded_calendar, moved, klass, klass2
):
    kid, _ = moved

    assert awaiting_contact(klass2, MONDAY) == {kid.pk: SUNDAY}
    assert kid.pk not in awaiting_contact(klass, MONDAY)


def test_the_ministry_row_counts_the_student_where_he_sat_that_day(school, moved, klass, klass2):
    kid, _ = moved

    summary = ministry_summary(school, SUNDAY)
    rows = {row.group.pk: row.counts for row in summary.class_rows}

    assert rows[klass.pk].enrolled == 1 and rows[klass.pk].absent_both_unexcused == 1
    assert rows[klass2.pk].enrolled == 0, "لم يكن في الثانية يومَ الأحد"
    assert ministry_summary(school, MONDAY).class_rows[1].counts.enrolled == 1


def test_the_class_grid_roster_is_the_class_of_that_day(school, moved, klass, klass2):
    kid, _ = moved

    assert _roster_student(klass, SUNDAY, kid.pk) == kid
    assert _roster_student(klass2, MONDAY, kid.pk) == kid
    for wrong_class, day in ((klass2, SUNDAY), (klass, MONDAY)):
        with pytest.raises(GridNotFoundError):
            _roster_student(wrong_class, day, kid.pk)


def test_old_sessions_stay_historical_and_nothing_is_orphaned_duplicated_or_deleted(
    school, moved, klass, klass2
):
    kid, marks = moved

    assert StudentAttendance.objects.filter(student=kid).count() == len(marks) == 4
    sunday = Session.objects.filter(date=SUNDAY, attendances__student=kid)
    assert {s.class_group_id for s in sunday} == {klass.pk}, "حصصُ الأحد بقيت بشعبتها القديمة"
    pairs = StudentAttendance.objects.filter(student=kid).values_list("session_id", "student_id")
    assert len(set(pairs)) == len(list(pairs)), "لا سجلَّ مكرَّر"
    assert not StudentAttendance.objects.filter(session__isnull=True).exists(), "لا سجلَّ يتيم"
