"""عدّاداتُ وقوائمُ لوحات الأدوار محصورةٌ بقدرة وجهتها (W-20261003-030، حكمُ 0105، D-171م).

رقمٌ أو اسمٌ يُعرض لمن لا تُفتح له شاشتُه كشفٌ بلا مسوّغ: المديرُ يرى أرقاماً ورابطاً
لا أسماءَ طلبة، وكلُّ عدّادٍ في لوحة الإداريّين يتبع القدرةَ التي تحرس صفحتَه.
"""

import datetime
from pathlib import Path

import pytest

from core.capabilities import capability, has_capability
from core.dashboard_selectors import ADMIN_OPS_ROLES, get_admin_ops_ctx
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_staff_register_screen import school  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parent.parent

#: العدّادُ ← القدرةُ التي تحرس الشاشةَ التي يفتحها.
COUNTER_CAPABILITY = {
    "absent_teachers_today": "operations.reports",
    "pending_swaps": "schedule.view",
    "pending_comp": "schedule.view",
}


def _user(school, role_name):
    user = UserFactory(national_id=f"2{abs(hash(role_name)) % 10**10:010d}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.mark.django_db
@pytest.mark.parametrize("role_name", sorted(ADMIN_OPS_ROLES))
class TestAdminOpsCountersFollowTheirDestination:
    def test_each_counter_is_present_only_with_its_capability(self, school, role_name):  # noqa: F811
        user = _user(school, role_name)
        ctx = get_admin_ops_ctx(user, school, datetime.date.today(), role_name)
        for key, cap in COUNTER_CAPABILITY.items():
            held = has_capability(user, cap)
            assert (ctx[key] is not None) == held, f"{role_name}: {key} ↔ {cap}"

    def test_the_names_list_needs_its_dedicated_capability(self, school, role_name):  # noqa: F811
        user = _user(school, role_name)
        ctx = get_admin_ops_ctx(user, school, datetime.date.today(), role_name)
        if not has_capability(user, "dashboard.absence_alert_names"):
            assert list(ctx["recent_alerts"]) == []


def test_the_director_card_shows_a_count_and_a_link_not_names():
    html = (ROOT / "templates/dashboard/roles/director.html").read_text(encoding="utf-8")
    assert "student.full_name" not in html
    assert "student_affairs:attendance_overview" in html


@pytest.mark.django_db
def test_nurse_holds_the_clinic_capability_her_dashboard_counts_for():
    assert "nurse" in capability("clinic.access").expanded_roles


@pytest.mark.django_db
def test_the_it_technician_context_carries_no_student_names(school):  # noqa: F811
    from core.dashboard_selectors import get_service_ctx

    user = _user(school, "it_technician")
    ctx = get_service_ctx(user, school, datetime.date.today(), "it_technician")
    assert not {"recent_alerts", "alerts", "students"} & set(ctx)
