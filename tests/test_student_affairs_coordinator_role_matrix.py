"""مصفوفةُ دور «منسّق شؤون الطلبة» (بطاقة W-20261018-003، قرارات المالك 2026-10-18).

العطبُ: الدورُ كان مذكوراً في بعض المواضع ومنسيّاً في غيرها فلا يعمل على المنصّة. هذا الجدولُ يقابل
كلَّ موضعٍ بقرارٍ مكتوب؛ فحذفُ موضعٍ أو نسيانُه في دورٍ جديد يُسقط الاختبار، وكذلك منحُ ما لم يُقرَّر.
"""

import pytest

from behavior.services import BehaviorPermissions
from core import permissions as perms
from core.capabilities import has_capability, registry
from core.module_registry import get_accessible_modules_from_registry
from core.views_auth import ROLES_REQUIRING_2FA
from reports.views import _teacher_can_access_class
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

ROLE = "student_affairs_coordinator"

#: القدراتُ الممنوحةُ بقرارات المالك لهذه البطاقة (وما قبلها يبقى كما هو).
GRANTED_BY_THIS_CARD = {"behavior.manage", "wings.excuse_after_deadline"}

#: ما استُبعد صراحةً (الجرد 0301 وقرار المالك): لا يُمنح للدور.
NEVER_GRANTED = {
    "attendance.mark",
    "student_affairs.transfer_approve",
    "student_affairs.activities",
    "students.import_export",
    "operations.reports",
}


def _user(school, role=ROLE, nid="29500000001"):
    user = UserFactory(full_name=f"موظّف {role}", national_id=nid)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def test_scope_is_the_whole_school(school):
    """الجذر: نطاقُه المدرسةُ كلُّها فلا يقع في فرع المعلّم (مجموعةٌ فارغة)."""
    assert perms.get_teacher_student_ids(_user(school)) is None


def test_summon_and_stats_follow_the_capabilities(school):
    user = _user(school)
    assert has_capability(user, "behavior.summon_parent")
    assert has_capability(user, "behavior.statistics")
    assert BehaviorPermissions.can_summon(user) is True
    assert BehaviorPermissions.can_view_stats(user) is True


def test_the_two_decided_capabilities_are_held(school):
    user = _user(school)
    for key in GRANTED_BY_THIS_CARD:
        assert has_capability(user, key), key


def test_nothing_excluded_is_held(school):
    user = _user(school)
    for key in NEVER_GRANTED:
        assert not has_capability(user, key), key


def test_only_the_two_capabilities_were_added_for_this_role():
    """من يحملها بالدور الخامّ: المنسّقُ على القدرتين وحدَهما من بين ما قُرِّر في هذه البطاقة."""
    holding = {k for k, cap in registry().items() if ROLE in cap.roles}
    assert GRANTED_BY_THIS_CARD <= holding


def test_the_class_report_opens_for_the_role(school, rf):
    request = rf.get("/")
    request.user = _user(school)
    assert _teacher_can_access_class(request, school, object(), object()) is True


def test_the_other_roles_keep_their_answers(school):
    """غيرُ المخوَّل يبقى مرفوضاً: معلّمٌ عاديٌّ لا يحمل القدرتين ولا الاستدعاء."""
    teacher = _user(school, "teacher", "29500000002")
    for key in GRANTED_BY_THIS_CARD | {"behavior.summon_parent"}:
        assert not has_capability(teacher, key), key
    assert BehaviorPermissions.can_summon(teacher) is False


def test_the_sidebar_shows_behavior_parents_and_wings(school):
    names = {m["name"] for m in get_accessible_modules_from_registry(_user(school))}
    assert {"behavior", "parents", "wings"} <= names


def test_two_factor_is_required_but_partial_id_search_is_not_granted():
    from core.privacy import PARTIAL_ID_SEARCH_ROLES

    assert ROLE in ROLES_REQUIRING_2FA
    assert ROLE not in PARTIAL_ID_SEARCH_ROLES
