"""[LEGAL] تجميدُ التواصل مع أولياء الأمور — كلُّ نقطة إرسالٍ تحترم المفتاح بلا فقد حالة (W-20261008-013، D-268م وD-272م).

قرارُ المالك «تجميد وإخفاء، لا حذف»: لا يخرج شيءٌ لوليّ أمر (منصّة ولا بريد ولا رسالة ولا دفع)، ولا تُكتب علامةُ «أُبلِغ»
لما لم يُرسَل، ولا يُحذف سجلّ. والتجميدُ يتقدّم على الأحداث «الإلزاميّة» (غياب، استدعاء، إرسال للمنزل).
S1 + S2 فقط: إغلاقُ البوابة وإخفاءُ الشاشات لاحقان (S3 فما بعد).
"""

import datetime as dt

import pytest
from django.core import mail
from django.test import RequestFactory
from django.urls import reverse

from core.parents_freeze import is_parent_only, parents_frozen, without_frozen_parents
from notifications.hub import NotificationHub
from notifications.models import InAppNotification
from tests.conftest import MembershipFactory, RoleFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def frozen(settings):
    settings.PARENTS_FROZEN = True


@pytest.fixture
def parent_with_email(parent_user):
    parent_user.email = "parent@example.test"
    parent_user.save(update_fields=["email"])
    return parent_user


def _alert(school, student, status="pending"):
    from operations.models import AbsenceAlert

    today = dt.date.today()
    return AbsenceAlert.objects.create(
        school=school,
        student=student,
        absence_count=5,
        gate="g1",
        period_start=today,
        period_end=today,
        status=status,
    )


# ── المفتاح ───────────────────────────────────────────────


def test_the_key_is_frozen_when_the_setting_is_absent(settings):
    del settings.PARENTS_FROZEN
    assert parents_frozen() is True


def test_testing_settings_keep_the_key_off_by_default():
    assert parents_frozen() is False


def test_the_context_processor_exposes_the_key(frozen, principal_user):
    from core.context_processors import school_context

    request = RequestFactory().get("/")
    request.user = principal_user
    assert school_context(request)["parents_frozen"] is True


def test_a_teacher_who_is_also_a_parent_is_not_parent_only(school, teacher_user, parent_user):
    role = RoleFactory(school=school, name="parent")
    MembershipFactory(user=teacher_user, school=school, role=role)
    assert not is_parent_only(teacher_user)
    assert is_parent_only(parent_user)


def test_without_frozen_parents_drops_only_parents_and_only_when_frozen(
    settings, parent_user, teacher_user
):
    settings.PARENTS_FROZEN = True
    assert without_frozen_parents([parent_user, teacher_user]) == [teacher_user]
    settings.PARENTS_FROZEN = False
    assert without_frozen_parents([parent_user, teacher_user]) == [parent_user, teacher_user]


# ── الـHub ────────────────────────────────────────────────


def test_dispatch_skips_parents_but_still_reaches_staff(frozen, school, parent_user, teacher_user):
    result = NotificationHub.dispatch(
        event_type="behavior_l2",
        school=school,
        recipients=[parent_user, teacher_user],
        title="t",
        body="b",
    )
    assert result["in_app"] == 1
    assert not InAppNotification.objects.filter(user=parent_user).exists()
    assert InAppNotification.objects.filter(user=teacher_user).exists()


@pytest.mark.parametrize("event", ["absence", "parent_summon", "sent_home", "behavior_l3", "fail"])
def test_dispatch_to_parents_writes_nothing_even_for_mandatory_events(
    frozen, school, parent_user, student_user, event
):
    result = NotificationHub.dispatch_to_parents(
        event_type=event, school=school, student=student_user, title="t", body="b"
    )
    assert result["frozen"] is True
    assert result["in_app"] == 0
    assert not InAppNotification.objects.filter(user=parent_user).exists()


def test_dispatch_to_parents_delivers_again_after_the_thaw(
    settings, school, parent_user, student_user
):
    settings.PARENTS_FROZEN = False
    result = NotificationHub.dispatch_to_parents(
        event_type="absence", school=school, student=student_user, title="t", body="b"
    )
    assert result["in_app"] == 1
    assert InAppNotification.objects.filter(user=parent_user).exists()


# ── الغياب والرسوب ────────────────────────────────────────


def test_notify_absence_sends_nothing_and_leaves_the_alert_status(
    frozen, school, parent_with_email, student_user
):
    from notifications.services import NotificationService

    alert = _alert(school, student_user)
    assert NotificationService.notify_absence(alert) == []
    alert.refresh_from_db()
    assert alert.status == "pending"
    assert mail.outbox == []


def test_the_bulk_pending_sender_leaves_pending_alerts_pending(
    frozen, school, parent_with_email, student_user
):
    from notifications.services import NotificationService

    alert = _alert(school, student_user)
    counts = NotificationService.send_pending_absence_alerts(school)
    assert tuple(counts) == (0, 0)
    assert counts.deferred == 0
    alert.refresh_from_db()
    assert alert.status == "pending"
    assert mail.outbox == []


def test_notify_fail_sends_nothing(frozen, school, parent_with_email, student_user):
    from notifications.services import NotificationService

    assert NotificationService.notify_fail(student_user, school, ["math"]) == []
    assert mail.outbox == []


# ── البريد والرسائل المباشرة ──────────────────────────────


def test_deliver_email_and_sms_refuse_a_parent_recipient(
    frozen, school, parent_with_email, student_user
):
    from core.parents_freeze import FROZEN_MESSAGE
    from notifications.services import NotificationService

    email = NotificationService.deliver_email(
        user=parent_with_email, school=school, subject="s", body_text="b", student=student_user
    )
    sms = NotificationService.deliver_sms(
        user=parent_with_email, school=school, phone_number="55555555", message="m"
    )
    assert (email.ok, email.error) == (False, FROZEN_MESSAGE)
    assert (sms.ok, sms.error) == (False, FROZEN_MESSAGE)
    assert mail.outbox == []


