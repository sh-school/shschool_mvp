"""[W-20261012-030] تسجيلُ المخالفة يحصر الطالبَ بنطاق صاحب الطلب: 404 موحَّد خارجه ولا مخالفةَ تُنشأ.

كان `student_id` من النموذج يُجلب بـ`get_object_or_404(CustomUser, id=…)` بلا مدرسةٍ ولا دورٍ ولا جدول،
فيسجّل معلّمٌ مخالفةً على طالبٍ من مدرسةٍ أخرى أو خارج صفوفه، أو على مستخدمٍ ليس طالباً.
"""

import uuid

import pytest
from django.urls import reverse

from behavior.models import BehaviorInfraction
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory
from tests.test_behavior_views2 import teacher_student_link  # noqa: F401

pytestmark = pytest.mark.django_db

URLS = ["behavior:report_infraction", "behavior:quick_log"]


def _post(client_as, user, name, student_id):
    return client_as(user).post(
        reverse(name),
        {
            "student_id": str(student_id),
            "description": "مخالفةٌ تجريبيّة طويلةٌ بما يكفي للتحقّق من النموذج",
        },
    )


@pytest.fixture
def outsider(db):
    other = SchoolFactory()
    user = UserFactory(full_name="طالب مدرسة أخرى")
    MembershipFactory(user=user, school=other, role=RoleFactory(school=other, name="student"))
    return user


@pytest.fixture
def unlinked_student(db, school):
    user = UserFactory(full_name="طالب خارج الجدول")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    return user


@pytest.mark.parametrize("name", URLS)
def test_student_of_another_school_is_404_and_nothing_is_created(
    client_as, teacher_user, outsider, name
):
    assert _post(client_as, teacher_user, name, outsider.id).status_code == 404
    assert not BehaviorInfraction.objects.exists()


@pytest.mark.parametrize("name", URLS)
def test_non_student_user_is_404(client_as, teacher_user, name):
    assert _post(client_as, teacher_user, name, teacher_user.id).status_code == 404
    assert not BehaviorInfraction.objects.exists()


@pytest.mark.parametrize("name", URLS)
def test_teacher_cannot_record_on_student_outside_the_schedule(
    client_as,
    teacher_user,
    unlinked_student,
    teacher_student_link,
    name,  # noqa: F811
):
    assert _post(client_as, teacher_user, name, unlinked_student.id).status_code == 404
    assert not BehaviorInfraction.objects.exists()


@pytest.mark.parametrize("name", URLS)
def test_unknown_and_malformed_ids_are_the_same_404(client_as, teacher_user, name):
    assert _post(client_as, teacher_user, name, uuid.uuid4()).status_code == 404
    assert _post(client_as, teacher_user, name, "ليس-معرّفاً").status_code == 404


@pytest.mark.parametrize("name", URLS)
def test_teacher_can_reach_own_student(
    client_as,
    teacher_user,
    student_user,
    teacher_student_link,
    name,  # noqa: F811
):
    assert _post(client_as, teacher_user, name, student_user.id).status_code != 404


@pytest.mark.parametrize("name", URLS)
def test_leadership_reaches_any_student_of_its_school(
    client_as, principal_user, unlinked_student, name
):
    assert _post(client_as, principal_user, name, unlinked_student.id).status_code != 404
