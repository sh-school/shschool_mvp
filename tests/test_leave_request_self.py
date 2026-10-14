"""طلبُ الإجازة للموظّف نفسِه — W-20261009-023، قرارُ المالك D-301م («يقدّم لنفسه فقط»).

المسارُ الذاتيُّ ``leave/request/self/`` بقدرةٍ جديدةٍ ``staff_affairs.own_leave`` لكلّ الكادر،
و«إدارةُ شؤون الموظّفين» (التقديمُ نيابةً عن غيره) لم تُوسَّع.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core import permissions as perm
from core.capabilities import capability, has_capability
from staff_affairs.models import LeaveRequest
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

SELF = "staff_affairs:leave_request_self"
STAFF_ROLES = sorted(perm.ALL_STAFF_ROLES)


def _user_with_role(school, role_name, name="موظّفٌ اصطناعيّ"):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _monday_after(offset_weeks=1):
    day = timezone.localdate() + timedelta(weeks=offset_weeks)
    return day - timedelta(days=day.weekday())


def _payload(**extra):
    start = _monday_after()
    data = {
        "leave_type": "annual",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=1)).isoformat(),
        "reason": "ظرفٌ عائليّ",
    }
    data.update(extra)
    return data


class TestTheCapabilityIsForAllStaffAndNothingElse:
    def test_the_staff_roles_are_what_the_decision_names(self):
        """أدوارُ الكادر كلُّها بلا وليّ أمرٍ ولا طالب — وتُسمّى هنا فيفشل الاختبارُ إن تبدّلت."""
        assert "parent" not in STAFF_ROLES
        assert "student" not in STAFF_ROLES
        assert {"teacher", "secretary", "principal", "nurse", "vice_admin"} <= set(STAFF_ROLES)

    def test_the_capability_roles_equal_all_staff_roles(self):
        assert set(capability("staff_affairs.own_leave").roles) == set(perm.ALL_STAFF_ROLES)

    def test_manage_is_not_widened(self):
        """التقديمُ نيابةً عن غيره يبقى لحاملي إدارة شؤون الموظّفين وحدَهم."""
        assert set(capability("staff_affairs.manage").roles) == set(perm.STAFF_AFFAIRS_MANAGE)
        assert "teacher" not in perm.STAFF_AFFAIRS_MANAGE


class TestEveryStaffRoleOpensTheSelfPage:
    @pytest.mark.parametrize("role_name", STAFF_ROLES)
    def test_status_is_200_not_403(self, client_as, school, role_name):
        user = _user_with_role(school, role_name)
        response = client_as(user).get(reverse(SELF))
        assert response.status_code == 200, role_name


class TestParentAndStudentAreOut:
    def test_parent_cannot_open_it(self, client_as, parent_user):
        assert client_as(parent_user).get(reverse(SELF)).status_code in (302, 403)
        assert not has_capability(parent_user, "staff_affairs.own_leave")

    def test_student_cannot_open_it(self, client_as, student_user):
        assert client_as(student_user).get(reverse(SELF)).status_code in (302, 403)
        assert not has_capability(student_user, "staff_affairs.own_leave")

    def test_parent_and_student_cannot_post_a_request(self, client_as, parent_user, student_user):
        for user in (parent_user, student_user):
            response = client_as(user).post(reverse(SELF), _payload())
            assert response.status_code in (302, 403)
            assert not LeaveRequest.objects.filter(staff=user).exists()

    def test_the_dashboard_of_a_student_has_no_link(self, client_as, student_user):
        response = client_as(student_user).get(reverse("dashboard"), follow=True)
        assert reverse(SELF) not in response.content.decode()


class TestSelfRequestBindsTheCurrentUser:
    def test_creates_a_request_for_the_user_himself(self, client_as, school, teacher_user):
        response = client_as(teacher_user).post(reverse(SELF), _payload())
        assert response.status_code == 302
        leave = LeaveRequest.objects.get()
        assert leave.staff_id == teacher_user.id
        assert leave.school_id == school.id

    def test_a_posted_staff_id_is_ignored(self, client_as, school, teacher_user):
        other = _user_with_role(school, "nurse", "ممرّضٌ آخر")
        client_as(teacher_user).post(reverse(SELF), _payload(staff_id=str(other.id)))
        leave = LeaveRequest.objects.get()
        assert leave.staff_id == teacher_user.id
        assert not LeaveRequest.objects.filter(staff=other).exists()

    def test_the_form_has_no_staff_field(self, client_as, teacher_user):
        page = client_as(teacher_user).get(reverse(SELF)).content.decode()
        assert 'name="staff_id"' not in page

    def test_a_service_rule_still_applies(self, client_as, teacher_user):
        """الخدمةُ بلا تغيير: إجازةُ زواجٍ بلا مرفقٍ تُرفض كما في المسار القديم."""
        response = client_as(teacher_user).post(reverse(SELF), _payload(leave_type="marriage"))
        assert response.status_code == 200
        assert not LeaveRequest.objects.exists()

    def test_the_user_sees_only_his_own_requests(self, client_as, school, teacher_user):
        other = _user_with_role(school, "nurse", "ممرّضٌ آخر")
        client_as(other).post(reverse(SELF), _payload(reason="سببُ الآخر الفريد"))
        client_as(teacher_user).post(reverse(SELF), _payload(reason="سببي"))
        page = client_as(teacher_user).get(reverse(SELF)).content.decode()
        assert page.count("<tr>") == 2  # ترويسةٌ وطلبٌ واحد
        assert "سببُ الآخر الفريد" not in page


class TestUserWithoutMembershipSeesAMessage:
    def test_departed_user_gets_a_clear_page_not_500(self, client_as, school, teacher_user):
        from core.models.access import Membership

        Membership.objects.filter(user=teacher_user).update(is_active=False)
        response = client_as(teacher_user).get(reverse(SELF))
        assert response.status_code in (200, 302, 403)
        if response.status_code == 200:
            assert "لا انتسابَ فعّالاً" in response.content.decode()
            posted = client_as(teacher_user).post(reverse(SELF), _payload())
            assert posted.status_code != 500
            assert not LeaveRequest.objects.exists()


class TestDashboardsShowTheSelfLink:
    @pytest.mark.parametrize("role_name", STAFF_ROLES)
    def test_every_staff_dashboard_links_to_the_self_path(self, client_as, school, role_name):
        user = _user_with_role(school, role_name)
        response = client_as(user).get(reverse("dashboard"), follow=True)
        assert response.status_code == 200, role_name
        html = response.content.decode()
        redirected = response.redirect_chain
        if redirected:  # لوحةٌ خاصّةٌ بالدور (بوّابةٌ لا لوحة) — خارج قوالب dashboard/roles
            pytest.skip(f"{role_name}: يُحوَّل إلى {redirected[-1][0]}")
        assert reverse(SELF) in html, role_name
        # الرابطُ الكاملُ بعلامة الاقتباس: المسارُ القديم بادئةٌ لمسار الذاتيّ فلا يصحّ البحثُ بنصّه وحده.
        assert f'href="{reverse("staff_affairs:leave_request")}"' not in html, role_name
