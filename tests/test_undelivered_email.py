"""بريدٌ لا يُسلَّم لا يُسجَّل «أُرسل» ولا يُطبع نصُّه في السجلّ."""

from __future__ import annotations

import logging

import pytest
from django.core.mail import EmailMessage
from django.test import override_settings

from core.mail_backends import UndeliveredEmailBackend
from notifications.models import NotificationLog
from notifications.services import NotificationService

_BACKEND = "core.mail_backends.UndeliveredEmailBackend"


def test_backend_returns_zero_and_writes_no_message_content(caplog):
    msg = EmailMessage(subject="غياب سرّيّ", body="اسم الطالب الحقيقي", to=["parent@example.com"])
    with caplog.at_level(logging.DEBUG):
        assert UndeliveredEmailBackend().send_messages([msg]) == 0
    logged = caplog.text
    assert "غياب سرّيّ" not in logged
    assert "اسم الطالب الحقيقي" not in logged
    assert "parent@example.com" not in logged


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_BACKEND)
def test_send_email_is_failed_not_sent_when_nothing_delivers(school, student_user):
    ok, err = NotificationService.send_email(
        school=school,
        recipient_email="parent@example.com",
        subject="موضوع",
        body_text="نص",
        student=student_user,
        notif_type="custom",
    )

    assert ok is False
    assert err
    log = NotificationLog.objects.filter(school=school).last()
    assert log.status == "failed"
    assert log.error_msg == err


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_BACKEND)
def test_html_email_path_is_also_failed_when_nothing_delivers(school, student_user):
    ok, _ = NotificationService.send_email(
        school=school,
        recipient_email="parent@example.com",
        subject="موضوع",
        body_text="نص",
        body_html="<p>نص</p>",
        student=student_user,
        notif_type="custom",
    )

    assert ok is False
    assert NotificationLog.objects.filter(school=school).last().status == "failed"


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_a_delivering_backend_still_records_sent(school, student_user):
    ok, err = NotificationService.send_email(
        school=school,
        recipient_email="parent@example.com",
        subject="موضوع",
        body_text="نص",
        student=student_user,
        notif_type="custom",
    )

    assert ok is True
    assert err is None
    assert NotificationLog.objects.filter(school=school).last().status == "sent"


@pytest.fixture
def developer_message(db):
    from developer_feedback.models import DeveloperMessage

    return DeveloperMessage.objects.create(
        ticket_number="DEV-UNDELIVERED-1",
        user_id_hash="0" * 64,
        subject="موضوع",
        body="نص",
    )


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=_BACKEND, DEVELOPER_FEEDBACK_RECIPIENT="dev@example.test")
def test_developer_notification_is_failed_when_nothing_delivers(developer_message):
    from developer_feedback.services.notifications import (
        send_developer_edit_notification,
        send_developer_notification,
    )

    first = send_developer_notification(developer_message)
    edit = send_developer_edit_notification(developer_message)

    assert first.status == "failed"
    assert edit.status == "failed"
    assert "مزوّد بريد" in first.error_detail


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEVELOPER_FEEDBACK_RECIPIENT="dev@example.test",
)
def test_developer_notification_is_sent_with_a_delivering_backend(developer_message):
    from developer_feedback.services.notifications import send_developer_notification

    assert send_developer_notification(developer_message).status == "sent"


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEVELOPER_FEEDBACK_RECIPIENT="",
)
def test_developer_notification_without_a_configured_recipient_is_failed_not_sent(
    developer_message,
):
    from django.core import mail

    from developer_feedback.services.notifications import (
        send_developer_edit_notification,
        send_developer_notification,
    )

    first = send_developer_notification(developer_message)
    edit = send_developer_edit_notification(developer_message)

    assert first.status == "failed" and edit.status == "failed"
    assert "DEVELOPER_FEEDBACK_RECIPIENT" in first.error_detail
    assert mail.outbox == []


def test_no_real_developer_address_is_tracked_in_the_source():
    import pathlib

    src = pathlib.Path("developer_feedback/services/notifications.py").read_text(encoding="utf-8")

    assert "@education.qa" not in src
