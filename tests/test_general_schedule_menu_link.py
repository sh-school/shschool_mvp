"""[NAV] «الجدول العام» في قائمة «إدارة الشؤون الأكاديميّة» تحت «الجدولة الذكية» مباشرةً (طلبُ المالك 2026-09-25).

كان الوصولُ إلى الجدول العامّ من قائمة الإدارة الأكاديميّة يحتاج مساراً أطول؛ فصار بندٌ واحدٌ بين «الجدولة الذكية» و«إعدادات الجدول»،
شرطُه `can_open:"weekly_schedule"` **وحدَه** (لا قيدَ الأدوار الثلاثة) فيراه كلُّ من يفتح القائمة ويملك فتحَه — كما يقول تعليقُ القائمة
«كلُّ قسمٍ فيه عنصرٌ متاحٌ لكلّ من يفتحها فلا يفرغ عمودٌ». ولا يتبدّل من يرى «الجدولة الذكية» و«الإعدادات».
"""

import re

import pytest
from django.urls import reverse

from tests.conftest import MembershipFactory, RoleFactory, UserFactory

#: من يرى الجدولةَ الذكيّةَ وإعداداتِها (شرطُ الأدوار في القالب).
SCHEDULE_MANAGERS = ("principal", "vice_academic")
#: قائمةُ الإدارة الأكاديميّة تُعرض للقيادة (`is_leadership`)؛ ومنها من لا يدير الجدولة.
LEADERS_WITHOUT_SCHEDULE_MANAGEMENT = ("vice_admin",)


@pytest.fixture
def user_in_role(db, school):
    def _make(role_name):
        role = RoleFactory(school=school, name=role_name)
        user = UserFactory(full_name=f"صاحبُ دور {role_name}")
        MembershipFactory(user=user, school=school, role=role)
        return user

    return _make


def _academic_menu_hrefs(html: str) -> list[str]:
    """روابطُ `role="menuitem"` في لوحة `#m-academic` بترتيب ظهورها."""
    start = html.index('id="m-academic"')
    following = re.search(r'<div class="sd-menu[^"]*" id="m-', html[start + 1 :])
    end = start + 1 + following.start() if following else len(html)
    hrefs = []
    for tag in re.findall(r"<a\b[^>]*>", html[start:end]):
        if 'role="menuitem"' in tag:
            found = re.search(r'href="([^"]+)"', tag)
            if found:
                hrefs.append(found.group(1))
    return hrefs


def _hrefs_for(role_name, user_in_role, client_as) -> list[str]:
    page = client_as(user_in_role(role_name)).get("/dashboard/", follow=True)
    assert page.status_code == 200, f"{role_name}: {page.status_code}"
    return _academic_menu_hrefs(page.content.decode())


@pytest.mark.parametrize("role_name", SCHEDULE_MANAGERS)
def test_the_general_schedule_sits_right_under_the_smart_schedule(
    role_name, user_in_role, client_as
):
    hrefs = _hrefs_for(role_name, user_in_role, client_as)
    smart, general, settings = (
        reverse("smart_schedule"),
        reverse("weekly_schedule"),
        reverse("schedule_settings"),
    )
    assert smart in hrefs and general in hrefs and settings in hrefs, hrefs
    assert hrefs.index(general) == hrefs.index(smart) + 1, hrefs
    assert hrefs.index(settings) == hrefs.index(general) + 1, hrefs


@pytest.mark.parametrize("role_name", LEADERS_WITHOUT_SCHEDULE_MANAGEMENT)
def test_the_general_schedule_is_offered_without_the_management_pages(
    role_name, user_in_role, client_as
):
    """البندُ بلا قيد الأدوار الثلاثة: يراه من لا يرى الجدولةَ الذكيّةَ ولا الإعدادات — ولا تُكشف له هاتان."""
    hrefs = _hrefs_for(role_name, user_in_role, client_as)
    assert reverse("weekly_schedule") in hrefs, hrefs
    assert reverse("smart_schedule") not in hrefs, hrefs
    assert reverse("schedule_settings") not in hrefs, hrefs
