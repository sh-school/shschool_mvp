"""
tests/test_observation_crud.py
اختبارات CRUD + سير الحالة + الحذف الناعم للزيارات الصفية (الإشراف على أداء المعلّم).
"""

import pytest
from django.urls import reverse

from quality.observation_models import ClassroomObservation, ObservationCriterion
from quality.observation_services import ObservationService


# ── مساعدات ──────────────────────────────────────────────────────────
def _criteria(school, n=3):
    out = []
    for i in range(1, n + 1):
        c, _ = ObservationCriterion.objects.get_or_create(
            school=school, domain="planning", text=f"معيار {i}", defaults={"order": i}
        )
        out.append(c)
    return out


def _make_obs(school, observer, teacher, status="draft", rate="complete"):
    obs = ClassroomObservation.objects.create(
        school=school, teacher=teacher, observer=observer, created_by=observer, status=status
    )
    crits = _criteria(school)
    ObservationService.save_scores(obs, {str(c.id): rate for c in crits}, {})
    obs.refresh_from_db()
    return obs, crits


# ══════════════════════ خدمة: تعديل ═══════════════════════════════════
@pytest.mark.django_db
def test_update_draft_persists_and_recomputes(school, coordinator_user, teacher_user):
    obs, crits = _make_obs(school, coordinator_user, teacher_user, rate="complete")
    assert obs.score_percent == 100
    ObservationService.update_observation(
        obs,
        header={"topic": "الكسور"},
        ratings={str(crits[0].id): "limited", str(crits[1].id): "complete", str(crits[2].id): "complete"},
        recommendations={str(crits[0].id): "يحتاج تطوير"},
        by_user=coordinator_user,
    )
    obs.refresh_from_db()
    assert obs.topic == "الكسور"
    # (25 + 100 + 100) / 3 = 75
    assert obs.score_percent == 75
    assert obs.scores.get(criterion=crits[0]).recommendation == "يحتاج تطوير"


@pytest.mark.django_db
def test_update_acknowledged_blocked(school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="acknowledged")
    with pytest.raises(ValueError):
        ObservationService.update_observation(
            obs, header={"topic": "x"}, ratings={}, recommendations={}, by_user=coordinator_user
        )


# ══════════════════════ خدمة: سير الحالة ══════════════════════════════
@pytest.mark.django_db
def test_submit_only_from_draft_increments_count(school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user)
    ObservationService.submit(obs, coordinator_user)
    obs.refresh_from_db()
    assert obs.status == "submitted"
    assert obs.submission_count == 1
    # إعادة استدعاء submit على مُرسَلة = لا شيء
    ObservationService.submit(obs, coordinator_user)
    obs.refresh_from_db()
    assert obs.submission_count == 1


@pytest.mark.django_db
def test_withdraw_submitted_to_draft(school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="submitted")
    ObservationService.withdraw(obs, coordinator_user)
    obs.refresh_from_db()
    assert obs.status == "draft"
    assert obs.submitted_at is None


@pytest.mark.django_db
def test_reopen_acknowledged_clears_ack(school, principal_user, teacher_user):
    obs, _ = _make_obs(school, principal_user, teacher_user, status="acknowledged")
    obs.teacher_acknowledged_at = obs.created_at
    obs.teacher_comment = "شكراً"
    obs.save()
    ObservationService.reopen(obs, principal_user, reason="تصحيح درجة")
    obs.refresh_from_db()
    assert obs.status == "submitted"
    assert obs.teacher_acknowledged_at is None
    assert obs.teacher_comment == ""


# ══════════════════════ خدمة: حذف ناعم ════════════════════════════════
@pytest.mark.django_db
def test_archive_soft_deletes_and_preserves_scores(school, principal_user, teacher_user):
    obs, crits = _make_obs(school, principal_user, teacher_user, status="submitted")
    obs_id = obs.id
    ObservationService.archive(obs, principal_user, reason="مكرّرة")
    # مخفيّة عن المدير الافتراضي، حاضرة في all_objects، وتقييماتها محفوظة
    assert not ClassroomObservation.objects.filter(id=obs_id).exists()
    archived = ClassroomObservation.all_objects.get(id=obs_id)
    assert archived.is_deleted is True
    assert archived.deleted_at is not None
    assert archived.scores.count() == len(crits)


