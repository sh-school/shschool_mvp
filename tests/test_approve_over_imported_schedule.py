"""[SCHEDULE] حارسُ الاستبدال — لا يُعتمد توليدٌ فوق جدول aSc المستورَد إلّا بإقرارٍ صريح."""

import pytest
from django.urls import reverse

from core.models.audit import AuditLog
from operations.live_schedule_selectors import IMPORT_MODE
from operations.models import ScheduleGeneration
from operations.schedule_breaches import BreachesNotAcknowledgedError
from operations.services.schedule import ScheduleService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"
ACK = 'name="replace_imported"'


def _gen(school, status, *, imported):
    snapshot = {"mode": IMPORT_MODE} if imported else {}
    return ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status=status, config_snapshot=snapshot
    )


def _status(gen):
    gen.refresh_from_db()
    return gen.status


@pytest.mark.django_db
def test_generated_over_imported_without_ack_is_refused_and_live_unchanged(school):
    live = _gen(school, "approved", imported=True)
    draft = _gen(school, "draft", imported=False)

    with pytest.raises(BreachesNotAcknowledgedError, match="aSc"):
        ScheduleService.approve_generation(draft, notify=False)

    assert _status(draft) == "draft"
    assert _status(live) == "approved"


@pytest.mark.django_db
def test_generated_over_imported_with_ack_is_approved_and_audited(school):
    live = _gen(school, "approved", imported=True)
    draft = _gen(school, "draft", imported=False)

    ScheduleService.approve_generation(draft, notify=False, replace_imported=True)

    assert _status(draft) == "approved"
    assert _status(live) == "archived"
    entry = AuditLog.objects.get(object_id=str(draft.pk), school=school)
    assert entry.changes == {
        "replaced_generation": str(live.pk),
        "approved_generation": str(draft.pk),
    }


@pytest.mark.django_db
def test_imported_over_imported_needs_no_ack(school):
    _gen(school, "approved", imported=True)
    draft = _gen(school, "draft", imported=True)

    ScheduleService.approve_generation(draft, notify=False)

    assert _status(draft) == "approved"
    assert not AuditLog.objects.filter(school=school).exists()


@pytest.mark.django_db
def test_generated_over_generated_is_as_before(school):
    _gen(school, "approved", imported=False)
    draft = _gen(school, "draft", imported=False)

    ScheduleService.approve_generation(draft, notify=False)

    assert _status(draft) == "approved"
    assert not AuditLog.objects.filter(school=school).exists()


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def assignment(school):
    from operations.models import Subject, SubjectClassAssignment

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=6,
        is_active=True,
    )


def _page(client_as, principal):
    return client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()


@pytest.mark.django_db
def test_view_refuses_without_ack_then_approves_with_it(client_as, principal, school, assignment):
    live = _gen(school, "approved", imported=True)
    draft = _gen(school, "draft", imported=False)
    client = client_as(principal)
    url = reverse("approve_schedule", args=[draft.pk])

    client.post(url)
    assert _status(draft) == "draft" and _status(live) == "approved"

    client.post(url, {"replace_imported": "1"})
    assert _status(draft) == "approved"


@pytest.mark.django_db
def test_ack_box_only_for_non_imported_draft_over_imported_live(
    client_as, principal, school, assignment
):
    _gen(school, "approved", imported=True)
    _gen(school, "draft", imported=False)
    assert ACK in _page(client_as, principal)


@pytest.mark.django_db
def test_no_ack_box_for_imported_draft_over_imported_live(client_as, principal, school, assignment):
    _gen(school, "approved", imported=True)
    _gen(school, "draft", imported=True)
    assert ACK not in _page(client_as, principal)


@pytest.mark.django_db
def test_no_ack_box_when_live_is_generated(client_as, principal, school, assignment):
    _gen(school, "approved", imported=False)
    _gen(school, "draft", imported=False)
    assert ACK not in _page(client_as, principal)
