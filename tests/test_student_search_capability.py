"""[SECURITY] W-20261004-005 (قرارُ المالك D-192م): سحبُ البحث السريع عن الطلبة من أربعة أدوارٍ لا حاجةَ لها به.

كانت قدرةُ `students.search` لكلّ الطاقم (`ALL_STAFF_ROLES`) فيبحث بها المندوبُ وأمينُ المخزن ومحضّرُ المختبر ومشرفُ المقصف عن أسماء الطلبة.
وحصرُها بأصحاب `reports.results` (مستهلكُها الوحيدُ صفحةُ التقارير) كان يحرم مشرفَ الجناح ومن في حكمه ممّن يبحثون بها مقيَّدين بجناحهم
(`tests/test_supervisor_cross_scope.py`) — فالسحبُ **صريحٌ من الأربعة وحدَهم**، ولا تُضاف أدوارٌ إلى `WING_BOUND_ROLES`.
"""

import pytest
from django.urls import reverse

from core.capabilities import capability
from core.models import Role
from core.permissions import ALL_STAFF_ROLES
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

WITHDRAWN = ("messenger", "storekeeper", "lab_technician", "canteen_supervisor")


def test_the_roles_holding_reports_results_are_enumerated_and_none_is_withdrawn():
    """قائمةٌ مثبَّتة لأصحاب كشوف النتائج (بالوراثة): أيُّ تغييرٍ فيها يُرى هنا؛ ولا أحدَ من الأربعة بينهم فلا سحبَ مزدوج."""
    holders = set(capability("reports.results").expanded_roles)
    assert holders == {
        "principal",
        "vice_academic",
        "vice_admin",
        "coordinator",
        "teacher",
        "ese_teacher",
        # الوراثةُ (ROLE_INHERITS): مساعدو المعلّم ومنسّقو الأنشطة والمشاريع
        "teacher_assistant",
        "ese_assistant",
        "activities_coordinator",
        "e_projects_coordinator",
    }
    assert holders.isdisjoint(WITHDRAWN)


@pytest.mark.parametrize("role", WITHDRAWN)
def test_the_four_withdrawn_roles_no_longer_hold_student_search(role):
    assert role not in capability("students.search").expanded_roles


def test_every_other_staff_role_keeps_student_search():
    """الباقون كما كانوا بالضبط: كلُّ الطاقم ما عدا الأربعة."""
    assert set(capability("students.search").roles) == set(ALL_STAFF_ROLES) - set(WITHDRAWN)


@pytest.mark.parametrize("role", WITHDRAWN)
def test_a_withdrawn_role_is_refused_by_the_endpoint(client_as, school, role):
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    response = client_as(user).get(reverse("api_student_search"), {"q": "طالب"})
    assert response.status_code in (302, 403)


@pytest.mark.parametrize("role", ["principal", "teacher", "coordinator", "admin_supervisor"])
def test_other_roles_still_reach_the_endpoint(client_as, school, role):
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    response = client_as(user).get(reverse("api_student_search"), {"q": "طالب"})
    assert response.status_code == 200


def test_the_four_names_are_real_role_keys():
    """مفاتيحُ حقيقيّةٌ في `Role.ROLES` — فلا يمرّ خطأٌ إملائيٌّ يجعل الاختبارَ فارغاً."""
    assert set(WITHDRAWN) <= {key for key, _label in Role.ROLES}
