"""
tests/test_delivery_state_wiring.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-3B] القنوات الأربع توصَّل بآلة الحالات.

العقد واحد في القنوات الثلاث التقليدية:

    حلّ التسليم  →  استحواذ  →  مزوّد  →  إنهاء مُسيَّج

وPush وحدها تكسر الشكل: نداء مزوّد لكل اشتراك، ونتيجةٌ واحدة للتسليم بعد
اكتمال الصورة — فقد تجتمع محاولة نجحت وأخرى فشلت وثالثة على اشتراك ميت.

ولا شيء من هذا يمسّ المسار القديم: `delivery_id=None` لا يلمس آلة الحالات
إطلاقاً.
"""

import sys
import types
import uuid
from unittest.mock import patch

import pytest

from notifications.delivery_state import claim_delivery, finalize_delivery
from notifications.models import (
    DeadLetterMessage,
    NotificationDelivery,
    NotificationDispatch,
    NotificationLog,
    NotificationSettings,
    PushSubscription,
)
from notifications.tasks import (
    send_email_task,
    send_push_task,
    send_sms_task,
    send_whatsapp_task,
)
from tests.conftest import SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════
# أدوات
# ══════════════════════════════════════════════════════════════════


def _delivery(school, channel, recipient=None):
    dispatch = NotificationDispatch.objects.create(school=school, event_type="absence")
    return NotificationDelivery.objects.create(
        dispatch=dispatch,
        school=school,
        recipient=recipient or UserFactory(),
        channel=channel,
    )


class _Provider:
    """مزوّد صامت — يُعيد ما يكفي `_send_whatsapp` لقراءة `sid`."""

    sid = "SM-test"

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise OSError("provider refused")
        return self


class _FakeTwilioClient:
    provider = None

    def __init__(self, *args, **kwargs):
        self.messages = self

    def create(self, **kwargs):
        return type(self).provider(**kwargs)


def _twilio(provider):
    _FakeTwilioClient.provider = provider
    return patch("twilio.rest.Client", _FakeTwilioClient)


def _twilio_settings(school):
    return NotificationSettings.objects.create(
        school=school,
        sms_enabled=True,
        sms_provider="twilio",
        sms_from_number="+97400000000",
        twilio_account_sid="AC-test",
        twilio_auth_token="token",
    )


def _status_of(delivery):
    delivery.refresh_from_db()
    return delivery.status


# ══════════════════════════════════════════════════════════════════
# النجاح
# ══════════════════════════════════════════════════════════════════


def test_a_tracked_email_that_succeeds_is_marked_sent():
    school = SchoolFactory()
    delivery = _delivery(school, "email")

    with patch("django.core.mail.send_mail", _Provider()):
        result = send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    assert result.get()["status"] == "sent"
    assert _status_of(delivery) == "sent"
    assert delivery.lease_token is None


def test_a_tracked_sms_that_succeeds_is_marked_sent():
    school = SchoolFactory()
    _twilio_settings(school)
    delivery = _delivery(school, "sms")

    with _twilio(_Provider()):
        send_sms_task.delay(
            school_id=str(school.id),
            phone_number="+97455555555",
            message="نصّ",
            delivery_id=str(delivery.id),
        )

    assert _status_of(delivery) == "sent"


def test_a_tracked_whatsapp_that_succeeds_is_marked_sent():
    school = SchoolFactory()
    _twilio_settings(school)
    delivery = _delivery(school, "whatsapp")

    with _twilio(_Provider()):
        send_whatsapp_task.delay(
            school_id=str(school.id),
            phone_number="+97455555555",
            title="عنوان",
            body="نصّ",
            delivery_id=str(delivery.id),
        )

    assert _status_of(delivery) == "sent"


