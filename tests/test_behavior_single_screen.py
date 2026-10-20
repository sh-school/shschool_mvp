"""W-20261001-042: شاشةٌ واحدة لتسجيل المخالفة؛ المسارُ القديم يحوّل إليها لكلّ دورٍ يملك `behavior.record`."""

import pytest
from django.urls import reverse

from core.capabilities import registry
from core.permissions import expand_roles
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

RECORD_ROLES = sorted(registry()["behavior.record"].expanded_roles)


def test_eleven_roles_hold_the_record_capability():
    assert len(RECORD_ROLES) == 11
    assert set(RECORD_ROLES) <= expand_roles(set(registry()["behavior.record"].roles))


@pytest.mark.parametrize("role_name", RECORD_ROLES)
def test_every_recording_role_is_sent_to_the_one_screen(client_as, school, role_name):
    user = UserFactory(full_name="مسجِّل")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))

    resp = client_as(user).get(reverse("behavior:quick_log"), {"student_id": "5"})

    assert resp.status_code == 301
    assert resp["Location"] == reverse("behavior:report_infraction") + "?student=5"


def test_a_role_without_the_capability_is_refused_before_any_redirect(client_as, school):
    user = UserFactory(full_name="طالب")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))

    assert client_as(user).get(reverse("behavior:quick_log")).status_code == 403
