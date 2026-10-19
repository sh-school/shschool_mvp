"""تبديلُ الدور العامل وزرعُ الأدوار وتحذيرُ الإدارة (W-20261019-008، قرار المالك 2026-10-19).

الجذر: دورٌ جديدٌ لموظّفٍ قائم يتركه على دوره القديم (أقدمُ عضويّةِ كادرٍ تحكم) ورابطُ «تبديل الدور»
ميّت. فهنا: الحاكمُ الافتراضيّ كما هو، واختيارُ الموظّف يُحفظ ويُطبَّق، وعضويّةُ غيره أو غير النشطة تُرفض.
"""

from datetime import date

import pytest
from django.contrib import messages
from django.contrib.admin.sites import site
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command

from core.management.commands.import_staff_register import role_for
from core.models import Membership, Role
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/auth/choose-role/"


def _staff_with_two_roles(school):
    """معلّمٌ منذ 2020 ثمّ مُنح «منسق شؤون الطلبة» حديثاً — العضويّتان نشطتان."""
    user = UserFactory()
    old = MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name="teacher"),
        joined_at=date(2020, 9, 1),
    )
    new = MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name="student_affairs_coordinator"),
        joined_at=date(2026, 10, 1),
    )
    return user, old, new


def _role_seen_by(client, user):
    client.force_login(user)
    return client.get(URL).wsgi_request.user.get_role()


def test_without_a_choice_nobody_changes_role_automatically(client, school):
    user, _old, _new = _staff_with_two_roles(school)
    assert _role_seen_by(client, user) == "teacher"


def test_the_employee_switches_and_the_choice_persists_across_requests(client, school):
    user, _old, new = _staff_with_two_roles(school)
    client.force_login(user)
    response = client.post(URL, {"membership_id": str(new.pk)})
    assert response.status_code == 302
    assert client.get(URL).wsgi_request.user.get_role() == "student_affairs_coordinator"
    assert client.get("/").wsgi_request.user.get_role() == "student_affairs_coordinator"


def test_the_switch_can_go_back_to_the_default_role(client, school):
    user, old, new = _staff_with_two_roles(school)
    client.force_login(user)
    client.post(URL, {"membership_id": str(new.pk)})
    client.post(URL, {"membership_id": str(old.pk)})
    assert client.get(URL).wsgi_request.user.get_role() == "teacher"


def test_another_users_membership_is_refused_and_nothing_changes(client, school):
    user, _old, _new = _staff_with_two_roles(school)
    stranger = MembershipFactory(
        school=school, role=RoleFactory(school=school, name="principal"), user=UserFactory()
    )
    client.force_login(user)
    client.post(URL, {"membership_id": str(stranger.pk)})
    assert client.get(URL).wsgi_request.user.get_role() == "teacher"


def test_an_inactive_membership_is_refused(client, school):
    user, _old, new = _staff_with_two_roles(school)
    Membership.objects.filter(pk=new.pk).update(is_active=False)
    client.force_login(user)
    client.post(URL, {"membership_id": str(new.pk)})
    assert client.get(URL).wsgi_request.user.get_role() == "teacher"


def test_a_saved_choice_that_became_inactive_falls_back_to_the_default(client, school):
    user, _old, new = _staff_with_two_roles(school)
    client.force_login(user)
    client.post(URL, {"membership_id": str(new.pk)})
    Membership.objects.filter(pk=new.pk).update(is_active=False)
    assert client.get(URL).wsgi_request.user.get_role() == "teacher"


def test_the_page_lists_only_my_active_memberships(client, school):
    user, _old, new = _staff_with_two_roles(school)
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name="nurse"),
        is_active=False,
    )
    client.force_login(user)
    page = client.get(URL)
    assert page.status_code == 200
    assert {m.pk for m in page.context["memberships"]} == {_old.pk, new.pk}


def test_the_menu_link_points_to_a_live_route(client, school):
    user, _old, _new = _staff_with_two_roles(school)
    client.force_login(user)
    html = client.get(URL).content.decode()
    assert 'href="/auth/choose-role/"' in html


def test_seed_creates_every_role_name_for_every_school_without_duplicates():
    first, second = SchoolFactory(), SchoolFactory()
    call_command("seed_new_roles")
    call_command("seed_new_roles")
    names = {name for name, _label in Role.ROLES}
    for school in (first, second):
        got = list(Role.objects.filter(school=school).values_list("name", flat=True))
        assert names <= set(got)
        assert len(got) == len(set(got))


@pytest.mark.parametrize("title", ["منسق شؤون الطلبة", "منسق شؤون الطلاب"])
def test_the_new_job_titles_resolve_to_the_student_affairs_coordinator(title):
    assert role_for(title) == "student_affairs_coordinator"


def test_other_coordinator_titles_still_resolve_as_before():
    assert role_for("منسق شؤون الطلبة") != "coordinator"


def _save_through_admin(school, user, role_name):
    from django.test import RequestFactory

    admin_obj = site._registry[Membership]
    request = RequestFactory().post("/admin/core/membership/add/")
    request.session = {}
    request._messages = FallbackStorage(request)
    request.user = UserFactory(is_staff=True, is_superuser=True)
    obj = Membership(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    admin_obj.save_model(request, obj, form=None, change=False)
    return obj, [str(m) for m in messages.get_messages(request)]


def test_admin_warns_but_does_not_block_a_second_active_staff_membership(school):
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    obj, warnings = _save_through_admin(school, user, "student_affairs_coordinator")
    assert Membership.objects.filter(pk=obj.pk).exists()
    assert warnings and "عضويّةُ كادرٍ نشطةٌ أخرى" in warnings[0]


def test_admin_is_silent_for_a_single_membership_or_a_parent_second_role(school):
    user = UserFactory()
    _obj, none = _save_through_admin(school, user, "teacher")
    assert none == []
    _obj, still_none = _save_through_admin(school, user, "parent")
    assert still_none == []
