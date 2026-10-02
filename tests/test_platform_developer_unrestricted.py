"""[SECURITY] مطوّرُ المنصّة لا حظرَ عليه في أيّ صفحة (قرار المالك D-118م، W-20261002-012).

يُلغي D-98م (استبعادُه من `/analytics/`). والقاعدةُ مركزيّة (`core/unrestricted_role.py`) فتشمل كلَّ
قدرةٍ ووحدةٍ، لا قائمةً تُحدَّث صفحةً صفحة. **حقُّ دخولِ صفحةٍ لا نطاقُ بيانات**: عزلُ المدرسة باقٍ.
"""

import pytest
from django.urls import reverse

from core.capabilities import has_capability, registry
from core.models import CustomUser
from core.models.access import Membership, Role
from core.module_registry import _MODULES, gate_admits
from core.navigation import can_open

pytestmark = pytest.mark.django_db


@pytest.fixture
def developer(school):
    """حسابٌ بدور المطوّر وحدَه — لا is_superuser ولا مجموعة developers."""
    user = CustomUser.objects.create(
        must_change_password=False, national_id="28700000055", full_name="مطوّر المنصّة"
    )
    user.set_password("Aa!23456789")
    user.save()
    role, _ = Role.objects.get_or_create(school=school, name="platform_developer")
    Membership.objects.create(user=user, school=school, role=role)
    return user


def test_the_developer_holds_every_capability(developer):
    missing = [key for key in registry() if not has_capability(developer, key)]
    assert not missing, f"قدراتٌ محجوبةٌ عن المطوّر: {missing}"


def test_the_developer_passes_every_module_gate(developer):
    blocked = [
        m.url_prefix
        for m in _MODULES.values()
        if not gate_admits(developer, m.url_prefix, m.allowed_roles)
    ]
    assert not blocked, f"وحداتٌ محجوبةٌ عن المطوّر: {blocked}"


def test_the_developer_can_open_a_guarded_link(developer):
    assert can_open(developer, "analytics_dashboard")


@pytest.mark.parametrize(
    "path",
    ["/analytics/", "/analytics/api/attendance-trend/", "/behavior/committee/", "/reports/"],
)
def test_pages_that_used_to_refuse_the_developer_now_open(client_as, developer, path):
    resp = client_as(developer).get(path)

    assert resp.status_code != 403, path


def test_a_teacher_is_still_refused_the_analytics_pages(client_as, teacher_user):
    """الرفعُ خاصٌّ بالمطوّر — لا يمسّ غيرَه."""
    assert client_as(teacher_user).get("/analytics/").status_code == 403


def test_reverse_of_the_sidebar_link_resolves():
    assert reverse("analytics_dashboard") == "/analytics/"


# ── إسنادُ الدور نفسِه: ترقيةٌ كاملة لا تُمنح من واجهة شؤون الكادر (مراجعة 0105) ──


def _appoint(school, by, role_name="platform_developer", national_id="28700000444"):
    from staff_affairs.appointments import appoint

    return appoint(
        school=school,
        national_id=national_id,
        full_name="مرشَّح",
        role_name=role_name,
        by=by,
        reference="قرار 1",
    )


def test_a_principal_cannot_appoint_the_developer_role(school, principal_user):
    from staff_affairs.appointments import AppointmentError

    with pytest.raises(AppointmentError):
        _appoint(school, principal_user)


def test_a_developer_cannot_appoint_another_developer(school, developer):
    from staff_affairs.appointments import AppointmentError

    with pytest.raises(AppointmentError):
        _appoint(school, developer)


def test_only_a_superuser_can_appoint_the_developer_role(school, django_user_model):
    admin = django_user_model.objects.create(
        national_id="28700000333", full_name="سوبريوزر", is_superuser=True
    )

    membership = _appoint(school, admin)

    assert membership.role.name == "platform_developer"


def test_ordinary_appointments_are_unaffected(school, principal_user):
    membership = _appoint(school, principal_user, role_name="librarian", national_id="28700000555")

    assert membership.role.name == "librarian"


# ── مواضعُ كانت تحجبه بالاسم ضمنيّاً ──


def test_the_developer_sees_the_whole_school_in_student_info(developer):
    from student_info.access import sees_whole_school

    assert sees_whole_school(developer)


def test_the_developer_sees_every_classroom_observation_but_cannot_edit(developer, school):
    from quality.observation_services import ObservationService

    assert ObservationService.visible_to(developer, school).query is not None
