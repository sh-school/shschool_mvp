"""W-20261128-004: تنبيهُ مشرف الجناح عند مغادرة العيادة ثمّ معلّمِ الحصّة الجارية بعد 5 دقائق."""

import datetime as dt

import pytest
from django.utils import timezone

from clinic import choices
from clinic.exit_services import depart_on_close
from clinic.services import ClinicService
from notifications.hub import NotificationHub
from operations import exit_card
from operations.exit_card_beat import exit_card_beat
from operations.models import ClassExit, Session
from operations.tasks import alert_clinic_returns_task
from tests.test_movement_live import _exit, wing_a  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

REASON = "سببٌ-صحّيٌّ-سرّيّ"


@pytest.fixture
def sent(monkeypatch):
    """إشعاراتُ المتابعة وحدَها؛ ما ترسله الزيارةُ نفسُها خارجُ هذا الاختبار."""
    calls: list[dict] = []

    def record(*args, **kwargs):
        if kwargs.get("title") == "طالبٌ بانتظار تأكيد وصوله":
            calls.append(kwargs)
        return {"in_app": 0, "queued": {}, "failed": 0}

    monkeypatch.setattr(NotificationHub, "dispatch", staticmethod(record))
    return calls


def _current_session(school, klass, teacher):
    """حصّةٌ تغطّي اليومَ كلَّه فهي «الجارية» مهما كانت ساعةُ التثبيت."""
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=timezone.localdate(),
        start_time=dt.time(0, 0),
        end_time=dt.time(23, 59),
        status="scheduled",
    )


def _departed(school, klass, teacher, nurse, nid, outcome=choices.OUTCOME_RETURN):
    row = _exit(school, klass, teacher, "طالب العيادة", nid, minutes_ago=20)
    ClassExit.objects.filter(pk=row.pk).update(clinic_arrived_at=row.left_at)
    visit = ClinicService.start_visit(school, row.student, nurse)
    visit.reason = REASON
    visit.save(update_fields=["reason"])
    ClinicService.close_visit(visit, outcome, "")
    assert depart_on_close(school, row.student_id, timezone.localdate(), nurse)
    row.refresh_from_db()
    return row


def _after(row, minutes):
    return row.clinic_left_at + dt.timedelta(minutes=minutes)


def test_departure_alerts_supervisor_immediately_after_commit(
    school, nurse_user, teacher_user, wing_a, sent, django_capture_on_commit_callbacks
):
    klass, supervisor = wing_a

    with django_capture_on_commit_callbacks(execute=True):
        _departed(school, klass, teacher_user, nurse_user, "29000000003")

    assert [c["recipients"] for c in sent] == [[supervisor]]


def test_teacher_alerted_after_five_minutes_each_stage_once(
    school, nurse_user, teacher_user, wing_a, sent
):
    klass, supervisor = wing_a
    row = _departed(school, klass, teacher_user, nurse_user, "29000000004")
    _current_session(school, klass, teacher_user)

    assert exit_card.alert_clinic_returns(school, _after(row, 4)) == 1
    assert exit_card.alert_clinic_returns(school, _after(row, 4)) == 0
    assert exit_card.alert_clinic_returns(school, _after(row, 5)) == 1
    assert exit_card.alert_clinic_returns(school, _after(row, 9)) == 0

    assert [c["recipients"] for c in sent] == [[supervisor], [teacher_user]]
    for call in sent:
        assert REASON not in call["title"] + call["body"] + call["external_body"]
        outside = call["title"] + call["external_body"]
        assert row.student.full_name not in outside and "العيادة" not in outside
    row.refresh_from_db()
    assert row.clinic_alert_stage == 2 and row.alert_stage == 0


def test_no_alert_for_leave_or_confirmed_or_not_departed(
    school, nurse_user, teacher_user, wing_a, sent
):
    klass, _ = wing_a
    _current_session(school, klass, teacher_user)
    gone = _departed(school, klass, teacher_user, nurse_user, "29000000005", choices.OUTCOME_LEAVE)
    back = _departed(school, klass, teacher_user, nurse_user, "29000000006")
    exit_card.return_exit(back.pk, None)
    _exit(school, klass, teacher_user, "طالب منتظر", "29000000007")

    assert exit_card.alert_clinic_returns(school, _after(gone, 10)) == 0
    assert sent == []


def test_confirmation_after_first_stage_stops_the_second(
    school, nurse_user, teacher_user, wing_a, sent
):
    klass, _ = wing_a
    row = _departed(school, klass, teacher_user, nurse_user, "29000000008")
    _current_session(school, klass, teacher_user)
    exit_card.alert_clinic_returns(school, _after(row, 0))
    exit_card.return_exit(row.pk, None)

    assert exit_card.alert_clinic_returns(school, _after(row, 10)) == 0
    assert len(sent) == 1


def test_bell_continuation_does_not_repeat_stages(school, nurse_user, teacher_user, wing_a, sent):
    klass, _ = wing_a
    row = _departed(school, klass, teacher_user, nurse_user, "29000000009")
    session = _current_session(school, klass, teacher_user)
    assert exit_card.alert_clinic_returns(school, _after(row, 5)) == 2
    ClassExit.objects.filter(pk=row.pk).update(returned_at=timezone.now())
    ClassExit.objects.create(
        school=school,
        session=session,
        student=row.student,
        destination="clinic",
        left_at=timezone.now(),
        allowed_by=teacher_user,
        continued_from=row,
    )

    assert exit_card.alert_clinic_returns(school, _after(row, 8)) == 0
    assert len(sent) == 2


def test_no_recipient_does_not_block_and_waits_for_a_session(
    school, nurse_user, teacher_user, wing_a, sent
):
    klass, _ = wing_a
    row = _departed(school, klass, teacher_user, nurse_user, "29000000003")
    Session.objects.filter(school=school).update(start_time=dt.time(0, 1), end_time=dt.time(0, 2))
    klass.wing = None
    klass.save(update_fields=["wing"])

    assert exit_card.alert_clinic_returns(school, _after(row, 6)) == 0
    _current_session(school, klass, teacher_user)
    assert exit_card.alert_clinic_returns(school, _after(row, 7)) == 1
    assert [c["recipients"] for c in sent] == [[teacher_user]]


def test_task_isolates_a_failing_school_and_is_scheduled(school, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("x")

    monkeypatch.setattr(exit_card, "alert_clinic_returns", boom)

    assert alert_clinic_returns_task()["failed_schools"] >= 1
    entry = exit_card_beat({"EXIT_CARD_BEAT": "1"})["alert-clinic-returns"]
    assert entry["task"] == "operations.alert_clinic_returns"
    assert exit_card_beat({}) == {}
