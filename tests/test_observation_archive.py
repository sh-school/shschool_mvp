"""[QUALITY] أرشيف الزيارات الصفّية — الحذف الناعم يصير قابلاً للرؤية والاستعادة.

كان `archive()` يُنادى من زرّ الحذف، و`restore()` مكتوبةً **لا تُنادى من أيّ
موضع**، و`all_objects` معلّقاً عليه «للأرشيف/الإدارة» ولا يستعمله شيء. فلا
مسار ولا واجهة ولا زرّ.

ورسالة الحذف تَعِد المستخدم: «محفوظة في الأرشيف ويمكن استرجاعها» — وهو صادقٌ
في القاعدة وغير قابل للتحقّق من الواجهة. أي أن الحذف الناعم كان يتصرّف كحذفٍ
نهائيّ في نظر من يستعمله، والوعد لا يُوفى.
"""

import pytest
from django.urls import reverse

from core.models import Role
from quality.observation_models import ClassroomObservation, ObservationCriterion
from quality.observation_services import ObservationService


def _make_obs(school, observer, teacher, status="draft"):
    obs = ClassroomObservation.objects.create(
        school=school, teacher=teacher, observer=observer, created_by=observer, status=status
    )
    crit, _ = ObservationCriterion.objects.get_or_create(
        school=school, domain="planning", text="معيار", defaults={"order": 1}
    )
    ObservationService.save_scores(obs, {str(crit.id): "complete"}, {})
    obs.refresh_from_db()
    return obs


# ══════════════════════ الأرشيف يُقرأ ═══════════════════════════════


@pytest.mark.django_db
def test_an_archived_observation_leaves_the_live_list(school, principal_user, teacher_user):
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)

    live = ObservationService.visible_to(principal_user, school)

    assert obs not in live


@pytest.mark.django_db
def test_the_archive_shows_what_the_live_list_hides(school, principal_user, teacher_user):
    """هذا هو العطب الأصلي: كان يُحذف ولا يظهر في أيّ موضع."""
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)

    archived = ObservationService.archived_for(principal_user, school)

    assert obs in archived


@pytest.mark.django_db
def test_the_archive_keeps_the_scores(school, principal_user, teacher_user):
    """الحذف الناعم يحفظ الزيارة **وتقييماتها** — وإلا فالاستعادة تُرجع هيكلاً فارغاً."""
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)

    restored = ObservationService.archived_for(principal_user, school).get(pk=obs.pk)

    assert restored.scores.count() == 1


@pytest.mark.django_db
def test_the_archive_respects_the_same_scope_as_the_live_list(
    client, school, principal_user, teacher_user
):
    """معلّمٌ آخر لا يرى في الأرشيف ما لا يراه حيّاً."""
    from tests.conftest import MembershipFactory, UserFactory

    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)
    role, _ = Role.objects.get_or_create(school=school, name="teacher")
    other = UserFactory(full_name="معلّم آخر")
    MembershipFactory(user=other, school=school, role=role)

    assert obs not in ObservationService.archived_for(other, school)


# ══════════════════════ الاستعادة ═══════════════════════════════════


@pytest.mark.django_db
def test_restoring_returns_the_observation_to_the_live_list(
    client, school, principal_user, teacher_user
):
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)
    client.force_login(principal_user)

    resp = client.post(reverse("observation_restore", args=[obs.id]))

    assert resp.status_code == 302
    assert obs in ObservationService.visible_to(principal_user, school)


@pytest.mark.django_db
def test_a_teacher_cannot_restore_what_leadership_archived(
    client, school, principal_user, teacher_user
):
    """الاستعادة تتبع صلاحية الحذف لا صلاحية القراءة.

    المعلّم يرى ملاحظته ولا يملك حذفها، فلا يُعقل أن يُرجع ما أرشفته القيادة.
    """
    obs = _make_obs(school, principal_user, teacher_user, status="submitted")
    ObservationService.archive(obs, principal_user)
    client.force_login(teacher_user)

    resp = client.post(reverse("observation_restore", args=[obs.id]))

    assert resp.status_code == 403
    assert obs not in ObservationService.visible_to(principal_user, school)


@pytest.mark.django_db
def test_the_observer_restores_their_own_draft(client, school, coordinator_user, teacher_user):
    """«الكل» لا تعني القيادة وحدها: من يملك حذف المسودة يملك إرجاعها."""
    obs = _make_obs(school, coordinator_user, teacher_user)
    ObservationService.archive(obs, coordinator_user)
    client.force_login(coordinator_user)

    resp = client.post(reverse("observation_restore", args=[obs.id]))

    assert resp.status_code == 302
    assert obs in ObservationService.visible_to(coordinator_user, school)


# ══════════════════════ الصفحة ══════════════════════════════════════


@pytest.mark.django_db
def test_the_archive_page_is_reachable_from_the_list(client, school, principal_user, teacher_user):
    """رابطٌ ظاهر — أرشيفٌ لا يُوصَل إليه كأنه غير موجود."""
    client.force_login(principal_user)

    html = client.get(reverse("observation_list")).content.decode()

    assert reverse("observation_archive") in html


@pytest.mark.django_db
def test_the_archive_page_renders_the_archived_rows(client, school, principal_user, teacher_user):
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)
    client.force_login(principal_user)

    html = client.get(reverse("observation_archive")).content.decode()

    assert teacher_user.full_name in html
    assert reverse("observation_restore", args=[obs.id]) in html
