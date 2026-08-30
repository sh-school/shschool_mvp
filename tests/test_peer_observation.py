"""[QUALITY] تبادل الزيارات — معلّمٌ يزور زميله.

كانت الوحدة تعرف نوعين: زيارةً إشرافيّةً من أعلى، وتقييماً ذاتياً يكتبه
المعلّم عن نفسه. فلا يجد المعلّم في حسابه إلّا أن يُقيّم نفسه — وتبادلُ
الزيارات ركنٌ في التطوير المهنيّ المدرسيّ.

والزائرُ هو صاحبُ الحساب دائماً ولا يُقرأ من النموذج: زيارةٌ تُنسب إلى
غير من كتبها ليست تبادلاً بل انتحال.
"""

import pytest
from django.test import Client
from django.urls import reverse

from core.models import CustomUser
from core.models.access import Membership, Role
from core.permissions import OBSERVATION_PEER_CREATE
from quality.observation_models import OBSERVATION_KIND, ClassroomObservation


@pytest.fixture
def person(db, school):
    def _make(name, role_name="teacher"):
        user = CustomUser.objects.create(
            national_id=f"285{abs(hash(name)) % 10**8:08d}", full_name=name
        )
        role, _ = Role.objects.get_or_create(school=school, name=role_name)
        Membership.objects.create(user=user, school=school, role=role)
        return user

    return _make


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def test_the_kind_exists():
    assert ("peer", "زيارة زميل") in OBSERVATION_KIND


def test_a_teacher_may_open_the_peer_form(db, person):
    resp = _client(person("زائر")).get(reverse("observation_peer_create"), HTTP_HOST="localhost")

    assert resp.status_code == 200
    assert "زيارة زميل" in resp.content.decode()


def test_the_button_is_offered_in_the_list(db, person):
    body = (
        _client(person("معلّم"))
        .get(reverse("observation_list"), HTTP_HOST="localhost")
        .content.decode()
    )

    assert reverse("observation_peer_create") in body


def test_the_visit_records_who_wrote_it(db, person):
    visitor, colleague = person("الزائر"), person("الزميل")

    _client(visitor).post(
        reverse("observation_peer_create"),
        {"teacher": str(colleague.id), "topic": "درسٌ في الكسور"},
        HTTP_HOST="localhost",
    )

    obs = ClassroomObservation.objects.get(kind="peer")
    assert obs.observer == visitor and obs.teacher == colleague


def test_the_visitor_cannot_be_impersonated(db, person):
    """الزائرُ صاحبُ الحساب، ولو كُتب في النموذج غيرُه."""
    visitor, colleague = person("الزائر"), person("الزميل")

    _client(visitor).post(
        reverse("observation_peer_create"),
        {"teacher": str(colleague.id), "observer": str(colleague.id)},
        HTTP_HOST="localhost",
    )

    assert ClassroomObservation.objects.get(kind="peer").observer == visitor


def test_one_does_not_visit_oneself(db, person):
    """لذلك التقييم الذاتي."""
    visitor = person("الزائر")

    _client(visitor).post(
        reverse("observation_peer_create"), {"teacher": str(visitor.id)}, HTTP_HOST="localhost"
    )

    assert not ClassroomObservation.objects.filter(kind="peer").exists()


def test_a_stranger_is_not_a_colleague(db, person, school):
    """من ليس في المدرسة لا يُزار — ولو مُرّر رقمه."""
    visitor = person("الزائر")
    outsider = CustomUser.objects.create(national_id="28500000999", full_name="غريب")

    _client(visitor).post(
        reverse("observation_peer_create"), {"teacher": str(outsider.id)}, HTTP_HOST="localhost"
    )

    assert not ClassroomObservation.objects.filter(kind="peer").exists()


def test_the_visited_colleague_acknowledges_it(db, person):
    """الزيارة الإشرافية وزيارة الزميل يُقرّهما المزور — والذاتيّ لا إقرارَ فيه."""
    from quality.observation_views import _obs_perms

    visitor, colleague = person("الزائر"), person("الزميل")
    obs = ClassroomObservation.objects.create(
        school=colleague.get_school(),
        teacher=colleague,
        observer=visitor,
        kind="peer",
        status="submitted",
    )

    assert _obs_perms(colleague, obs)["can_ack"] is True
    assert _obs_perms(visitor, obs)["can_ack"] is False


@pytest.mark.parametrize("role", sorted(OBSERVATION_PEER_CREATE))
def test_whoever_may_self_assess_may_visit_a_peer(db, person, role):
    """الزيارة بين الأقران لا فوقيّة فيها: من يصلح أن يُزار يصلح أن يزور."""
    resp = _client(person(f"شخص {role}", role)).get(
        reverse("observation_peer_create"), HTTP_HOST="localhost"
    )

    assert resp.status_code == 200
