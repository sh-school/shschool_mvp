"""غياب المستلِم لا يضيع الإشعارات بصمت (W-20261121-005).

- فحص Django يحذّر في الإنتاج عند غياب `DEVELOPER_FEEDBACK_RECIPIENT`.
- الأمر `resend_developer_notifications` يعيد إرسال الفاشلة لهذا السبب، وidempotent.
البيانات اصطناعيّة حصرًا.
"""

from __future__ import annotations

import pytest
from django.core import mail
from django.core.checks import Warning as CheckWarning
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from developer_feedback.checks import W_RECIPIENT_MISSING, check_developer_recipient
from developer_feedback.models import (
    DeveloperMessage,
    DeveloperMessageNotification,
    NotificationStatus,
)
from developer_feedback.services.notifications import send_developer_notification

_LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
_RECIPIENT = "dev@example.test"


@override_settings(DEBUG=False, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_check_warns_in_production_when_recipient_missing(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    messages = check_developer_recipient(None)

    assert len(messages) == 1
    assert isinstance(messages[0], CheckWarning)
    assert messages[0].id == W_RECIPIENT_MISSING


@override_settings(DEBUG=False, DEVELOPER_FEEDBACK_RECIPIENT=_RECIPIENT)
def test_check_is_silent_when_recipient_is_configured(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert check_developer_recipient(None) == []


@override_settings(DEBUG=True, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_check_is_silent_in_debug_mode(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert check_developer_recipient(None) == []


@override_settings(DEBUG=False, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_check_is_silent_outside_the_platform(monkeypatch):
    # فحص النشر في CI لا يجوز أن يفشل بسبب متغيّرٍ لا يُضبط هناك
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    assert check_developer_recipient(None) == []


@pytest.fixture
def developer_message(db):
    return DeveloperMessage.objects.create(
        ticket_number="DEV-RESEND-1",
        user_id_hash="0" * 64,
        subject="موضوع",
        body="نص",
    )


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_LOCMEM, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_missing_recipient_leaves_a_failed_notification_with_empty_recipient(developer_message):
    notification = send_developer_notification(developer_message)

    assert notification.status == NotificationStatus.FAILED
    assert notification.recipient == ""
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_LOCMEM, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_resend_refuses_to_run_while_recipient_is_still_missing(developer_message):
    send_developer_notification(developer_message)

    with pytest.raises(CommandError):
        call_command("resend_developer_notifications")
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_LOCMEM, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_resend_after_configuring_sends_once_and_is_idempotent(developer_message):
    send_developer_notification(developer_message)

    with override_settings(DEVELOPER_FEEDBACK_RECIPIENT=_RECIPIENT):
        call_command("resend_developer_notifications")
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [_RECIPIENT]

        call_command("resend_developer_notifications")
        assert len(mail.outbox) == 1

    sent = DeveloperMessageNotification.objects.filter(
        message=developer_message, status=NotificationStatus.SENT
    )
    assert sent.count() == 1


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_LOCMEM, DEVELOPER_FEEDBACK_RECIPIENT="")
def test_resend_dry_run_sends_nothing(developer_message, capsys):
    send_developer_notification(developer_message)

    with override_settings(DEVELOPER_FEEDBACK_RECIPIENT=_RECIPIENT):
        call_command("resend_developer_notifications", "--dry-run")

    assert mail.outbox == []
    assert "DEV-RESEND-1" in capsys.readouterr().out
