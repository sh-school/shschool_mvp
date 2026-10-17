"""سلسلةُ نموذج 07 للانتقال الوارد والصادر: تدقيقٌ ← اعتمادٌ ← تشعيبٌ ← إدخال (W-20261001-018)."""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import AuditLog, Membership, StudentEnrollment
from student_affairs.models import StudentTransfer
from student_affairs.transfer_chain import apply_chain_action, available_actions
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.transfer_chain_support import ALL_DOCS, advance, run_full_chain

pytestmark = pytest.mark.django_db

ALL_ACTIONS = ("review", "approved", "rejected", "place", "enter", "completed", "cancelled")


@pytest.fixture
def make(school, kid, student_affairs_coordinator_user):
    def _make(direction="out"):
        return StudentTransfer.objects.create(
            school=school,
            student=kid,
            direction=direction,
            other_school_name="مدرسة أخرى",
            transfer_date=dt.date(2026, 10, 8),
            academic_year="2026-2027",
            created_by=student_affairs_coordinator_user,
            updated_by=student_affairs_coordinator_user,
        )

    return _make


def _act(transfer, action, user, notes="", documents=ALL_DOCS, missing=""):
    return apply_chain_action(
        transfer, action, notes, user, documents=documents, missing_reason=missing
    )


@pytest.mark.parametrize("direction", ["in", "out"])
def test_the_full_chain_records_each_stage_with_actor_and_time(
    make, student_affairs_coordinator_user, direction
):
    transfer = run_full_chain(make(direction), student_affairs_coordinator_user)

    transfer.refresh_from_db()
    assert transfer.status == "completed"
    for stage in ("reviewed", "approved", "placed", "entered"):
        assert getattr(transfer, f"{stage}_by") == student_affairs_coordinator_user
        assert getattr(transfer, f"{stage}_at") is not None
    assert transfer.documents_checked == sorted(ALL_DOCS, key=int)


@pytest.mark.parametrize("action", ["approved", "rejected", "place", "enter", "completed"])
def test_nothing_goes_ahead_of_the_review(make, student_affairs_coordinator_user, action):
    transfer = make()

    with pytest.raises(ValueError):
        _act(transfer, action, student_affairs_coordinator_user, notes="سبب")

    transfer.refresh_from_db()
    assert transfer.status == "pending" and transfer.reviewed_at is None


def test_review_needs_all_eleven_documents_or_a_recorded_reason(
    make, student_affairs_coordinator_user
):
    transfer = make()

    with pytest.raises(ValueError):
        _act(transfer, "review", student_affairs_coordinator_user, documents=ALL_DOCS[:10])
    transfer.refresh_from_db()
    assert transfer.reviewed_at is None

    _act(
        transfer,
        "review",
        student_affairs_coordinator_user,
        documents=ALL_DOCS[:10],
        missing="شهادة النجاح قيد الإصدار",
    )
    assert transfer.documents_missing_reason == "شهادة النجاح قيد الإصدار"
    assert len(transfer.documents_checked) == 10


def test_review_rejects_an_unknown_document(make, student_affairs_coordinator_user):
    with pytest.raises(ValueError):
        _act(make(), "review", student_affairs_coordinator_user, documents=["99"])


def test_rejection_needs_a_reason_after_review(make, student_affairs_coordinator_user):
    transfer = make()
    advance(transfer, student_affairs_coordinator_user, "review")

    with pytest.raises(ValueError):
        _act(transfer, "rejected", student_affairs_coordinator_user, notes="")
    _act(transfer, "rejected", student_affairs_coordinator_user, notes="مستندات غير صحيحة")
    assert transfer.status == "rejected"


def test_place_and_enter_keep_their_order(make, student_affairs_coordinator_user):
    transfer = make()
    advance(transfer, student_affairs_coordinator_user, "approved")

    with pytest.raises(ValueError):
        _act(transfer, "enter", student_affairs_coordinator_user)
    with pytest.raises(ValueError):
        _act(transfer, "completed", student_affairs_coordinator_user)
    _act(transfer, "place", student_affairs_coordinator_user)
    with pytest.raises(ValueError):
        _act(transfer, "completed", student_affairs_coordinator_user)
    with pytest.raises(ValueError):
        _act(transfer, "place", student_affairs_coordinator_user)
    _act(transfer, "enter", student_affairs_coordinator_user)
    _act(transfer, "completed", student_affairs_coordinator_user)
    assert transfer.status == "completed"


