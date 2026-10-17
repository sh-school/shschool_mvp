"""[SCHEDULE] حصرُ توليد الجدول واعتماده بمطوّر المنصّة (W-20261010-034، أمرُ المالك 2026-10-10).

المنفذُ الواحدُ في `core/capabilities.py` يغطّي المسارات الأربعة: `schedule.admin` (توليد، تقدّم، إيقاف، مختبر)
و`schedule.operator` المفوَّضة و`schedule.approve` و`approve_schedule` المتحقَّقة بـ`schedule.settings`.
والمديرُ والنائبُ يقرآن الجدولَ كما كان. والمفتاحُ `SCHEDULE_DEVELOPER_ONLY` يُطفأ فيعود السلوكُ السابق.
"""

import pytest
from django.test import override_settings
from django.urls import reverse

from core import capability_grants as grants
from core.capabilities import SCHEDULE_DEVELOPER_ONLY_MESSAGE, has_capability
from core.models import AuditLog
from operations.models import ScheduleGeneration
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

ON = override_settings(SCHEDULE_DEVELOPER_ONLY=True)
OFF = override_settings(SCHEDULE_DEVELOPER_ONLY=False)
BLOCKED_ROLES = ["principal", "vice_academic", "admin"]


def staff(school, role):
    user = UserFactory(full_name="سرّي-الاسم")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def operator(school):
    """معلّمٌ مفوَّضٌ بـ`schedule.operator` — كان يولّد الجدولَ بالتفويض."""
    teacher = staff(school, "teacher")
    boss = staff(school, "principal")
    grants.grant(
        user=teacher,
        capability="schedule.operator",
        by=boss,
        reason="تكليفٌ بمسؤوليّة الجدول العامّ للاختبار",
    )
    return teacher


def draft(school):
    return ScheduleGeneration.objects.create(
        school=school, academic_year="2026-2027", status="draft", config_snapshot={}
    )


def _paths(school):
    gen = draft(school)
    return {
        "generate": ("post", reverse("smart_generate")),
        "status": ("get", reverse("smart_generate_status")),
        "page": ("get", reverse("smart_schedule")),
        "lab": ("get", reverse("schedule_quality_lab")),
        "stop": ("post", reverse("stop_schedule_generation", args=[gen.pk])),
        "v2_progress": ("get", reverse("schedule_v2_progress", args=[gen.pk])),
        "v2_stop": ("post", reverse("schedule_v2_stop", args=[gen.pk])),
        "approve": ("post", reverse("approve_schedule", args=[gen.pk])),
    }


def _call(client, spec):
    method, url = spec
    return getattr(client, method)(url)


@pytest.mark.parametrize("who", [*BLOCKED_ROLES, "operator"])
@ON
def test_everyone_but_the_developer_is_refused_on_every_path_with_a_visible_reason(
    client_as, school, who
):
    user = operator(school) if who == "operator" else staff(school, who)
    client = client_as(user)
    for name, spec in _paths(school).items():
        response = _call(client, spec)
        assert response.status_code == 403, name
        assert SCHEDULE_DEVELOPER_ONLY_MESSAGE.split("،")[0] in response.content.decode(), name


@ON
def test_the_developer_is_not_refused_by_the_switch(client_as, school):
    client = client_as(staff(school, "platform_developer"))
    for name, spec in _paths(school).items():
        assert _call(client, spec).status_code != 403, name


@pytest.mark.parametrize("key", ["schedule.admin", "schedule.operator", "schedule.approve"])
@ON
def test_has_capability_closes_the_non_view_paths_too(school, key):
    for role in BLOCKED_ROLES:
        assert not has_capability(staff(school, role), key), (role, key)
    assert not has_capability(operator(school), "schedule.operator")
    assert has_capability(staff(school, "platform_developer"), key)


@OFF
def test_with_the_switch_off_the_previous_behaviour_returns(client_as, school):
    for role in BLOCKED_ROLES[:2]:
        client = client_as(staff(school, role))
        assert client.get(reverse("smart_schedule")).status_code != 403
        assert has_capability(staff(school, role), "schedule.admin")
    assert has_capability(operator(school), "schedule.operator")


@ON
def test_the_principal_and_vice_still_read_the_schedule_and_open_the_settings(client_as, school):
    for role in ("principal", "vice_academic"):
        client = client_as(staff(school, role))
        assert client.get(reverse("weekly_schedule")).status_code == 200, role
        assert client.get(reverse("schedule_settings")).status_code == 200, role


@ON
def test_each_refusal_is_audited_by_role_and_path_without_the_user_name(client_as, school):
    principal = staff(school, "principal")
    client_as(principal).post(reverse("smart_generate"))
    row = AuditLog.objects.filter(object_repr__contains="محصورٌ بمطوّر المنصّة").get()
    assert row.changes["role"] == "principal"
    assert row.changes["path"] == reverse("smart_generate")
    assert "سرّي-الاسم" not in str(row.changes) + row.object_repr


@ON
def test_a_refused_approval_leaves_the_draft_untouched(client_as, school):
    gen = draft(school)
    client_as(staff(school, "vice_academic")).post(reverse("approve_schedule", args=[gen.pk]))
    gen.refresh_from_db()
    assert gen.status == "draft"


def test_the_default_in_production_settings_is_on():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    text = (root / "shschool/settings/base.py").read_text(encoding="utf-8")
    assert 'config("SCHEDULE_DEVELOPER_ONLY", default=True, cast=bool)' in text
