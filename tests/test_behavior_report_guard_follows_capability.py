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
#: المساعدان يرثان المعلّمَ (جدولَه وحضورَه) لا رصدَه: حكم 0104 باستثنائهما صراحةً، فلا تتوسّع الصلاحيةُ بالمصادفة.
ASSISTANTS = ["teacher_assistant", "ese_assistant"]
#: أدوارٌ لا تحمل القدرة: لا ترصد.
WITHOUT = [*ASSISTANTS, "nurse", "psychologist", "librarian", "student", "parent"]


def test_the_static_list_is_gone():
    assert not hasattr(BehaviorPermissions, "REPORTER_ROLES")


@pytest.mark.parametrize("role", [*NEWLY_ADMITTED, "teacher", "principal"])
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


@pytest.mark.parametrize("role", ASSISTANTS)
def test_the_assistants_stay_refused_on_the_report_and_the_recording_forms(
    client_as, school, seeded_calendar, supervisor, child, role
):
    from unittest.mock import patch

    user = _staff(school, role, "29000008004")
    with patch("behavior.views._deny_unreachable", return_value=None):
        report = client_as(user).get(reverse("behavior:behavior_report", args=[child.pk]))
    form = client_as(user).get(reverse("behavior:report_infraction"))
    quick = client_as(user).get(reverse("behavior:quick_log"))

    assert report.status_code == 403
    assert form.status_code == 403
    assert quick.status_code == 403


def test_excluding_the_assistants_changes_only_behavior_record_for_only_them():
    """الفرقُ بين الوراثة الكاملة والمستثناة: قدرةٌ واحدة، لمساعدَين فقط؛ ومصفوفةُ المعلّم لا تتغيّر."""
    from core.capabilities import registry
    from core.permissions import expand_roles

    diff = {}
    for cap in registry().values():
        lost = expand_roles(set(cap.roles)) - cap.expanded_roles
        if lost:
            diff.setdefault(cap.key, set()).update(lost)

    assert diff.get("behavior.record") == set(ASSISTANTS)
    assert "teacher" in capability("behavior.record").expanded_roles
    assert not (set(diff) - {"behavior.record", "student_affairs.view"})
