"""[QUALITY] الزيارةُ الصفّيّة تُؤرشف ولا تُحذف — من يؤرشف وبأيّ شرط (قرارُ المالك W-20261002-015).

المسودّة            ← الزائرُ صاحبُها وحدَه (لا المستخدمُ الفائق، لا قيادة، لا معلّم)
المرسَلة والمُقَرّة   ← القيادةُ والمدير بدورهما، بسببٍ إلزاميٍّ يُدقَّق (لا المستخدمُ الفائق بلا دور، ولا الزائر، ولا المعلّم)
المعلّمُ المُزار      ← لا يؤرشف شيئاً
الحذفُ النهائيّ      ← ممنوعٌ على الجميع حتى المطوّر: لا مسارَ في الواجهة ولا زرَّ في الإدارة
"""

import pathlib

import pytest
from django.urls import reverse

from quality.observation_models import ClassroomObservation
from quality.observation_views import _obs_perms
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_observation_crud import _make_obs

pytestmark = pytest.mark.django_db


def _user(school, role, *, superuser=False, name="مستخدم"):
    user = UserFactory(full_name=name, is_superuser=superuser, is_staff=superuser)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _actors(school, coordinator_user, principal_user, teacher_user):
    return {
        "observer": coordinator_user,
        "principal": principal_user,
        "vice_academic": _user(school, "vice_academic", name="النائب الأكاديمي"),
        "teacher": teacher_user,
        "superuser_no_role": _user(school, "it_technician", superuser=True, name="مطوّر"),
        "other_observer": _user(school, "academic_coordinator", name="زائرٌ آخر"),
    }


def _archived(obs):
    return ClassroomObservation.all_objects.get(pk=obs.pk).is_deleted


def _post(client_as, actor, obs, **data):
    return client_as(actor).post(reverse("observation_delete", args=[obs.id]), data)


# ── المسودّة: الزائرُ وحدَه ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "who", ["principal", "vice_academic", "teacher", "superuser_no_role", "other_observer"]
)
def test_nobody_but_the_observer_archives_a_draft(
    client_as, school, coordinator_user, principal_user, teacher_user, who
):
    actors = _actors(school, coordinator_user, principal_user, teacher_user)
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="draft")

    assert _obs_perms(actors[who], obs)["can_archive"] is False
    assert _post(client_as, actors[who], obs).status_code == 403
    assert not _archived(obs)


def test_the_observer_archives_his_own_draft_without_a_reason(
    client_as, school, coordinator_user, teacher_user
):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="draft")

    assert _obs_perms(coordinator_user, obs)["can_archive"] is True
    assert _post(client_as, coordinator_user, obs).status_code == 302
    assert _archived(obs)


# ── المرسَلة والمُقَرّة: القيادةُ والمدير بسببٍ ───────────────────────────
@pytest.mark.parametrize("status", ["submitted", "acknowledged"])
@pytest.mark.parametrize("who", ["principal", "vice_academic"])
def test_leadership_archives_a_sent_or_acknowledged_visit_only_with_a_reason(
    client_as, school, coordinator_user, principal_user, teacher_user, who, status
):
    actor = _actors(school, coordinator_user, principal_user, teacher_user)[who]
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status=status)

    assert _obs_perms(actor, obs)["can_archive"] is True
    _post(client_as, actor, obs, reason="   ")
    assert not _archived(obs), "السببُ إلزاميّ — الفراغُ لا يؤرشف"
    _post(client_as, actor, obs, reason="مكرّرة")
    assert _archived(obs)


@pytest.mark.parametrize("status", ["submitted", "acknowledged"])
@pytest.mark.parametrize("who", ["observer", "teacher", "superuser_no_role", "other_observer"])
def test_nobody_else_archives_a_sent_or_acknowledged_visit(
    client_as, school, coordinator_user, principal_user, teacher_user, who, status
):
    """حتى الزائرُ صاحبُها: ما أُرسل خرج من يده، والمعلّمُ المُزار لا يؤرشف شيئاً، والمطوّرُ بلا دورِ قيادةٍ مرفوض."""
    actors = _actors(school, coordinator_user, principal_user, teacher_user)
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status=status)

    assert _obs_perms(actors[who], obs)["can_archive"] is False
    assert _post(client_as, actors[who], obs, reason="سبب").status_code == 403
    assert not _archived(obs)


# ── الاستعادة لمن يملك الأرشفة ─────────────────────────────────────────
def test_only_those_who_may_archive_may_restore(
    client_as, school, coordinator_user, principal_user, teacher_user
):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="submitted")
    _post(client_as, principal_user, obs, reason="مكرّرة")
    assert _archived(obs)

    assert (
        client_as(teacher_user).post(reverse("observation_restore", args=[obs.id])).status_code
        == 403
    )
    assert _archived(obs)
    client_as(principal_user).post(reverse("observation_restore", args=[obs.id]))
    assert not _archived(obs)


# ── لا حذفَ نهائيّاً ────────────────────────────────────────────────────
def test_no_view_reaches_a_permanent_delete():
    source = pathlib.Path("quality/observation_views.py").read_text(encoding="utf-8")

    assert "hard_delete" not in source


def test_the_admin_offers_no_permanent_delete_even_to_the_developer(school):
    from django.contrib import admin
    from django.test import RequestFactory

    from quality.admin import ObservationScoreInline
    from quality.observation_models import ObservationScore

    request = RequestFactory().get("/admin/")
    request.user = _user(school, "it_technician", superuser=True, name="مطوّر")

    assert admin.site._registry[ClassroomObservation].has_delete_permission(request) is False
    assert admin.site._registry[ObservationScore].has_delete_permission(request) is False
    assert ObservationScoreInline.can_delete is False


def test_the_screens_say_archive_not_delete(client_as, school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="draft")

    html = (
        client_as(coordinator_user)
        .get(reverse("observation_detail", args=[obs.id]))
        .content.decode()
    )

    assert "أرشفة" in html
    assert ">حذف<" not in html
