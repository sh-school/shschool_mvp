"""[DASHBOARD] مُجمِّعُ يوم المدرسة للمدير (W-20261008-004، D-249م وD-251م وD-257م).

الطالبُ يُعدّ مرّةً واحدة مهما تعدّدت صفوفُه، والحكمُ `_judge` نفسُه، والاستعلاماتُ ثابتةٌ مهما كثر الطلاب،
ولا اسمَ ولا رقمَ شخصيّاً في الحمولة. ما لا يُقاس هنا: الإنتاجُ والذاكرة (يقيسها 0701 بعد الدمج).
"""

import datetime as dt
import json

import pytest

from core.models.academic import StudentEnrollment
from operations.day_selectors import (
    PHASE_CLOSED,
    PHASE_FINAL,
    PHASE_LIVE,
    school_day_summary,
)
from operations.models import PeriodConfirmation, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SATURDAY, SUNDAY, at
from tests.conftest import MembershipFactory, RoleFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

SLOTS = (
    (dt.time(7, 10), dt.time(7, 55)),
    (dt.time(8, 0), dt.time(8, 45)),
    (dt.time(12, 45), dt.time(13, 30)),
)


def _students(school, klass, count, start=1):
    out = []
    for i in range(start, start + count):
        user = UserFactory(full_name=f"طالب {i}", national_id=f"2900000{i:04d}")
        StudentEnrollmentFactory(student=user, class_group=klass, enrolled_at=ENROLLED)
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
        out.append(user)
    return out


def _sessions(school, klass, teacher, day=SUNDAY, provisional=False, slots=SLOTS):
    return [
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            date=day,
            start_time=start,
            end_time=end,
            status="scheduled",
            provisional=provisional,
        )
        for start, end in slots
    ]


def _mark(school, session, student, status, excuse="", whereabouts=""):
    return StudentAttendance.objects.create(
        school=school,
        session=session,
        student=student,
        status=status,
        excuse_type=excuse,
        whereabouts=whereabouts,
    )


def test_a_student_is_counted_once_however_many_rows_they_have(school, klass, teacher, bells):
    sessions = _sessions(school, klass, teacher)
    a, b, c = _students(school, klass, 3)
    for student in (a, b, c):
        for session in sessions:
            _mark(school, session, student, "present")

    summary = school_day_summary(school, SUNDAY, now=at(14, 30))

    assert summary.phase == PHASE_FINAL
    assert summary.school.students == 3
    assert summary.school.present == 3  # لا تسعةَ صفوف


def test_the_five_verdicts_are_separate_and_unrecorded_is_not_absent(school, klass, teacher, bells):
    sessions = _sessions(school, klass, teacher)
    present, absent, excused, partial, nothing = _students(school, klass, 5)
    for session in sessions:
        _mark(school, session, present, "present")
        _mark(school, session, absent, "absent")
        _mark(school, session, excused, "absent", excuse="medical")
    _mark(school, sessions[0], partial, "present")  # رصدٌ ناقص: ما حضره مع غير المرصود يبلغ الحدّ

    c = school_day_summary(school, SUNDAY, now=at(14, 30)).school

    assert (c.present, c.absent_unexcused, c.absent_excused, c.incomplete, c.unrecorded) == (
        1,
        1,
        1,
        1,
        1,
    )
    assert c.students == 5


def test_before_two_oclock_the_headline_is_early_absence_not_a_verdict(
    school, klass, teacher, bells
):
    sessions = _sessions(school, klass, teacher)
    early, late_only = _students(school, klass, 2)
    _mark(school, sessions[0], early, "absent")
    _mark(school, sessions[1], early, "absent")
    _mark(school, sessions[0], late_only, "absent")

    summary = school_day_summary(school, SUNDAY, now=at(9, 0))

    assert summary.phase == PHASE_LIVE
    assert summary.school.early_absent == 1  # غائبٌ عن الخانتين معاً وحده


def test_a_closed_day_returns_an_empty_closed_summary(school, klass, teacher, bells):
    summary = school_day_summary(school, SATURDAY, now=at(10, 0, day=SATURDAY))

    assert summary.phase == PHASE_CLOSED
    assert summary.school.students == 0


def test_provisional_sessions_count_in_the_verdict_but_not_in_the_bell_slots(
    school, klass, teacher, bells
):
    _sessions(school, klass, teacher)
    _sessions(school, klass, teacher, provisional=True, slots=((dt.time(9, 0), dt.time(9, 45)),))

    summary = school_day_summary(school, SUNDAY, now=at(14, 30))

    assert summary.bell_slots == 3  # المؤقّتةُ ليست خانةَ جرس
    assert summary.slots_ended == 3


def test_a_provisional_entry_is_recorded_and_judged(school, klass, teacher, bells):
    real = _sessions(school, klass, teacher)
    provisional = _sessions(
        school, klass, teacher, provisional=True, slots=((dt.time(9, 0), dt.time(9, 45)),)
    )
    (student,) = _students(school, klass, 1)
    for session in real:
        _mark(school, session, student, "present")

    # المؤقّتةُ مجدولةٌ في حكم اليوم: أربعُ خاناتٍ تُطلب فلا يُحسم اليومُ قبل رصدها.
    assert school_day_summary(school, SUNDAY, now=at(14, 30)).school.incomplete == 1

    _mark(school, provisional[0], student, "present")  # ما رُصد فيها يدخل المرصودَ فيُحسم حاضراً
    assert school_day_summary(school, SUNDAY, now=at(14, 30)).school.present == 1


