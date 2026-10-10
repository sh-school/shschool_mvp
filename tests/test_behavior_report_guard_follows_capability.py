"""[BEHAVIOR] حارسُ الرصد يقرأ القدرةَ `behavior.record` لا قائمةَ أدوارٍ ثابتة (بطاقة W-20261010-013).

كان `BehaviorPermissions.can_report` يفحص قائمةً ثابتة `REPORTER_ROLES`، فيردّ من يحمل القدرةَ فعلاً
(منسّقَ الأنشطة والمشاريع وشؤون الطلبة) بـ403 بعد أن مرّ حارسَ القدرة: تناقضٌ يفشل إلى الإغلاق.
الآن الجوابُ واحدٌ: من يحمل القدرةَ يرصد، ومن لا يحملها لا يرصد.
"""

import pytest
from django.urls import reverse

from behavior.services import BehaviorPermissions
from core.capabilities import capability, has_capability
from tests.test_guardian_name_need_to_know import _staff, child  # noqa: F401
from tests.test_period_register import klass, supervisor, year  # noqa: F401

pytestmark = pytest.mark.django_db

#: الأدوارُ التي كان حارسُ القائمة يردّها وهي تحمل القدرة (من مراجعة 0104).
NEWLY_ADMITTED = ["activities_coordinator", "e_projects_coordinator", "student_affairs_coordinator"]
#: ومن يحمل القدرةَ بالوراثة من المعلّم ولم يكن في القائمة — يُرفع لحكم 0104 لا يُخفى.
INHERITED_ASSISTANTS = ["teacher_assistant", "ese_assistant"]
#: أدوارٌ لا تحمل القدرة: لا ترصد.
WITHOUT = ["nurse", "psychologist", "librarian", "student", "parent"]


def test_the_static_list_is_gone():
    assert not hasattr(BehaviorPermissions, "REPORTER_ROLES")


@pytest.mark.parametrize("role", [*NEWLY_ADMITTED, *INHERITED_ASSISTANTS, "teacher", "principal"])
def test_whoever_holds_the_capability_can_report(school, role):
    user = _staff(school, role, "29000008001")

    assert has_capability(user, "behavior.record")
    assert BehaviorPermissions.can_report(user) is True


@pytest.mark.parametrize("role", WITHOUT)
def test_whoever_lacks_the_capability_cannot_report(school, role):
    user = _staff(school, role, "29000008002")

    assert not has_capability(user, "behavior.record")
    assert BehaviorPermissions.can_report(user) is False


def test_the_guard_and_the_capability_agree_for_every_role_in_the_registry(school):
    roles = set()
    for cap in (capability("behavior.record"), capability("behavior.view")):
        roles |= cap.expanded_roles
    for n, role in enumerate(sorted(roles)):
        user = _staff(school, role, f"29000{9000 + n:06d}")
        assert BehaviorPermissions.can_report(user) == has_capability(user, "behavior.record"), role


@pytest.mark.parametrize("role", NEWLY_ADMITTED)
def test_the_newly_admitted_roles_open_the_report_instead_of_being_refused(
    client_as, school, seeded_calendar, supervisor, child, role
):
    from unittest.mock import patch

    user = _staff(school, role, "29000008003")
    with patch("behavior.views._deny_unreachable", return_value=None):
        response = client_as(user).get(reverse("behavior:behavior_report", args=[child.pk]))

    assert response.status_code == 200
