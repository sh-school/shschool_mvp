"""[DBT-11] بريدٌ لا مزوّدَ له ليس عطلاً: يُوسَم `undeliverable` بتحذيرٍ واحد — بلا إعادةٍ ولا DLQ ولا Sentry.

تعريفُ المالك (2026-09-26): بريدٌ لا يُسلَّم في غياب مزوّدٍ فعليّ (`UndeliveredEmailBackend`) لا يدخل إعادةً ولا DLQ ولا Sentry،
ولا يبقى في DLQ محتوىً. والإعادةُ وDLQ لأعطال مزوّدٍ **حقيقيّ** وحدَها. وكان المسارُ كلُّه يجري لرسالةٍ لن تُسلَّم
مهما أُعيدت: `logger.error` و`logger.exception` (حدثان في Sentry) ثمّ ثلاثُ إعاداتٍ ثمّ صفُّ DLQ.
"""

import logging
from unittest.mock import patch

import pytest
from celery.exceptions import MaxRetriesExceededError
from django.test import override_settings

from core.mail_backends import UndeliveredEmailBackend, provider_configured
from notifications.models import (
    DeadLetterMessage,
    NotificationDelivery,
    NotificationDispatch,
    NotificationLog,
)
from notifications.tasks import send_email_task
from tests.conftest import SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

NO_PROVIDER = "core.mail_backends.UndeliveredEmailBackend"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def _delivery(school):
    dispatch = NotificationDispatch.objects.create(school=school, event_type="absence")
    return NotificationDelivery.objects.create(
        dispatch=dispatch, school=school, recipient=UserFactory(), channel="email"
    )


def _run(school, delivery=None):
    kwargs = {
        "school_id": str(school.id),
        "recipient_email": "parent@example.com",
        "subject": "موضوعٌ اصطناعيّ",
        "body_text": "نصٌّ اصطناعيّ",
    }
    if delivery is not None:
        kwargs["delivery_id"] = str(delivery.id)
    return send_email_task.delay(**kwargs).get()


@pytest.fixture
def no_retry():
    """أيُّ استدعاءٍ للإعادة يُسقط الاختبار — الإعادةُ لأعطال المزوّد الحقيقيّ وحدَها."""
    with patch.object(send_email_task, "retry", side_effect=AssertionError("retry")) as retry:
        yield retry


# ── الحدُّ بين «لا مزوّد» و«مزوّدٌ فشل» ────────────────────────────────────


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_the_undelivered_backend_declares_it_has_no_provider():
    assert UndeliveredEmailBackend.delivers is False
    assert provider_configured() is False


@pytest.mark.parametrize(
    "backend",
    [
        LOCMEM,
        "django.core.mail.backends.smtp.EmailBackend",
        "django.core.mail.backends.console.EmailBackend",
    ],
)
def test_any_other_backend_counts_as_a_provider(backend):
    with override_settings(EMAIL_BACKEND=backend):
        assert provider_configured() is True


# ── (أ) بلا مزوّد: لا DLQ ولا إعادة ─────────────────────────────────────────


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_a_tracked_email_without_a_provider_is_undeliverable_not_dead_lettered(no_retry):
    school = SchoolFactory()
    delivery = _delivery(school)

    result = _run(school, delivery)

    assert result == {"status": "undeliverable"}
    delivery.refresh_from_db()
    assert delivery.status == "undeliverable" and delivery.lease_token is None
    assert DeadLetterMessage.objects.count() == 0, "لا يبقى في DLQ شيء"
    assert no_retry.call_count == 0, "لا إعادة"


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_an_untracked_email_without_a_provider_is_dropped_the_same_way(no_retry):
    school = SchoolFactory()

    assert _run(school) == {"status": "undeliverable"}

    assert DeadLetterMessage.objects.count() == 0
    assert no_retry.call_count == 0


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_the_undeliverable_email_keeps_one_failed_log_row_with_the_reason(no_retry):
    """السجلُّ باقٍ: «لم يُسلَّم» بسببه — كما كان قبل التعريف الجديد."""
    school = SchoolFactory()
    delivery = _delivery(school)

    _run(school, delivery)

    logs = NotificationLog.objects.filter(school=school, channel="email")
    assert logs.count() == 1
    assert logs.get().status == "failed" and "لا مزوّد" in logs.get().error_msg
    assert logs.get().delivery_id == delivery.id


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_the_whole_path_writes_one_warning_and_no_error(caplog, no_retry):
    """Sentry يلتقط ERROR وما فوقه: تحذيرٌ واحدٌ (من الـbackend) ولا سطرَ خطأٍ ولا استثناءَ مُسجَّل."""
    school = SchoolFactory()
    delivery = _delivery(school)

    with caplog.at_level(logging.DEBUG):
        _run(school, delivery)

    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert warnings[0].name == "core.mail_backends"
    assert not any(r.exc_info for r in caplog.records), "لا traceback"


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_no_message_content_reaches_the_logs_or_the_result(caplog, no_retry):
    school = SchoolFactory()

    with caplog.at_level(logging.DEBUG):
        result = _run(school)

    everything = caplog.text + repr(result)
    for secret in ("parent@example.com", "موضوعٌ اصطناعيّ", "نصٌّ اصطناعيّ"):
        assert secret not in everything


@override_settings(EMAIL_BACKEND=NO_PROVIDER)
def test_a_marked_delivery_is_not_processed_twice(no_retry):
    """الوسمُ نهائيّ: رسالةٌ مكرَّرةٌ في الطابور لا تُنتج سجلّاً ثانياً ولا تحذيراً ثانياً."""
    school = SchoolFactory()
    delivery = _delivery(school)
    _run(school, delivery)

    second = _run(school, delivery)

    assert second == {"status": "not_claimed"}
    delivery.refresh_from_db()
    assert delivery.status == "undeliverable"
    assert NotificationLog.objects.filter(school=school, channel="email").count() == 1
    assert DeadLetterMessage.objects.count() == 0


# ── وأعطالُ المزوّد الحقيقيّ تبقى إعادةً ثمّ DLQ ────────────────────────────────


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_real_provider_failure_still_retries_then_dead_letters():
    school = SchoolFactory()
    exhausted = MaxRetriesExceededError()

    with (
        patch("django.core.mail.send_mail", side_effect=OSError("provider down")),
        patch.object(send_email_task, "retry", side_effect=exhausted) as retry,
    ):
        result = _run(school)

    assert retry.call_count == 1, "الإعادةُ لمزوّدٍ حقيقيّ تبقى"
    assert result["status"] == "dead_letter"
    assert DeadLetterMessage.objects.filter(kind="email", school=school).count() == 1


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_real_provider_that_returns_zero_is_still_an_error():
    """مزوّدٌ حقيقيّ ردّ صفراً = عطلٌ يُبلَّغ (لا «لا مزوّد»)."""
    from notifications.services import NotificationService

    school = SchoolFactory()

    with (
        patch("django.core.mail.send_mail", return_value=0),
        patch("notifications.services.logger") as log,
    ):
        ok, _err = NotificationService.send_email(
            school=school, recipient_email="p@example.com", subject="س", body_text="ن"
        )

    assert ok is False
    assert log.error.called, "ردُّ الصفر من مزوّدٍ حقيقيّ يبقى خطأً"
