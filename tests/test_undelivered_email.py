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
