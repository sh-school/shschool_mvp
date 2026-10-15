"""الطالب المنقول يبقى ظاهراً في شعبته القديمة لأيّامها السابقة للنقل (W-20261010-017، D-323م خيار أ).

`left_at` آخرُ يومٍ في الشعبة القديمة (= يوم النقل − 1) فلا يتداخل يومان؛ والجديدةُ تبدأ من يوم النقل.
وقيدٌ معطَّلٌ بلا `left_at` لا يُخمَّن فيبقى غيرَ ظاهر.
"""

import datetime as dt

import pytest

from core.models import StudentEnrollment
from operations.attendance_policy import can_enter
from student_affairs.internal_transfer import complete_internal
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db

MOVE = dt.date(2026, 10, 1)
BEFORE = MOVE - dt.timedelta(days=1)
AFTER = MOVE + dt.timedelta(days=1)


@pytest.fixture
def klass2(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


def _moved(school, kid, klass2, user):
    transfer = StudentTransfer.objects.create(
        school=school,
        student=kid,
        direction="internal",
        other_school_name=school.name,
        to_class_group=klass2,
        transfer_date=MOVE,
        status="approved",
        academic_year="2026-2027",
        created_by=user,
        updated_by=user,
    )
    complete_internal(transfer, user)


def _roll(klass, day):
    return set(
        StudentEnrollment.objects.filter(class_group=klass)
        .on_roll(day)
        .values_list("student_id", flat=True)
    )


def test_completion_records_the_last_day_in_the_old_class(
    school, kid, klass, klass2, student_affairs_coordinator_user
):
    _moved(school, kid, klass2, student_affairs_coordinator_user)

    old = StudentEnrollment.objects.get(student=kid, class_group=klass)
    new = StudentEnrollment.objects.get(student=kid, class_group=klass2)
    assert (old.is_active, old.left_at) == (False, BEFORE)
    assert (new.is_active, new.left_at, new.enrolled_at) == (True, None, MOVE)


def test_the_moved_student_is_on_the_old_roll_before_the_move_and_the_new_from_it(
    school, kid, klass, klass2, student_affairs_coordinator_user
):
    StudentEnrollment.objects.filter(student=kid, class_group=klass).update(
        enrolled_at=dt.date(2026, 9, 1)
    )
    _moved(school, kid, klass2, student_affairs_coordinator_user)

    assert kid.pk in _roll(klass, dt.date(2026, 9, 1))
    assert kid.pk in _roll(klass, BEFORE), "آخرُ يومٍ في القديمة"
    assert kid.pk not in _roll(klass, MOVE), "يومُ النقل للجديدة"
    assert kid.pk not in _roll(klass, AFTER)
    assert kid.pk not in _roll(klass2, BEFORE)
    assert kid.pk in _roll(klass2, MOVE)
    assert kid.pk in _roll(klass2, AFTER)


def test_no_day_shows_the_student_in_both_classes(
    school, kid, klass, klass2, student_affairs_coordinator_user
):
    StudentEnrollment.objects.filter(student=kid, class_group=klass).update(
        enrolled_at=dt.date(2026, 9, 1)
    )
    _moved(school, kid, klass2, student_affairs_coordinator_user)

    for offset in range(-10, 10):
        day = MOVE + dt.timedelta(days=offset)
        assert (kid.pk in _roll(klass, day)) != (kid.pk in _roll(klass2, day)) or day < dt.date(
            2026, 9, 1
        )


def test_a_deactivated_enrollment_without_left_at_stays_hidden(school, kid, klass):
    StudentEnrollment.objects.filter(student=kid, class_group=klass).update(is_active=False)

    assert kid.pk not in _roll(klass, dt.date(2026, 12, 1))


def test_an_active_student_is_still_hidden_before_enrolling(school, kid, klass):
    StudentEnrollment.objects.filter(student=kid, class_group=klass).update(
        enrolled_at=dt.date(2026, 10, 5)
    )

    assert kid.pk not in _roll(klass, dt.date(2026, 10, 4))
    assert kid.pk in _roll(klass, dt.date(2026, 10, 5))


def test_the_old_teacher_may_not_enter_after_the_move(
    school, kid, klass, klass2, session, teacher, student_affairs_coordinator_user
):
    """سياسةُ الإدخال تستعمل القاعدةَ نفسَها: الجلسةُ في القديمة بعد يوم النقل ← غيرُ مسجَّل."""
    StudentEnrollment.objects.filter(student=kid, class_group=klass).update(
        enrolled_at=dt.date(2026, 9, 1)
    )
    _moved(school, kid, klass2, student_affairs_coordinator_user)
    type(session).objects.filter(pk=session.pk).update(date=AFTER)
    session.refresh_from_db()

    verdict = can_enter(teacher, session, kid, now=at(7, 30, day=AFTER))

    assert not verdict.allowed