def test_registered_sections_read_confirmations_and_marked_rows_not_confirmations_alone(
    school, klass, teacher, bells
):
    sessions = _sessions(school, klass, teacher)
    (student,) = _students(school, klass, 1)
    # بلا أيّ تسجيل: لم تُسجَّل الخانات المنتهية.
    before = school_day_summary(school, SUNDAY, now=at(14, 30)).school
    assert (before.sections_registered, before.sections_total) == (0, 1)

    PeriodConfirmation.objects.create(
        school=school,
        class_group=klass,
        date=SUNDAY,
        start_time=SLOTS[0][0],
        end_time=SLOTS[0][1],
        first_confirmed_at=at(8, 0),
    )
    _mark(school, sessions[1], student, "present")  # صفٌّ معتمَدٌ يسجّل الخانة ولو بلا تثبيت
    PeriodConfirmation.objects.create(
        school=school,
        class_group=klass,
        date=SUNDAY,
        start_time=SLOTS[2][0],
        end_time=SLOTS[2][1],
        first_confirmed_at=at(13, 40),
    )

    after = school_day_summary(school, SUNDAY, now=at(14, 30)).school
    assert (after.sections_registered, after.sections_total) == (1, 1)


def test_wings_are_grouped_with_a_no_wing_row(school, klass, special_klass, teacher, bells):
    _sessions(school, klass, teacher)
    _sessions(school, special_klass, teacher, slots=((dt.time(9, 0), dt.time(9, 45)),))
    _students(school, klass, 2)
    _students(school, special_klass, 1, start=10)

    summary = school_day_summary(school, SUNDAY, now=at(14, 30))

    names = [row.name for row in summary.wings]
    assert names == ["جناح 1", "بلا جناح"]
    assert [row.counts.students for row in summary.wings] == [2, 1]


def test_permitted_whereabouts_are_a_separate_marker_and_do_not_change_the_verdict(
    school, klass, teacher, bells
):
    sessions = _sessions(school, klass, teacher)
    (student,) = _students(school, klass, 1)
    for session in sessions:
        _mark(school, session, student, "absent", whereabouts="clinic")

    c = school_day_summary(school, SUNDAY, now=at(14, 30)).school

    assert c.away_permitted == 1
    assert c.absent_unexcused == 1  # _judge لا يتغيّر (D-251م: مرحليّ)


def test_the_query_count_does_not_grow_with_the_students(
    school, klass, teacher, bells, django_assert_max_num_queries
):
    sessions = _sessions(school, klass, teacher)
    for student in _students(school, klass, 3):
        for session in sessions:
            _mark(school, session, student, "present")
    with django_assert_max_num_queries(14) as small:
        school_day_summary(school, SUNDAY, now=at(14, 30))
    base = len(small.captured_queries)

    for student in _students(school, klass, 40, start=100):
        for session in sessions:
            _mark(school, session, student, "present")
    with django_assert_max_num_queries(base) as _:
        school_day_summary(school, SUNDAY, now=at(14, 30))


def test_the_payload_carries_no_names_or_national_ids(school, klass, teacher, bells):
    sessions = _sessions(school, klass, teacher)
    students = _students(school, klass, 2)
    for student in students:
        _mark(school, sessions[0], student, "absent")

    payload = json.dumps(
        school_day_summary(school, SUNDAY, now=at(14, 30)).as_dict(), ensure_ascii=False
    )

    for student in students:
        assert student.full_name not in payload
        assert student.national_id not in payload
    assert StudentEnrollment.objects.count() == 2


def test_a_sections_schedule_state_separates_not_started_from_partial_and_complete(
    school, klass, teacher, bells
):
    sessions = _sessions(school, klass, teacher)
    (student,) = _students(school, klass, 1)

    def state():
        (row,) = school_day_summary(school, SUNDAY, now=at(14, 30)).sections
        return row

    assert state().state == "not_started" and state().gap  # لا تسجيلَ وقد انتهت الخانات
    _mark(school, sessions[0], student, "present")
    assert state().state == "partial" and state().gap and state().slots_registered == 1
    _mark(school, sessions[1], student, "present")
    _mark(school, sessions[2], student, "present")
    row = state()
    assert row.state == "complete" and not row.gap
    assert (row.slots_registered, row.slots_total, row.code) == (3, 3, klass.short_code)


def test_a_section_with_no_ended_slot_yet_is_not_flagged_as_a_gap(school, klass, teacher, bells):
    _sessions(school, klass, teacher)

    (row,) = school_day_summary(school, SUNDAY, now=at(6, 0)).sections

    assert row.state == "not_started" and not row.gap


def test_exits_are_counted_per_wing_and_section(school, klass, teacher, bells):
    from operations.models import DailyExitTally

    _sessions(school, klass, teacher)
    inside, outside = _students(school, klass, 2)
    DailyExitTally.objects.create(
        school=school,
        student=inside,
        date=SUNDAY,
        exit_count=2,
        total_seconds=600,
        by_destination={"clinic": {"count": 2, "seconds": 600}},
    )

    summary = school_day_summary(school, SUNDAY, now=at(14, 30))

    assert summary.school.exit_students == 1 and summary.school.exit_minutes == 10
    assert summary.wings[0].counts.exit_count == 2
    assert summary.sections[0].counts.exit_minutes == 10
    assert outside.pk is not None