# ══════════════════════════════════════════════════════════════════
# الاستحواذ المرفوض
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("status", ["sent", "dead_lettered", "undeliverable"])
def test_a_finished_delivery_stops_the_task_before_the_provider(status):
    """
    [B4-3B] استحواذ مرفوض ⇒ لا مزوّد ولا سجلّ محاولة ولا إعادة.

    وهذا ما يجعل تكرار رسالة في الطابور غير ضارّ في المسار المتتبَّع: النسخة
    الثانية تخسر الاستحواذ قبل أن تبلغ المزوّد.
    """
    school = SchoolFactory()
    delivery = _delivery(school, "email")
    NotificationDelivery.objects.filter(id=delivery.id).update(status=status)

    provider = _Provider()
    with patch("django.core.mail.send_mail", provider):
        result = send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    assert result.get()["status"] == "not_claimed"
    assert provider.calls == 0
    assert NotificationLog.objects.count() == 0
    assert _status_of(delivery) == status


def test_a_second_execution_cannot_reach_the_provider_twice():
    """
    [B4-3B] القيمة التنفيذية للسياج — لا صحّته كبدائيّة وحدها.

    تنفيذان متتبَّعان على التسليم نفسه: الأول يستحوذ ويُرسل، والثاني يخسر
    الاستحواذ. المزوّد يُنادى **مرّة واحدة**.
    """
    school = SchoolFactory()
    delivery = _delivery(school, "email")
    provider = _Provider()

    with patch("django.core.mail.send_mail", provider):
        for _ in range(2):
            send_email_task.delay(
                school_id=str(school.id),
                recipient_email="p@example.com",
                subject="عنوان",
                body_text="نصّ",
                delivery_id=str(delivery.id),
            )

    assert provider.calls == 1, "بلغ المزوّد مرّتين رغم السياج"
    assert _status_of(delivery) == "sent"


# ══════════════════════════════════════════════════════════════════
# الفشل — إعادة ثم استنفاد
# ══════════════════════════════════════════════════════════════════


def test_a_retryable_failure_writes_retry_wait_before_retrying():
    """`retry_wait` قبل `self.retry()` — فالأخير يرفع ولا يعود."""
    school = SchoolFactory()
    delivery = _delivery(school, "email")

    with patch("django.core.mail.send_mail", _Provider(fail=True)):
        with pytest.raises(Exception):  # noqa: B017 — Retry أو الأصل حسب المسار
            send_email_task.delay(
                school_id=str(school.id),
                recipient_email="p@example.com",
                subject="عنوان",
                body_text="نصّ",
                delivery_id=str(delivery.id),
            )

    assert _status_of(delivery) == "retry_wait"
    assert delivery.lease_token is None


def test_an_exhausted_delivery_is_dead_lettered_and_linked():
    """
    [B4-3B] الاستنفاد يُقرَّر قبل `self.retry()` لا بالتقاط استثنائه.

    وعقد Celery أن `retry(exc=exc)` عند تجاوز الحدّ — ونحن داخل معالجة
    استثناء — قد يُعيد رفع الاستثناء الأصلي، فبناءُ دورة الحياة على ذلك يجعل
    صحّتها رهينة تفاصيل إطار العمل.

    والربط بالطابور يصير ذا معنى لأول مرّة: صفّ DLQ يشير إلى تسليمه.
    """
    school = SchoolFactory()
    delivery = _delivery(school, "email")

    with (
        patch("django.core.mail.send_mail", _Provider(fail=True)),
        patch.object(type(send_email_task), "max_retries", 0),
    ):
        result = send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    assert result.get()["status"] == "dead_letter"
    assert _status_of(delivery) == "dead_lettered"

    dead_letter = DeadLetterMessage.objects.get()
    assert dead_letter.delivery_id == delivery.id
    assert dead_letter.kind == "email"


def test_a_lost_lease_after_success_neither_retries_nor_overwrites():
    """
    [B4-3B] عاملٌ فقد السياج لا يُعوّض ذلك بإعادة الإرسال.

    المزوّد قد يكون قبِل الرسالة، والملكيّة انتقلت. الإعادة عندئذٍ تعويضٌ عن
    سلطة فُقدت — وهي بالضبط ما يُنتج التكرار.
    """
    school = SchoolFactory()
    delivery = _delivery(school, "email")

    def _steal_the_lease(*args, **kwargs):
        NotificationDelivery.objects.filter(id=delivery.id).update(lease_token=uuid.uuid4())
        return _Provider()

    with patch("django.core.mail.send_mail", side_effect=_steal_the_lease):
        result = send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    assert result.get()["status"] == "lost_lease"
    assert _status_of(delivery) == "in_progress", "كتب حالةً وهو لا يملك الصفّ"


