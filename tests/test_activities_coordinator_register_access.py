"""[PDPPL] منسّقُ الأنشطة لا يرث سجلَّ الطلبة (بطاقة W-20261010-012، حكم 0104).

يرث منسّقُ الأنشطة المنسّقَ في ``ROLE_INHERITS``، فكان يفتح سجلَّ الطلبة (``student_affairs.view``) ويرى
اسمَ وليّ الأمر وهاتفَه وهو لا يتّصل بالأسر (قاعدةُ الحاجة). والتضييقُ بحقل ``not_inherited_by`` على القدرة
وحدَها — لا بحذف الوراثة، التي تُفقده ثمانيَ عشرة قدرةً يعمل بها (الدرجات والحضور والتبديل...).

المحروس هنا: (١) الفرقُ بين المصفوفة قبل وبعد قدرةٌ واحدةٌ لدورٍ واحد؛ (٢) السجلُّ والحارسُ وhas_capability
يجيبون جواباً واحداً؛ (٣) الشاشاتُ والبحثُ العامُّ والرابطُ في القائمة؛ (٤) ما يرثه من غيرها باقٍ.
"""

import pytest
from django.urls import reverse

from core.capabilities import capability, has_capability, registry
from core.navigation import can_open
from core.permissions import expand_roles
from tests.test_guardian_name_need_to_know import (  # noqa: F401 — الطالبُ ووليُّه وعلامتُه نفسُها
    GUARDIAN,
    _staff,
    child,
)
from tests.test_period_register import klass, supervisor, year  # noqa: F401

pytestmark = pytest.mark.django_db

ACTIVITIES = "activities_coordinator"
LIST = "student_affairs:student_list"


def test_the_only_change_is_one_capability_for_one_role():
    """مصفوفةُ كلّ الأدوار قبل التضييق وبعده: الفرقُ student_affairs.view لمنسّق الأنشطة وحدَه."""
    diff = {}
    for key, cap in registry().items():
        before = expand_roles(set(cap.roles))  # الوراثةُ كما كانت بلا استثناء
        after = set(cap.expanded_roles)
        if before != after and key != "behavior.record":  # استثناءُ المساعدين بطاقةُ W-20261010-013
            diff[key] = before - after
    assert diff == {"student_affairs.view": {ACTIVITIES}}


@pytest.mark.parametrize(
    "role", ["coordinator", "vice_academic", "principal", "e_projects_coordinator"]
)
def test_every_other_inheriting_role_keeps_its_capabilities(role):
    held = {k for k, cap in registry().items() if role in cap.expanded_roles}
    held_before = {k for k, cap in registry().items() if role in expand_roles(set(cap.roles))}
    assert held == held_before


def test_the_activities_coordinator_keeps_the_other_inherited_capabilities(school):
    user = _staff(school, ACTIVITIES, "29000007001")
    for key in (
        "attendance.mark",
        "assessments.enter_grades",
        "swap.request",
        "workload.edit",
        "student_affairs.activities",
        "behavior.record",
    ):
        assert has_capability(user, key), key
    assert not has_capability(user, "student_affairs.view")


def test_the_registry_the_guard_and_has_capability_agree(school):
    from student_affairs import views

    cap = capability("student_affairs.view")
    user = _staff(school, ACTIVITIES, "29000007002")

    assert ACTIVITIES not in cap.expanded_roles
    assert ACTIVITIES not in views.student_list._required_roles
    assert set(views.student_list._required_roles) == set(cap.expanded_roles)
    assert has_capability(user, "student_affairs.view") is False
    # وإن ذُكر الدورُ صراحةً حمل القدرة: الاستثناءُ من الوراثة لا حظرٌ للدور.
    assert ACTIVITIES in expand_roles({"coordinator", ACTIVITIES}, not_inherited_by={ACTIVITIES})


@pytest.mark.parametrize(
    "name", ["student_affairs:student_list", "student_affairs:student_list_pdf"]
)
def test_the_activities_coordinator_is_refused_the_register_and_its_pdf(
    client_as, school, seeded_calendar, supervisor, child, name
):
    user = _staff(school, ACTIVITIES, "29000007003")
    response = client_as(user).get(reverse(name))

    assert response.status_code == 403
    assert GUARDIAN not in response.content.decode()


def test_the_activities_coordinator_gets_no_register_link(school):
    user = _staff(school, ACTIVITIES, "29000007004")
    assert can_open(user, LIST) is False
    assert can_open(_staff(school, "coordinator", "29000007005"), LIST) is True


def test_the_global_search_never_leaks_a_guardian_to_the_activities_coordinator(
    client_as, school, seeded_calendar, supervisor, child
):
    user = _staff(school, ACTIVITIES, "29000007006")
    response = client_as(user).get(reverse("global_search"), {"q": GUARDIAN[:6]})

    assert GUARDIAN not in response.content.decode()


@pytest.mark.parametrize("role", ["coordinator", "vice_academic", "principal"])
def test_the_inheriting_roles_still_open_the_register_with_the_guardian(
    client_as, school, seeded_calendar, supervisor, child, role
):
    user = _staff(school, role, "29000007100")
    response = client_as(user).get(reverse(LIST))

    assert response.status_code == 200
    assert GUARDIAN in response.content.decode()
