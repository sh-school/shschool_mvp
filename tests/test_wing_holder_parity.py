"""تطابقُ الميدانيّ مع مشرف الجناح: الواجهةُ والقدرات (W-20261123-003).

قرارُ المالك 2026-11-23: حاملُ الجناح بأيّ دورٍ يرى نوافذَ المشرف وقوائمَه وقدراتِه ليعمل بدله
عند غيابه — بالتعيين لا بالدور، ولا يتغيّر دورٌ أساسيّ. والاستثناءُ الوحيدُ تصويتُ لجنة السلوك.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.capabilities import has_capability
from core.capabilities.base import WING_PARITY_EXCEPTIONS
from core.capabilities.registry import registry
from core.models import Wing, WingAssignment
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _user(school, role, nid):
    user = UserFactory(full_name=f"مستخدم {nid}", national_id=nid)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _wing(school, supervisor):
    return Wing.objects.create(
        school=school,
        code="wp",
        name="wp",
        academic_year=academic_year_for_school(school),
        supervisor=supervisor,
    )


def _assign_field(wing, user):
    WingAssignment.objects.create(
        wing=wing,
        user=user,
        role="field_supervisor",
        start_date=timezone.localdate() - dt.timedelta(days=1),
    )


@pytest.fixture
def parity(school):
    """مشرفٌ بدوره، وملاحظُ طلبةٍ معيَّنٌ ميدانيّاً، وملاحظٌ غيرُ معيَّن."""
    sup = _user(school, "admin_supervisor", "29000000601")
    field = _user(school, "student_observer", "29000000602")
    other = _user(school, "student_observer", "29000000603")
    _assign_field(_wing(school, sup), field)
    return sup, field, other


def test_assigned_observer_sees_supervisor_menus(client, parity):
    _, field, other = parity

    client.force_login(field)
    html = client.get(reverse("dashboard")).content.decode()
    assert 'id="m-wing-students"' in html
    assert reverse("wings:record_index") in html
    assert has_capability(field, "wings.floors")

    # غيرُ المعيَّن لا يرى قوائمَ المشرف
    client.force_login(other)
    html = client.get(reverse("dashboard")).content.decode()
    assert 'id="m-wing-students"' not in html
    assert not has_capability(other, "wings.floors")


def test_wing_holder_has_every_supervisor_capability_except_the_vote(parity):
    sup, field, other = parity
    registry_ = registry()
    missing = [
        key
        for key, cap in registry_.items()
        if "admin_supervisor" in cap.expanded_roles
        and key not in WING_PARITY_EXCEPTIONS
        and has_capability(sup, key)
        and not has_capability(field, key)
    ]
    assert missing == []
    # الاستثناءُ الصريحُ وحدَه: لا مقعدَ تصويتٍ بالتعيين، وللمشرف بدوره
    assert set(WING_PARITY_EXCEPTIONS) == {"behavior.committee"}
    assert not has_capability(field, "behavior.committee")
    # والتطابقُ بالتعيين لا بالدور: غيرُ المعيَّن لا يرث شيئاً
    assert not has_capability(other, "behavior.statistics")
    assert has_capability(field, "behavior.statistics")
    # الدورُ الأساسيُّ لم يتغيّر
    assert field.get_role() == "student_observer"