# ══════════════════════════════════════════════════════════════════
# المسار القديم — لا يلمس آلة الحالات
# ══════════════════════════════════════════════════════════════════


def test_a_legacy_email_never_touches_the_state_machine():
    school = SchoolFactory()

    with (
        patch("django.core.mail.send_mail", _Provider()),
        patch("notifications.tasks.claim_delivery") as claim,
        patch("notifications.tasks.finalize_delivery") as finalize,
        patch("notifications.tasks.mark_undeliverable") as undeliverable,
    ):
        result = send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
        )

    assert result.get()["status"] == "sent"
    assert not claim.called
    assert not finalize.called
    assert not undeliverable.called


def test_a_legacy_push_without_subscriptions_behaves_as_before():
    school = SchoolFactory()
    user = UserFactory()

    with patch("notifications.tasks.mark_undeliverable") as undeliverable:
        result = send_push_task.delay(
            str(user.id), "عنوان", "نصّ", "/parents/", school_id=str(school.id)
        )

    assert result.get()["status"] == "no_subscriptions"
    assert not undeliverable.called


# ══════════════════════════════════════════════════════════════════
# Push — المصفوفة
# ══════════════════════════════════════════════════════════════════


class _WebPush:
    """يُقرّر لكل endpoint: نجاح، أو فشل عابر، أو اشتراك ميت."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = 0

    def __call__(self, subscription_info, **kwargs):
        self.calls += 1
        outcome = self.outcomes[subscription_info["endpoint"]]
        if outcome is not None:
            raise outcome


class _WebPushError(Exception):
    pass


def _push_module(webpush=None, missing=False):
    if missing:
        return patch.dict(sys.modules, {"pywebpush": None})

    module = types.ModuleType("pywebpush")
    module.webpush = webpush
    module.WebPushException = _WebPushError
    return patch.dict(sys.modules, {"pywebpush": module})


def _subscription(school, user, endpoint):
    return PushSubscription.objects.create(
        school=school, user=user, endpoint=endpoint, p256dh="k", auth="a"
    )


def _run_push(user, school, delivery=None):
    return send_push_task.delay(
        str(user.id),
        "عنوان",
        "نصّ",
        "/parents/",
        school_id=str(school.id),
        delivery_id=str(delivery.id) if delivery else None,
    )


def test_push_without_subscriptions_is_undeliverable_without_a_claim():
    """
    [B4-3B] لا وجهة أصلاً — ولا استحواذ.

    المرور بـ`in_progress` هنا ادّعاءٌ بأن تنفيذاً جرى: لم تُنادَ منطقة مزوّد
    ولا كُتب سجلّ محاولة.
    """
    school = SchoolFactory()
    user = UserFactory()
    delivery = _delivery(school, "push", recipient=user)

    result = _run_push(user, school, delivery)

    assert result.get()["status"] == "no_subscriptions"
    assert _status_of(delivery) == "undeliverable"
    assert NotificationLog.objects.count() == 0


def test_push_partial_success_is_sent_and_not_retried():
    """عقد B3 محفوظ: النجاح الجزئي نجاح، وإعادتُه تُكرّر على الجهاز الذي وصلته."""
    school = SchoolFactory()
    user = UserFactory()
    delivery = _delivery(school, "push", recipient=user)
    _subscription(school, user, "https://push.example/a")
    _subscription(school, user, "https://push.example/b")

    webpush = _WebPush(
        {"https://push.example/a": None, "https://push.example/b": _WebPushError("boom")}
    )

    with _push_module(webpush):
        result = _run_push(user, school, delivery)

    assert result.get()["sent"] == 1
    assert _status_of(delivery) == "sent"
    assert NotificationLog.objects.count() == 2


def test_push_with_every_endpoint_gone_is_undeliverable():
    """
    [B4-3B] الفرع الذي كان بلا حالة صادقة.

    اشتراكان ردّ المزوّد على كليهما بـ410: `sent=0` و`transient=0` و
    `invalidated=2`. المهمّة تنتهي اليوم بنجاح عدديّ رغم أن الرسالة لم تبلغ
    جهازاً واحداً — والوجهات ميتة نهائياً فلا إعادة تُحييها.
    """
    school = SchoolFactory()
    user = UserFactory()
    delivery = _delivery(school, "push", recipient=user)
    _subscription(school, user, "https://push.example/a")
    _subscription(school, user, "https://push.example/b")

    webpush = _WebPush(
        {
            "https://push.example/a": _WebPushError("410 gone"),
            "https://push.example/b": _WebPushError("404 not found"),
        }
    )

    with _push_module(webpush):
        result = _run_push(user, school, delivery)

    assert result.get()["invalidated"] == 2
    assert _status_of(delivery) == "undeliverable"

    # المحاولات جرت فعلاً — وهذا ما يُميّز هذا الفرع عن "بلا اشتراكات".
    assert NotificationLog.objects.filter(status="failed").count() == 2


def test_push_with_every_endpoint_transient_waits_to_retry():
    school = SchoolFactory()
    user = UserFactory()
    delivery = _delivery(school, "push", recipient=user)
    _subscription(school, user, "https://push.example/a")

    webpush = _WebPush({"https://push.example/a": _WebPushError("503 unavailable")})

    with _push_module(webpush), pytest.raises(Exception):  # noqa: B017
        _run_push(user, school, delivery)

    assert _status_of(delivery) == "retry_wait"


def test_a_missing_push_library_is_a_failure_when_tracked():
    """
    [B4-3B] المكتبة الغائبة عطلٌ تشغيلي لا "لا وجهة".

    الوجهة موجودة والنظام هو الذي لا يستطيع بلوغها، فالإعادة قد تنجح على عامل
    آخر — وتصنيفها `undeliverable` كان سيُنهي التسليم بصمت.
    """
    school = SchoolFactory()
    user = UserFactory()
    delivery = _delivery(school, "push", recipient=user)
    _subscription(school, user, "https://push.example/a")

    with _push_module(missing=True), pytest.raises(Exception):  # noqa: B017
        _run_push(user, school, delivery)

    assert _status_of(delivery) == "retry_wait"


def test_a_missing_push_library_is_unchanged_for_legacy():
    school = SchoolFactory()
    user = UserFactory()
    _subscription(school, user, "https://push.example/a")

    with _push_module(missing=True):
        result = _run_push(user, school)

    assert result.get()["status"] == "queued_no_pywebpush"


# ══════════════════════════════════════════════════════════════════
# البدائيّة الجديدة
# ══════════════════════════════════════════════════════════════════


def test_mark_undeliverable_needs_no_claim():
    from notifications.delivery_state import mark_undeliverable

    school = SchoolFactory()
    delivery = _delivery(school, "push")

    assert mark_undeliverable(delivery.id, school.id) is True
    assert _status_of(delivery) == "undeliverable"


def test_mark_undeliverable_refuses_a_claimed_delivery():
    """تسليمٌ يملكه تنفيذ لا يُنهيه طرفٌ خارج السياج."""
    from notifications.delivery_state import mark_undeliverable

    school = SchoolFactory()
    delivery = _delivery(school, "push")
    claim_delivery(delivery.id, school.id)

    assert mark_undeliverable(delivery.id, school.id) is False
    assert _status_of(delivery) == "in_progress"


def test_undeliverable_is_terminal():
    school = SchoolFactory()
    delivery = _delivery(school, "push")
    token = claim_delivery(delivery.id, school.id)
    finalize_delivery(delivery.id, school.id, token, "undeliverable")

    assert claim_delivery(delivery.id, school.id) is None
