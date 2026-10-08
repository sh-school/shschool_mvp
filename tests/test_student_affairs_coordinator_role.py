"""دورُ «منسّق شؤون الطلبة» — W-20261001-020.

السند: بطاقتُه في `03_job_descriptions_rbac.md` (بطاقة 1033: «إدخال بيانات الطلبة إلكترونياً
وتحديثها» وتنفيذ تسجيل الطلبة)، وم5.7 من سياسة إدارة سلوك الطلبة (08_conduct_policy_2026.md)
تعدّه من الأعضاء الأساسيين. مفتاحٌ داخليّ مستقلّ — لا يُحمل على رمز 1033 (نائب الأكاديميّ).
والبطاقةُ لا تذكر نقلاً ولا إيقافَ قيد، فلا يملك الدورُ `transfers` ولا `deactivate` (افتراضٌ معلَن).
"""

import pytest
from django.urls import reverse

from core.capabilities import has_capability
from core.models import Role
from core.navigation import can_open
from core.permissions import (
    ACTIVITIES_MANAGE,
    ALL_STAFF_ROLES,
    STUDENT_AFFAIRS_MANAGE,
    STUDENT_DEACTIVATE,
    STUDENT_FOLLOW_UP,
)
from quality.reporting_lines import DIRECT_SUPERVISOR, VICE_ADMIN
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

ROLE = "student_affairs_coordinator"

#: حاملو `manage` قبل إضافة المنسّق — لا يتغيّر وصولُ أحدٍ منهم إلى شيءٍ كانوا يدخلونه.
HOLDERS_BEFORE = ("principal", "vice_admin", "vice_academic", "platform_developer")
TRANSFER_SCREENS = ("student_affairs.transfers", "student_affairs.manage")


def _user_with(school, role_name):
    user = UserFactory(full_name=f"مستخدم {role_name}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.mark.django_db
class TestRegistry:
    def test_the_role_is_registered_with_its_arabic_title(self):
        assert dict(Role.ROLES)[ROLE] == "منسق شؤون الطلبة"

    def test_it_is_a_staff_role_in_the_supervisors_tier(self, school):
        role = Role.objects.create(school=school, name=ROLE)
        assert role.tier == 3
        assert ROLE in ALL_STAFF_ROLES

    def test_it_reports_to_the_administrative_deputy(self):
        """بطاقة 1033: المسؤول المباشر النائبُ الإداريّ."""
        assert DIRECT_SUPERVISOR[ROLE] == VICE_ADMIN


@pytest.mark.django_db
class TestCapabilities:
    def test_it_manages_student_records(self, student_affairs_coordinator_user):
        assert has_capability(student_affairs_coordinator_user, "student_affairs.manage")
        assert ROLE in STUDENT_AFFAIRS_MANAGE

    def test_it_cannot_deactivate_a_student(self, student_affairs_coordinator_user):
        assert not has_capability(student_affairs_coordinator_user, "student_affairs.deactivate")
        assert ROLE not in STUDENT_DEACTIVATE

    def test_it_has_no_transfers(self, student_affairs_coordinator_user):
        """إتمامُ الانتقال الصادر يعطّل عضويّةَ الطالب — ولا نصَّ في بطاقته يمنحه إيّاه."""
        assert not has_capability(student_affairs_coordinator_user, "student_affairs.transfers")

    def test_it_does_not_run_the_activities(self, student_affairs_coordinator_user):
        assert ROLE not in ACTIVITIES_MANAGE
        assert not has_capability(student_affairs_coordinator_user, "student_affairs.activities")

    def test_it_follows_up_student_conduct(self):
        """بطاقة 1033: «مساعدة النائب الإداري في متابعة سلوك الطلبة وتنفيذ سياسة الانضباط»."""
        assert ROLE in STUDENT_FOLLOW_UP

    @pytest.mark.parametrize("role", HOLDERS_BEFORE)
    @pytest.mark.parametrize("capability", TRANSFER_SCREENS)
    def test_every_prior_holder_keeps_the_transfer_screens(self, school, role, capability):
        assert has_capability(_user_with(school, role), capability)

    @pytest.mark.parametrize("role", ("principal", "vice_admin"))
    def test_deactivation_stays_with_the_leadership(self, school, role):
        assert has_capability(_user_with(school, role), "student_affairs.deactivate")


@pytest.mark.django_db
class TestTheRoleHasAWayIn:
    """عيبُ المعاينة: دورٌ يدير شؤون الطلبة وصل إلى «لم تُفعَّل صلاحيّاتُك» وقائمةٍ بلا شاشة."""

    def test_the_home_page_lands_on_the_student_affairs_dashboard(
        self, client, student_affairs_coordinator_user
    ):
        client.force_login(student_affairs_coordinator_user)

        response = client.get(reverse("dashboard"))

        assert response.status_code == 302
        assert response.url == reverse("student_affairs:dashboard")

    def test_that_dashboard_opens_for_it(self, client, student_affairs_coordinator_user):
        client.force_login(student_affairs_coordinator_user)

        assert client.get(reverse("student_affairs:dashboard")).status_code == 200

    @pytest.mark.parametrize(
        "url_name",
        (
            "student_affairs:dashboard",
            "student_affairs:student_list",
            "student_affairs:behavior_overview",
        ),
    )
    def test_the_screens_it_manages_open_for_it(self, student_affairs_coordinator_user, url_name):
        assert can_open(student_affairs_coordinator_user, url_name)

    def test_the_menu_offers_it_the_student_screens(self, client, student_affairs_coordinator_user):
        client.force_login(student_affairs_coordinator_user)

        html = client.get(reverse("student_affairs:dashboard")).content.decode()

        assert 'id="btn-student-affairs"' in html
        assert reverse("student_affairs:student_list") in html

    def test_it_is_not_offered_the_transfers_it_does_not_hold(
        self, client, student_affairs_coordinator_user
    ):
        client.force_login(student_affairs_coordinator_user)

        html = client.get(reverse("student_affairs:dashboard")).content.decode()

        assert reverse("student_affairs:transfer_list") not in html
