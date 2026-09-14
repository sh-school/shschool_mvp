"""لوحةُ الإدارة تُري كلَّ موظّفٍ بياناتِ مدرسته وحدَها — والمشرفُ الأعلى يرى الكلّ.

كانت لوحاتُ الأشخاص (المستخدمون، العضويّات، القيود، روابطُ أولياء الأمور،
سجلُّ التدقيق، الموافقات) تقرأ الجدولَ كاملاً لكلّ من دخل `/admin/`. والقيدُ
في `core.admin.SchoolScopedAdmin`: مسارٌ مسمّىً إلى المدرسة، ومن لا مدرسةَ له
لا يرى شيئاً.
"""

import pytest
from django.contrib.admin.sites import site
from django.test import RequestFactory

from core.models import AuditLog, CustomUser, Membership, ParentStudentLink, StudentEnrollment
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _staff(school):
    user = UserFactory(is_staff=True)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    return user


def _as(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


@pytest.fixture
def two_schools():
    here, there = SchoolFactory(), SchoolFactory()
    for school in (here, there):
        pupil = UserFactory()
        MembershipFactory(
            user=pupil, school=school, role=RoleFactory(school=school, name="student")
        )
        StudentEnrollmentFactory(student=pupil, class_group=ClassGroupFactory(school=school))
        parent = UserFactory()
        ParentStudentLink.objects.create(parent=parent, student=pupil, school=school)
        AuditLog.log(user=pupil, action="view", model_name="other", school=school)
    return here, there


@pytest.mark.parametrize(
    "model", [CustomUser, Membership, StudentEnrollment, ParentStudentLink, AuditLog]
)
def test_a_staff_member_sees_only_their_school(two_schools, model):
    here, there = two_schools
    admin = _staff(here)

    rows = site._registry[model].get_queryset(_as(admin))

    assert rows.exists()
    scoped = site._registry[model].school_lookup
    assert not rows.exclude(**{scoped: here}).exists(), f"{model.__name__}: صفٌّ من مدرسةٍ أخرى"


def test_a_superuser_sees_every_school(two_schools):
    here, there = two_schools
    root = UserFactory(is_staff=True, is_superuser=True)

    rows = site._registry[StudentEnrollment].get_queryset(_as(root))

    assert set(rows.values_list("class_group__school", flat=True)) == {here.pk, there.pk}


def test_a_staff_member_without_a_school_sees_nothing(two_schools):
    lost = UserFactory(is_staff=True)

    assert not site._registry[Membership].get_queryset(_as(lost)).exists()
