"""[W-20261008-018] عدّاداتُ «الخارج من الفصل» — قراءةٌ فقط وبلا أسماء (S0 المحمول + S1 العدّادات، D-251م وD-279م).

المدير للمدرسة، والمشرفُ لجناحه؛ وكلُّ رقمٍ بوحدته ومصدره، لا يتغيّر بها شيءٌ ممّا يراه طالبٌ أو وليُّ أمر.
"""

import dataclasses

import pytest

from core.domain.attendance import IN_CUSTODY, is_out_with_leave
from core.models import Wing
from operations.away_counters import (
    AwayCounters,
    away_counters,
    away_counters_for,
    can_see_away_counters,
    exit_day_totals,
)
from operations.class_exit import come_back, leave
from operations.models import StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SUNDAY, at
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _mark(session, student, school, status="absent", where=""):
    return StudentAttendance.objects.create(
        session=session, student=student, school=school, status=status, whereabouts=where
    )


# ── S0: المحمول المركزي ────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "where", "expected"),
    [
        ("absent", "clinic", True),
        ("absent", "activity", True),
        ("absent", "out_permit", False),  # استئذانٌ بإذن: قاعدةُ الأربع حصص لا تتغيّر
        ("absent", "left_early", False),
        ("absent", "out_no_permit", False),  # الهروبُ يبقى هروباً
        ("absent", "gate", False),
        ("absent", "", False),
        ("present", "clinic", False),  # حاضرٌ أصلاً
        ("late", "activity", False),
    ],
)
def test_is_out_with_leave_is_clinic_or_activity_while_absent_only(status, where, expected):
    assert is_out_with_leave(status, where) is expected


def test_the_custody_list_is_the_single_two_item_constant():
    assert IN_CUSTODY == ("clinic", "activity")


# ── S1: الخروج وزمنه ───────────────────────────────────────


def test_exit_counts_and_minutes_come_from_the_tally_plus_the_clipped_open_exit(
    school, kid, session
):
    leave(session, kid, "restroom", by=session.teacher, now=at(7, 15))
    come_back(session, kid, now=at(7, 20))  # 5 د مغلقة
    leave(session, kid, "restroom", by=session.teacher, now=at(7, 30))  # مفتوح
    counters = away_counters(school, SUNDAY, now=at(7, 40))
    assert counters.exit_count == 2
    assert counters.exit_seconds == (5 + 10) * 60
    assert counters.exit_students == 1
    assert counters.avg_exit_seconds == 15 * 60
    assert counters.still_out == 1


def test_an_open_exit_is_clipped_at_the_end_of_the_school_day(school, kid, session):
    leave(session, kid, "restroom", by=session.teacher, now=at(7, 30))
    count, seconds, students, still_out = exit_day_totals(school, SUNDAY, now=at(20, 0))
    assert (count, students, still_out) == (1, 1, 1)
    assert seconds <= (13 * 60 + 30 - (7 * 60 + 30)) * 60  # لا يتضخّم بعد نهاية الدوام


def test_a_day_without_exits_is_all_zeros(school, kid, session):
    assert away_counters(school, SUNDAY, now=at(8, 0)).exit_count == 0
    assert away_counters(school, SUNDAY, now=at(8, 0)).avg_exit_seconds == 0


# ── S1: الاستئذان وخارج الفصل بإذن والغياب ──────────────────


def test_distinct_students_out_with_leave_and_leave_requests(school, kid, klass, session):
    other = UserFactory(full_name="طالب ثانٍ", national_id="29000001002")
    StudentEnrollmentFactory(student=other, class_group=klass, enrolled_at=ENROLLED)
    _mark(session, kid, school, "absent", "clinic")
    _mark(session, other, school, "absent", "out_permit")
    counters = away_counters(school, SUNDAY, now=at(8, 0))
    assert counters.out_with_leave == 1  # العيادةُ وحدَها
    assert counters.leave_requests == 1  # الاستئذانُ وحدَه
    assert counters.absence_rows == 2  # الصفوفُ كما سُجّلت — لا يغيّرها الوسم


def test_a_student_with_two_clinic_marks_is_counted_once(school, kid, session):
    _mark(session, kid, school, "absent", "clinic")
    assert away_counters(school, SUNDAY, now=at(8, 0)).out_with_leave == 1


# ── S1: السلوك بيوم الواقعة ────────────────────────────────


def test_behaviour_is_counted_on_the_session_day_not_the_writing_day(school, kid, session, teacher):
    BehaviorInfractionFactory(
        school=school, student=kid, reported_by=teacher, session=session, level=3
    )
    BehaviorInfractionFactory(
        school=school, student=kid, reported_by=teacher, session=session, level=1
    )
    BehaviorInfractionFactory(
        school=school, student=kid, reported_by=teacher, session=session, level=4, is_resolved=True
    )
    counters = away_counters(school, SUNDAY, now=at(8, 0))
    assert counters.infractions == 3
    assert counters.serious_open == 1  # الدرجةُ ≥3 غيرُ المعالَجة
    assert away_counters(school, SUNDAY.replace(day=14), now=at(8, 0)).infractions == 0


# ── النطاق والصلاحيّة وغياب الأسماء ─────────────────────────


def test_a_supervisor_counts_only_their_wing_and_the_principal_counts_all(
    school, year, kid, session, holder, principal_user
):
    other_holder = UserFactory(full_name="مشرف آخر", national_id="29000001030")
    other_wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    other_klass = ClassGroupFactory(
        school=school,
        grade="G8",
        section="1",
        level_type="prep",
        academic_year=year,
        wing=other_wing,
    )
    stranger = UserFactory(full_name="طالب جناح آخر", national_id="29000001003")
    StudentEnrollmentFactory(student=stranger, class_group=other_klass, enrolled_at=ENROLLED)
    _mark(session, kid, school, "absent", "clinic")
    _mark(session, stranger, school, "absent", "clinic")

    mine = away_counters_for(holder, school, SUNDAY, now=at(8, 0))
    everyone = away_counters_for(principal_user, school, SUNDAY, now=at(8, 0))
    assert mine is not None and everyone is not None
    assert mine.out_with_leave == 1
    assert everyone.out_with_leave == 2


def test_only_leadership_and_wing_holders_may_see_the_counters(
    school, teacher, holder, principal_user, parent_user
):
    assert can_see_away_counters(principal_user)
    assert can_see_away_counters(holder)
    assert not can_see_away_counters(teacher)
    assert not can_see_away_counters(parent_user)
    assert away_counters_for(teacher, school, SUNDAY) is None


def test_the_counters_carry_numbers_only_never_a_name():
    fields = dataclasses.fields(AwayCounters)
    assert fields and all(f.type in ("int", int) for f in fields)


def test_the_number_of_queries_does_not_grow_with_the_students(
    school, klass, session, django_assert_max_num_queries
):
    for n in range(6):
        pupil = UserFactory(full_name=f"طالب {n}", national_id=f"2900001{n:04d}")
        StudentEnrollmentFactory(student=pupil, class_group=klass, enrolled_at=ENROLLED)
        _mark(session, pupil, school, "absent", "clinic")
    with django_assert_max_num_queries(25):
        assert away_counters(school, SUNDAY, now=at(8, 0)).out_with_leave == 6
