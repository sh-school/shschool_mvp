"""[ATTENDANCE] «حاصرُ الغياب العامّ» (`wings.school_wide`) — قرارُ المالك 2026-10-06.

مشرفٌ إداريٌّ يرى الأجنحةَ الخمسةَ في الغياب ويعتمد رصدَ المعلّمين ويصحّحه بجانب حامل كلّ جناح، بقدرةٍ مفوَّضةٍ
باسمه (لا دورٍ جديد). الثوابتُ:

    الاعتماد    معتمِدٌ ثانٍ دائماً بجانب الحامل — لا إدخالَه هو، ولا رصدَ التربية الخاصّة (النهائيّ)
    النطاق      الأجنحةُ كلُّها لمن يحمل المنحَ **ومعه دورُ المشرف الإداريّ** — المنحُ لغيره لا يرفع شيئاً
    الحجب       يبقى مقيَّداً بالجناح فتُحجب عنه الدرجاتُ وملاحظاتُ الأخصّائيّين (النطاقُ كلُّه أجنحةٌ)
    التدقيق     أساسُ القرار `school_wide` لا `wing_holder` — فلا يُنسب لحاملٍ ما قرّره غيرُه

ولا رقمَ وظيفيّاً ولا اسماً حقيقيّاً: كلُّ هويّةٍ مولَّدةٌ.
"""

import pytest

from core import capability_grants as grants
from core.capabilities import has_capability
from core.models import Wing
from operations.attendance_entries import submit_entry
from operations.models import Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SUNDAY, _staff, at
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory
from wings.scope import student_scope
from wings.services import holds_school_wide, wings_of

pytestmark = pytest.mark.django_db

REASON = "حصرُ الغياب في المدرسة كلِّها بتكليفٍ من الإدارة"


@pytest.fixture
def principal(school):
    return _staff(school, "principal", "المدير", "29000002001")


@pytest.fixture
def general(school, principal):
    """مشرفٌ إداريٌّ بلا جناحٍ يحمل «حاصرَ الغياب العامّ»."""
    user = _staff(school, "admin_supervisor", "حاصرُ الغياب", "29000002002")
    grants.grant(user=user, capability="wings.school_wide", by=principal, reason=REASON)
    return user


@pytest.fixture
def plain_supervisor(school):
    """مشرفٌ إداريٌّ بلا منح — ولا جناح."""
    return _staff(school, "admin_supervisor", "مشرفٌ بلا منح", "29000002003")


@pytest.fixture
def second_wing(school, year, band, general):
    other_holder = _staff(school, "admin_supervisor", "حاملُ الجناح الثاني", "29000002004")
    wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    klass = ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=year, wing=wing
    )
    student = UserFactory(full_name="طالب الجناح الثاني", national_id="29000002010")
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return wing, klass, student


def entry_in(school, klass, teacher, kid):
    session = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=at(7, 10).time(),
        end_time=at(7, 55).time(),
        status="scheduled",
    )
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    return session, entry


# ── القدرةُ والمنح ─────────────────────────────────────────────────────


def test_the_capability_is_delegated_only_and_held_by_no_role(school, general, plain_supervisor):
    assert has_capability(general, "wings.school_wide")
    assert not has_capability(plain_supervisor, "wings.school_wide")
    assert not has_capability(
        _staff(school, "vice_admin", "نائب", "29000002020"), "wings.school_wide"
    )


def test_a_grant_to_a_non_supervisor_lifts_nothing(school, principal):
    teacher = _staff(school, "teacher", "معلّم بمنحٍ", "29000002021")
    grants.grant(user=teacher, capability="wings.school_wide", by=principal, reason=REASON)

    assert not holds_school_wide(teacher)
    assert wings_of(teacher, school, "x") == []


def test_only_the_three_granting_roles_may_grant_it(school):
    vice_admin = _staff(school, "vice_admin", "نائبٌ إداريّ", "29000002022")
    target = _staff(school, "admin_supervisor", "هدف", "29000002023")

    with pytest.raises(grants.GrantError):
        grants.grant(user=target, capability="wings.school_wide", by=vice_admin, reason=REASON)


# ── النطاق ──────────────────────────────────────────────────────────────


def test_the_holder_sees_every_wing_and_displaces_no_supervisor(
    school, year, wing, second_wing, general, holder
):
    other_wing, _, _ = second_wing

    assert {w.code for w in wings_of(general, school, year)} == {"w1", "w2"}
    assert wing.current_supervisor() == holder  # لم يُزَح أحد
    assert other_wing.current_supervisor() != general


def test_a_plain_supervisor_without_the_grant_sees_no_wing(school, year, wing, plain_supervisor):
    assert wings_of(plain_supervisor, school, year) == []


def test_the_scope_covers_every_wing_student_yet_stays_wing_bound_so_the_hiding_holds(
    school, year, wing, klass, kid, second_wing, general
):
    _, _, other_kid = second_wing
    scope = student_scope(general, school)

    assert scope.is_wing_bound  # فتُحجب الدرجاتُ وملاحظاتُ الأخصّائيّين وسببُ العيادة كما للمشرف
    assert scope.hides_grades and scope.hides_specialist_notes and scope.clinic_summary_only
    assert {kid.id, other_kid.id} <= set(scope.student_ids())
    assert scope.covers_student(other_kid.id) and scope.covers_class(klass.id)


# ── الاعتمادُ والتصحيح ─────────────────────────────────────────────────
