"""قائمة المستخدم: رابط «طلب إجازة» الذاتيّ وسطر الدور (W-20261012-017 وW-20261012-019).

الرابطُ بشرط `can_open` على صفحة الإجازة الذاتيّة فيصل كلَّ الكادر، ومنهم من يُحوَّل لصفحة بدء خاصّة، ولا يصل وليَّ الأمر ولا الطالب.
وسطرُ الدور يعرض الاسمَ العربيَّ للدور الفعليّ من العضويّة (`get_role_display` لا وجودَ لها على المستخدم).
"""

import pytest
from django.urls import reverse

from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

LEAVE_LABEL = "طلب إجازة"
#: أدوارٌ بصفحة بدء خاصّةٍ أو عاديّة من الكادر.
STAFF_ROLES = ("student_affairs_coordinator", "teacher", "coordinator", "principal", "secretary")
NON_STAFF_ROLES = ("parent", "student")


@pytest.fixture
def user_in_role(school):
    def _make(role_name):
        user = UserFactory(full_name=f"صاحبُ دور {role_name}")
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
        return user

    return _make


def _user_menu_html(client_as, user) -> str:
    resp = client_as(user).get("/dashboard/", follow=True)
    html = resp.content.decode()
    start = html.index('id="m-user"')
    return html[start:]


@pytest.mark.parametrize("role_name", STAFF_ROLES)
def test_staff_roles_see_the_self_leave_link(role_name, user_in_role, client_as):
    html = _user_menu_html(client_as, user_in_role(role_name))
    assert reverse("staff_affairs:leave_request_self") in html
    assert LEAVE_LABEL in html


@pytest.mark.parametrize("role_name", NON_STAFF_ROLES)
def test_parent_and_student_do_not_see_it(role_name, user_in_role, client_as):
    resp = client_as(user_in_role(role_name)).get("/", follow=True)
    assert reverse("staff_affairs:leave_request_self") not in resp.content.decode()


@pytest.mark.parametrize(
    ("role_name", "label"),
    [("principal", "مدير المدرسة"), ("teacher", "معلم")],
)
def test_user_menu_role_line_shows_the_arabic_role(role_name, label, user_in_role, client_as):
    user = user_in_role(role_name)
    assert user.role_label == label or label in user.role_label
    html = _user_menu_html(client_as, user)
    assert 'class="sd-user-role">' + user.role_label + "<" in html
    assert user.role_label


def test_role_label_is_empty_without_membership_and_does_not_break():
    assert UserFactory().role_label == ""