def test_deliver_email_still_reaches_staff(frozen, school, teacher_user):
    from notifications.services import NotificationService

    teacher_user.email = "teacher@example.test"
    teacher_user.save(update_fields=["email"])
    outcome = NotificationService.deliver_email(
        user=teacher_user, school=school, subject="s", body_text="b"
    )
    assert outcome.ok


def test_the_clinic_sent_home_mail_is_skipped(
    frozen, school, parent_with_email, student_user, clinic_visit, nurse_user
):
    from clinic.services import ClinicService

    assert ClinicService._notify_parents_sent_home(clinic_visit, school, nurse_user) is False
    assert mail.outbox == []


def test_the_behavior_report_mail_is_skipped(
    frozen, client, school, principal_user, parent_with_email, student_user
):
    client.force_login(principal_user)
    client.post(reverse("behavior:behavior_report", args=[student_user.pk]), {"action": "send"})
    assert mail.outbox == []


def test_resend_is_refused_for_a_student_notification(
    frozen, client, school, principal_user, student_user
):
    from notifications.models import NotificationLog

    log = NotificationLog.objects.create(
        school=school,
        student=student_user,
        channel="email",
        recipient="parent@example.test",
        subject="s",
        body="b",
        status="failed",
        notif_type="absence_alert",
    )
    client.force_login(principal_user)
    client.post(reverse("resend_notification", args=[log.pk]))
    assert mail.outbox == []


# ── الإخطار بعد العتبة (#887) ──────────────────────────────


def test_issuing_the_threshold_notice_is_refused_and_the_alert_stays_held(
    frozen, monkeypatch, school, principal_user, parent_user, student_user
):
    from wings.absence_notice_services import IssueRefused, issue

    monkeypatch.setattr("wings.services.holds_school_wide", lambda user: True)
    alert = _alert(school, student_user, status="held")
    with pytest.raises(IssueRefused, match="مجمَّد"):
        issue(principal_user, school, alert.pk)
    alert.refresh_from_db()
    assert alert.status == "held"
    assert not InAppNotification.objects.filter(user=parent_user).exists()


# ── الملخّص التلقائيّ: لا علامةَ بلا إرسال ─────────────────


def test_the_digest_finds_no_parents_so_it_writes_no_notice_mark(
    frozen, school, parent_user, student_user
):
    from behavior.digest import _parents_of
    from behavior.models import AutoInfractionNotice
    from core.models import ParentStudentLink

    ParentStudentLink.objects.filter(parent=parent_user).update(can_view_behavior=True)
    assert _parents_of(student_user, school) == []
    assert not AutoInfractionNotice.objects.exists()


def test_the_digest_finds_the_parents_again_after_the_thaw(
    settings, monkeypatch, school, parent_user, student_user
):
    from behavior.digest import _parents_of
    from core.models import ParentStudentLink

    monkeypatch.setattr("notifications.hub._filter_consent", lambda parents, *a, **k: parents)
    settings.PARENTS_FROZEN = False
    ParentStudentLink.objects.filter(parent=parent_user).update(can_view_behavior=True)
    assert _parents_of(student_user, school) == [parent_user]


# ── الدفع والمهامّ ─────────────────────────────────────────


def test_the_school_wide_push_skips_parent_only_subscribers(
    frozen, monkeypatch, school, parent_user, teacher_user
):
    from notifications.models import PushSubscription
    from notifications.tasks import send_push_to_school_task

    for user in (parent_user, teacher_user):
        PushSubscription.objects.create(
            user=user,
            school=school,
            endpoint=f"https://push.example/{user.pk}",
            p256dh="k",
            is_active=True,
        )
    queued = []
    monkeypatch.setattr(
        "notifications.push_publisher.enqueue_push", lambda **kw: queued.append(kw["user_id"])
    )
    send_push_to_school_task(str(school.id), "t", "b")
    assert queued == [teacher_user.pk]


def test_the_hub_task_skips_a_parent_queued_before_the_freeze(frozen, school, parent_with_email):
    from notifications.tasks import hub_send_notification_task

    result = hub_send_notification_task.run(
        str(parent_with_email.pk), str(school.id), ["email"], "t", "b", "absence"
    )
    assert result["skipped"] == "parents_frozen"
    assert mail.outbox == []


def test_the_absence_task_does_not_push_to_parents(
    frozen, monkeypatch, school, parent_with_email, student_user
):
    from notifications.tasks import notify_absence_task

    alert = _alert(school, student_user)
    pushed = []
    monkeypatch.setattr("notifications.push_publisher.enqueue_push", lambda **kw: pushed.append(kw))
    notify_absence_task.run(str(alert.pk), None, str(school.id))
    assert pushed == []
    assert mail.outbox == []


def test_a_quiet_hours_item_for_a_parent_is_neither_sent_nor_dropped(
    frozen, monkeypatch, school, parent_with_email
):
    from unittest.mock import patch

    from notifications.tasks import release_after_quiet_hours_task, send_email_task

    payload = {"recipient_email": parent_with_email.email}
    with (
        patch.object(send_email_task, "delay") as sent,
        patch.object(release_after_quiet_hours_task, "apply_async") as again,
    ):
        result = release_after_quiet_hours_task.run(
            str(school.id), str(parent_with_email.pk), "email", payload
        )
    assert result["status"] == "held_parents_frozen"
    sent.assert_not_called()
    assert again.call_args.kwargs["kwargs"]["payload"] == payload