@pytest.mark.django_db
def test_restore_returns_obs(school, principal_user, teacher_user):
    obs, _ = _make_obs(school, principal_user, teacher_user)
    obs_id = obs.id
    ObservationService.archive(obs, principal_user)
    restored = ClassroomObservation.all_objects.get(id=obs_id)
    ObservationService.restore(restored, principal_user)
    assert ClassroomObservation.objects.filter(id=obs_id).exists()


@pytest.mark.django_db
def test_visible_to_excludes_deleted(school, principal_user, teacher_user):
    obs, _ = _make_obs(school, principal_user, teacher_user)
    assert ObservationService.visible_to(principal_user, school).filter(id=obs.id).exists()
    ObservationService.archive(obs, principal_user)
    assert not ObservationService.visible_to(principal_user, school).filter(id=obs.id).exists()


# ══════════════════════ صلاحيات (تكامل عبر الـviews) ══════════════════
@pytest.mark.django_db
def test_edit_by_non_author_leadership_denied(client_as, school, coordinator_user, principal_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user)  # الزائر = المنسّق
    c = client_as(principal_user)  # قيادة لكنه ليس الزائر
    r = c.get(reverse("observation_edit", args=[obs.id]))
    assert r.status_code == 403


@pytest.mark.django_db
def test_edit_by_teacher_denied(client_as, school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user)
    c = client_as(teacher_user)
    r = c.get(reverse("observation_edit", args=[obs.id]))
    assert r.status_code == 403


@pytest.mark.django_db
def test_delete_draft_by_observer_ok(client_as, school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user)
    c = client_as(coordinator_user)
    r = c.post(reverse("observation_delete", args=[obs.id]))
    assert r.status_code == 302
    assert not ClassroomObservation.objects.filter(id=obs.id).exists()
    assert ClassroomObservation.all_objects.filter(id=obs.id, is_deleted=True).exists()


@pytest.mark.django_db
def test_delete_submitted_by_observer_denied(client_as, school, coordinator_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="submitted")
    c = client_as(coordinator_user)  # المنسّق ليس قيادة
    r = c.post(reverse("observation_delete", args=[obs.id]), {"reason": "x"})
    assert r.status_code == 403
    assert ClassroomObservation.objects.filter(id=obs.id).exists()


@pytest.mark.django_db
def test_delete_submitted_by_leadership_requires_reason(client_as, school, principal_user, teacher_user):
    obs, _ = _make_obs(school, principal_user, teacher_user, status="submitted")
    c = client_as(principal_user)
    # بلا سبب → يُرفض ويبقى
    c.post(reverse("observation_delete", args=[obs.id]), {"reason": ""})
    assert ClassroomObservation.objects.filter(id=obs.id).exists()
    # بسبب → يُؤرشَف
    c.post(reverse("observation_delete", args=[obs.id]), {"reason": "مكرّرة"})
    assert not ClassroomObservation.objects.filter(id=obs.id).exists()


@pytest.mark.django_db
def test_reopen_leadership_only(client_as, school, coordinator_user, principal_user, teacher_user):
    obs, _ = _make_obs(school, coordinator_user, teacher_user, status="acknowledged")
    # المنسّق (الزائر، ليس قيادة) → ممنوع
    assert client_as(coordinator_user).post(reverse("observation_reopen", args=[obs.id])).status_code == 403
    # المدير (قيادة) → يُعيد الفتح
    client_as(principal_user).post(reverse("observation_reopen", args=[obs.id]), {"reason": "تصحيح"})
    obs.refresh_from_db()
    assert obs.status == "submitted"


@pytest.mark.django_db
def test_list_filter_by_status(client_as, school, coordinator_user, teacher_user):
    _make_obs(school, coordinator_user, teacher_user, status="draft")
    _make_obs(school, coordinator_user, teacher_user, status="submitted")
    c = client_as(coordinator_user)
    r = c.get(reverse("observation_list"), {"status": "submitted"})
    assert r.status_code == 200
    assert len(r.context["rows"]) == 1
    assert r.context["rows"][0][0].status == "submitted"
