"""[LEGAL] T-P1: معلّمُ الجلسة الاختيارية يرصد أعضاءَ مجموعته فقط (W-20261002-021، D-129م).

قبل هذا كان الوسمُ `Session.elective_group` نصّاً بلا أعضاء، فيرى المعلّمُ طلبةَ الشعبة كلَّهم.
"""

import pytest

from core.models import ElectiveGroupMembership, StudentEnrollment
from operations.attendance_policy import can_enter
from operations.elective_roster import has_members, session_enrollments
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, at
from tests.conftest import StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

LABEL = "الفنون"


@pytest.fixture
def mate(klass):
    student = UserFactory(full_name="زميل في مجموعة أخرى", national_id="29000001002")
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


def _join(student, klass, label=LABEL):
    enrollment = StudentEnrollment.objects.get(student=student, class_group=klass)
    return ElectiveGroupMembership.objects.create(enrollment=enrollment, group_label=label)


def test_without_label_the_whole_section_is_visible(session, kid, mate):
    assert set(session_enrollments(session).values_list("student_id", flat=True)) == {
        kid.pk,
        mate.pk,
    }
    assert not has_members(session)


def test_label_without_members_falls_back_to_the_section(session, kid, mate):
    session.elective_group = LABEL
    session.save()
    assert session_enrollments(session).count() == 2


def test_t_p1_elective_teacher_sees_only_group_members(session, klass, kid, mate):
    session.elective_group = LABEL
    session.save()
    _join(kid, klass)
    assert [e.student_id for e in session_enrollments(session)] == [kid.pk]


def test_t_p1_teacher_may_enter_only_for_members(session, klass, teacher, kid, mate):
    session.elective_group = LABEL
    session.save()
    _join(kid, klass)
    assert can_enter(teacher, session, kid, now=at(7, 30)).allowed
    verdict = can_enter(teacher, session, mate, now=at(7, 30))
    assert not verdict.allowed


def test_other_label_members_do_not_leak(session, klass, kid, mate):
    session.elective_group = LABEL
    session.save()
    _join(kid, klass)
    _join(mate, klass, label="التكنولوجيا")
    assert [e.student_id for e in session_enrollments(session)] == [kid.pk]


def test_non_elective_session_ignores_memberships(session, klass, kid, mate):
    _join(kid, klass)
    assert session_enrollments(session).count() == 2
