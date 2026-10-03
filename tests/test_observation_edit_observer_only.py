"""[QUALITY] تعديلُ الزيارة الصفّيّة للزائر صاحبِها وحدَه (بلاغ المالك W-20261002-015).

لا قيادةٌ ولا مستخدمٌ فائقٌ ولا معلّمٌ ولا زائرٌ آخر — حتى المطوّر (استثناءٌ من D-118م لهذه الشاشة بقرار المالك).
فالتقييمُ شهادةُ كاتبِه: من يملك الاطّلاعَ لا يملك تغييرَ ما كُتب، والقيادةُ تسحب المرسَلةَ وتُعيد فتحَ المُقَرّة
فيعدّلها صاحبُها.
"""

import pytest
from django.urls import reverse

from quality.observation_views import _obs_perms
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_observation_crud import _make_obs  # noqa: F401 — مساعدُ الإنشاء نفسُه

pytestmark = pytest.mark.django_db


def _superuser(school):
    user = UserFactory(full_name="مستخدمٌ فائق", is_superuser=True, is_staff=True)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    return user


def _other_observer(school):
    user = UserFactory(full_name="زائرٌ آخر")
    role = RoleFactory(school=school, name="academic_coordinator")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.mark.parametrize("who", ["principal", "teacher", "superuser", "other_observer"])
@pytest.mark.parametrize("status", ["draft", "submitted"])
def test_only_the_observer_may_edit_a_visit(
    client_as, school, coordinator_user, principal_user, teacher_user, who, status
):
    """مدير ومعلّم ومستخدمٌ فائق وزائرٌ آخر: كلُّهم مرفوضون، في المسودّة والمرسَلة، على القراءة والكتابة."""
    actor = {
        "principal": principal_user,
        "teacher": teacher_user,
        "superuser": _superuser(school),
        "other_observer": _other_observer(school),
    }[who]
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status=status)
    topic_before = obs.topic

    perms = _obs_perms(actor, obs)
    assert perms["can_edit"] is False
    assert perms["can_submit"] is False
    client = client_as(actor)
    url = reverse("observation_edit", args=[obs.id])
    assert client.get(url).status_code == 403
    assert client.post(url, {"topic": "تعديلٌ مرفوض"}).status_code == 403
    obs.refresh_from_db()
    assert obs.topic == topic_before


@pytest.mark.parametrize("status", ["draft", "submitted"])
def test_the_observer_still_edits_his_own_visit(school, coordinator_user, teacher_user, status):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status=status)

    assert _obs_perms(coordinator_user, obs)["can_edit"] is True


def test_nobody_edits_an_acknowledged_visit_not_even_the_observer(
    school, coordinator_user, teacher_user
):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="acknowledged")

    assert _obs_perms(coordinator_user, obs)["can_edit"] is False
