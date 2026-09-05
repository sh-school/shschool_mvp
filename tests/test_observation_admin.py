"""[QUALITY] الملاحظة الصفّية في لوحة الإدارة — الوحدةُ كانت منشورةً وغيرَ مسجَّلة.

الجداولُ الثلاثة موجودةٌ منذ إصداراتٍ وتعمل على الإنتاج، لكنّ `quality/admin.py`
لم يسجّل منها شيئاً. فلا سبيلَ لقيادة المدرسة أن تفتّش زيارةً، أو تُصلح معياراً
مزروعاً خطأً، أو ترى المؤرشَف — كلُّ شيءٍ يمرّ بالواجهة وحدَها.

وثلاثةُ قيودٍ يحرسها هذا الملفّ لأنّ التسجيل الساذج يكسرها:
    ١ المديرُ الافتراضيّ يستبعد المحذوفَ ناعماً — فيختفي الأرشيف من اللوحة أيضاً.
    ٢ حذفُ Django الجماعيّ يستدعي `queryset.delete()` بلا ختمِ `updated_by`.
    ٣ `score_percent` مشتقٌّ من التقييمات — تعديلُ تقييمٍ من اللوحة يُبقيه قديماً.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import site
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from quality.admin import (
    ClassroomObservationAdmin,
    ObservationScoreAdmin,
)
from quality.observation_models import (
    ClassroomObservation,
    ObservationCriterion,
    ObservationScore,
)
from quality.observation_services import ObservationService


def _make_obs(school, observer, teacher, rating="complete"):
    obs = ClassroomObservation.objects.create(
        school=school, teacher=teacher, observer=observer, created_by=observer
    )
    crit, _ = ObservationCriterion.objects.get_or_create(
        school=school, domain="planning", text="معيار", defaults={"order": 1}
    )
    ObservationService.save_scores(obs, {str(crit.id): rating}, {})
    obs.refresh_from_db()
    return obs


def _request(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


# ══════════════════════ التسجيل ═══════════════════════════════════


@pytest.mark.parametrize("model", [ObservationCriterion, ClassroomObservation, ObservationScore])
def test_the_observation_models_reach_the_admin(model):
    assert model in site._registry, f"{model.__name__} غير مسجَّل في لوحة الإدارة"


# ══════════════════════ ١ المؤرشَف يُرى ══════════════════════════════


@pytest.mark.django_db
def test_the_admin_list_shows_what_the_default_manager_hides(school, principal_user, teacher_user):
    """المديرُ الافتراضيّ يستبعد المحذوفَ ناعماً؛ لوحةُ الإدارة تُبنى من `all_objects`."""
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)

    listed = ClassroomObservationAdmin(ClassroomObservation, site).get_queryset(
        _request(principal_user)
    )

    assert obs in listed
    assert obs not in ClassroomObservation.objects.all()


# ══════════════════════ ٢ لا حذفَ من اللوحة ══════════════════════════


@pytest.mark.django_db
def test_the_admin_refuses_to_delete_an_observation(school, principal_user, teacher_user):
    """الحذفُ الجماعيّ يستدعي `queryset.delete()` بلا ختمٍ — فالزرّ مُغلق."""
    model_admin = ClassroomObservationAdmin(ClassroomObservation, site)
    request = _request(principal_user)
    obs = _make_obs(school, principal_user, teacher_user)

    assert model_admin.has_delete_permission(request) is False
    assert model_admin.has_delete_permission(request, obs) is False
    assert "delete_selected" not in model_admin.get_actions(request)


@pytest.mark.django_db
def test_archiving_from_the_admin_keeps_the_scores_and_stamps_who(
    school, principal_user, teacher_user
):
    model_admin = ClassroomObservationAdmin(ClassroomObservation, site)
    obs = _make_obs(school, principal_user, teacher_user)

    model_admin.archive_selected(
        _request(principal_user), ClassroomObservation.all_objects.filter(id=obs.id)
    )

    obs.refresh_from_db()
    assert obs.is_deleted is True
    assert obs.deleted_at is not None
    assert obs.updated_by == principal_user
    assert obs.scores.count() == 1


@pytest.mark.django_db
def test_restoring_from_the_admin_returns_the_observation_to_the_live_list(
    school, principal_user, teacher_user
):
    model_admin = ClassroomObservationAdmin(ClassroomObservation, site)
    obs = _make_obs(school, principal_user, teacher_user)
    ObservationService.archive(obs, principal_user)

    model_admin.restore_selected(
        _request(principal_user), ClassroomObservation.all_objects.filter(id=obs.id)
    )

    obs.refresh_from_db()
    assert obs.is_deleted is False
    assert obs in ClassroomObservation.objects.all()


# ══════════════════════ ٣ النسبة تبقى مشتقّة ════════════════════════


@pytest.mark.django_db
def test_the_percentage_is_read_only_in_the_admin():
    model_admin = ClassroomObservationAdmin(ClassroomObservation, site)

    assert "score_percent" in model_admin.readonly_fields
    for state_field in ("submitted_at", "teacher_acknowledged_at", "submission_count"):
        assert state_field in model_admin.readonly_fields


@pytest.mark.django_db
def test_editing_a_score_from_the_admin_recomputes_the_percentage(
    school, principal_user, teacher_user
):
    """وإلّا قالت الترويسةُ 100% وتقييمُها الوحيد «محدود»."""
    obs = _make_obs(school, principal_user, teacher_user, rating="complete")
    assert obs.score_percent == Decimal("100.00")

    score = obs.scores.get()
    score.rating = "limited"
    ObservationScoreAdmin(ObservationScore, site).save_model(
        _request(principal_user), score, None, True
    )

    obs.refresh_from_db()
    assert obs.score_percent == Decimal("25.00")


@pytest.mark.django_db
def test_deleting_a_score_from_the_admin_recomputes_the_percentage(
    school, principal_user, teacher_user
):
    obs = _make_obs(school, principal_user, teacher_user, rating="complete")
    score = obs.scores.get()

    ObservationScoreAdmin(ObservationScore, site).delete_queryset(
        _request(principal_user), ObservationScore.objects.filter(id=score.id)
    )

    obs.refresh_from_db()
    assert obs.score_percent is None


@pytest.mark.django_db
def test_saving_inline_scores_recomputes_the_percentage(school, principal_user, teacher_user):
    """مسارُ التحرير في صفحة الزيارة: التقييماتُ inline ثمّ `save_related`."""
    obs = _make_obs(school, principal_user, teacher_user, rating="complete")
    obs.scores.update(rating="some")

    ClassroomObservationAdmin(ClassroomObservation, site).save_related(
        _request(principal_user),
        SimpleNamespace(instance=obs, save_m2m=lambda: None),
        [],
        True,
    )

    obs.refresh_from_db()
    assert obs.score_percent == Decimal("50.00")