@pytest.mark.parametrize("until", [None, "review", "approved"])
def test_cancel_is_allowed_before_completion(make, student_affairs_coordinator_user, until):
    transfer = make()
    if until:
        advance(transfer, student_affairs_coordinator_user, until)

    _act(transfer, "cancelled", student_affairs_coordinator_user)

    assert transfer.status == "cancelled"


@pytest.mark.parametrize("final", ["rejected", "completed", "cancelled"])
def test_a_finished_request_accepts_nothing(make, student_affairs_coordinator_user, final):
    transfer = make()
    if final == "completed":
        run_full_chain(transfer, student_affairs_coordinator_user)
    else:
        advance(transfer, student_affairs_coordinator_user, "review")
        _act(transfer, final, student_affairs_coordinator_user, notes="سبب")

    for action in ALL_ACTIONS:
        with pytest.raises(ValueError):
            _act(transfer, action, student_affairs_coordinator_user, notes="سبب")
    assert available_actions(transfer) == []


def test_the_internal_direction_is_not_touched_by_the_chain(make, student_affairs_coordinator_user):
    with pytest.raises(ValueError):
        _act(make("internal"), "review", student_affairs_coordinator_user)


def _student_active(school, kid):
    return Membership.objects.filter(
        user=kid, school=school, role__name="student", is_active=True
    ).exists()


def test_the_outgoing_student_stays_active_until_the_chain_is_complete(
    make, school, kid, klass, student_affairs_coordinator_user
):
    transfer = make("out")
    advance(transfer, student_affairs_coordinator_user, "enter")

    assert _student_active(school, kid)
    assert StudentEnrollment.objects.get(student=kid, class_group=klass).is_active

    _act(transfer, "completed", student_affairs_coordinator_user)

    assert not _student_active(school, kid)
    assert not StudentEnrollment.objects.get(student=kid, class_group=klass).is_active


def test_an_incoming_completion_does_not_deactivate_anyone(
    make, kid, klass, student_affairs_coordinator_user
):
    run_full_chain(make("in"), student_affairs_coordinator_user)

    assert StudentEnrollment.objects.get(student=kid, class_group=klass).is_active


def test_the_view_walks_the_chain_and_audits_without_personal_data(
    client, make, kid, student_affairs_coordinator_user
):
    transfer = make("out")
    client.force_login(student_affairs_coordinator_user)
    url = reverse("student_affairs:transfer_review", args=[transfer.pk])

    client.post(url, {"action": "completed"})
    transfer.refresh_from_db()
    assert transfer.status == "pending"

    client.post(url, {"action": "review", "documents": ALL_DOCS})
    for action in ("approved", "place", "enter", "completed"):
        client.post(url, {"action": action})

    transfer.refresh_from_db()
    assert transfer.status == "completed"
    detail = client.get(reverse("student_affairs:transfer_detail", args=[transfer.pk]))
    assert detail.status_code == 200
    rows = AuditLog.objects.filter(changes__event__startswith="transfer_")
    log = " ".join(f"{r.changes} {r.object_repr}" for r in rows)
    assert "transfer_review" in log and "transfer_completed" in log
    assert kid.national_id not in log and kid.full_name not in log


def test_the_detail_page_lists_documents_stages_and_blocks_early_completion(
    client, make, student_affairs_coordinator_user
):
    transfer = make("in")
    client.force_login(student_affairs_coordinator_user)

    page = client.get(
        reverse("student_affairs:transfer_detail", args=[transfer.pk])
    ).content.decode()

    assert "البطاقة الشخصية" in page and "شهادة نجاح نهاية العام الدراسي" in page
    assert "التشعيب" in page and "تدقيق المستندات" in page
    assert 'value="completed"' not in page, "لا إتمامَ قبل شرطه"
