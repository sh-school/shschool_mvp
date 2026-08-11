"""
tests/test_delivery_wire_compatibility.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-1] العمّال يفهمون السلك الجديد قبل أن يُسمح لأيّ منتج بإرساله.

الاتجاه الخطر ليس متماثلاً. عاملٌ جديد يستقبل رسالة قديمة يربط الوسيطة الغائبة
بقيمتها الافتراضية ويعمل. أمّا عاملٌ قديم يستقبل رسالة تحمل وسيطة لا يعرفها
فيرفع `TypeError` عند التنفيذ، وCelery يعتبرها فشلاً ويؤكّد الرسالة — فتُفقد ولا
تُعاد. `task_acks_late` يحمي من موت العامل لا من خطأ داخل المهمّة.

ولهذا يسبق **القبولُ** الإرسالَ بإصدار كامل. هذه الدفعة تقبل ولا تُرسل: لا كاتب
تطبيقي يُمرّر `dispatch_id` ولا `delivery_id`، ولا شيء يُنشئ واقعةً أو تسليماً.

والقبول هنا ليس ابتلاعاً للوسيطة. مهمّة تقبل `delivery_id` ثم تتجاهله تنجو من
`TypeError` ولا تصير صالحة لاستهلاك رسائل الإصدار التالي — وهو الغرض كلّه.
"""

import inspect
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from celery.exceptions import Retry

from notifications.models import (
    NotificationDelivery,
    NotificationDispatch,
    NotificationLog,
)
from notifications.tasks import (
    hub_send_notification_task,
    send_email_task,
    send_push_task,
    send_sms_task,
    send_whatsapp_task,
)
from tests.conftest import SchoolFactory, UserFactory

ROOT = Path(__file__).resolve().parents[1]

# لا pytestmark عام: فحوص التوقيع وحارس المصدر تعمل بلا قاعدة بيانات.


# ══════════════════════════════════════════════════════════════════
# شكل السلك — الموضع هو الفخّ
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (send_email_task, "delivery_id"),
        (send_sms_task, "delivery_id"),
        (send_whatsapp_task, "delivery_id"),
        (send_push_task, "delivery_id"),
        (hub_send_notification_task, "dispatch_id"),
    ],
)
def test_the_new_wire_argument_is_last_and_optional(task, expected):
    """
    الوسيطة الجديدة آخر الترتيب وبقيمة افتراضية.

    Push تُستدعى بأربعة وسائط **موضعية** في مسارين قائمين، فإدخال وسيطة قبل
    `school_id` كان سيُزيح الربط بصمت: `body` يستقبل رابطاً، والرسالة تخرج
    مشوّهة بلا خطأ واحد.
    """
    parameters = list(inspect.signature(task.run).parameters.values())

    assert parameters[-1].name == expected
    assert parameters[-1].default is None


def test_hub_carries_a_dispatch_not_a_delivery():
    """
    [B4-1] المستلم الواحد على أربع قنوات يقابله أربعة تسليمات لا واحد.

    تسمية الوسيطة `delivery_id` هنا كانت ستفرض هويّة تسليم واحدة على مهمّة
    تفوّض أربعاً.
    """
    names = set(inspect.signature(hub_send_notification_task.run).parameters)

    assert "dispatch_id" in names
    assert "delivery_id" not in names


def test_the_old_positional_push_call_binds_identically():
    """
    استدعاء بالنمط القديم يربط كما كان بالضبط.

    هذا ما تحمله رسالة من إصدار سابق: أربعة وسائط موضعية و`school_id` مفتاحية.
    """
    signature = inspect.signature(send_push_task.run)

    bound = signature.bind("user-1", "عنوان", "نصّ", "/parents/", school_id="school-1")

    assert bound.arguments == {
        "user_id": "user-1",
        "title": "عنوان",
        "body": "نصّ",
        "url": "/parents/",
        "school_id": "school-1",
    }


@pytest.mark.parametrize(
    "task",
    [send_email_task, send_sms_task, send_whatsapp_task, send_push_task],
)
def test_channel_tasks_carry_a_delivery_not_a_dispatch(task):
    """وحدة القناة تسليم؛ الواقعة شأن الـHub."""
    names = set(inspect.signature(task.run).parameters)

    assert "delivery_id" in names
    assert "dispatch_id" not in names


# ══════════════════════════════════════════════════════════════════
# أدوات
# ══════════════════════════════════════════════════════════════════


class _Provider:
    """مزوّد صامت — الاختبارات هنا عن السلك لا عن الإرسال."""

    sid = "SM-test"

    def __call__(self, *args, **kwargs):
        return self


class _FakeTwilioClient:
    provider = None

    def __init__(self, *args, **kwargs):
        self.messages = self

    def create(self, **kwargs):
        return type(self).provider(**kwargs)


@contextmanager
def _silent_providers():
    _FakeTwilioClient.provider = _Provider()
    with (
        patch("django.core.mail.send_mail", _Provider()),
        patch("twilio.rest.Client", _FakeTwilioClient),
    ):
        yield


def _twilio_settings(school):
    from notifications.models import NotificationSettings

    return NotificationSettings.objects.create(
        school=school,
        sms_enabled=True,
        sms_provider="twilio",
        sms_from_number="+97400000000",
        twilio_account_sid="AC-test",
        twilio_auth_token="token",
    )


def _delivery_for(school, recipient, channel, dispatch=None):
    dispatch = dispatch or NotificationDispatch.objects.create(
        school=school, event_type="absence_alert"
    )
    return NotificationDelivery.objects.create(
        dispatch=dispatch, school=school, recipient=recipient, channel=channel
    )


@contextmanager
def _expect_refusal():
    """المهمّة ترفض فتُجدوِل إعادة — والسبب `ValueError` تحتها.

    `self.retry` يرفع `celery.exceptions.Retry` حين تصل المهمّة عبر الطابور،
    ويُعيد رفع الاستثناء الأصلي فقط عند الاستدعاء المباشر. فالمُلاحَظ هنا هو
    ما يراه العامل الحقيقي، والسبب يُفحص تحته كي لا يمرّ الاختبار على إعادة
    جُدولت لعلّة أخرى.
    """
    with pytest.raises(Retry) as caught:
        yield

    assert isinstance(caught.value.exc, ValueError), f"سبب آخر: {caught.value.exc!r}"


# ══════════════════════════════════════════════════════════════════
# الرسائل القديمة — المسار الحالي حرفياً
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_channel_task_without_a_delivery_behaves_as_before():
    """رسالة إصدار سابق تُنفَّذ كما كانت، وسجلّها بلا تسليم."""
    school = SchoolFactory()

    with _silent_providers():
        send_email_task.delay(
            school_id=str(school.id),
            recipient_email="parent@example.com",
            subject="عنوان",
            body_text="نصّ",
        )

    log = NotificationLog.objects.get()
    assert log.status == "sent"
    assert log.delivery_id is None


@pytest.mark.django_db
def test_a_hub_message_without_a_dispatch_behaves_as_before():
    """الـHub بلا واقعة يفوّض القنوات بلا `delivery_id` — ولا يقرأ شيئاً."""
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with patch("notifications.tasks.send_email_task.delay") as email:
        hub_send_notification_task.delay(
            user_id=str(user.id),
            school_id=str(school.id),
            channels=["email"],
            title="عنوان",
            body="نصّ",
            event_type="absence",
        )

    assert email.call_args.kwargs["delivery_id"] is None
    assert NotificationDispatch.objects.count() == 0
    assert NotificationDelivery.objects.count() == 0


# ══════════════════════════════════════════════════════════════════
# المسار المتتبَّع — قراءة فقط
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_the_hub_resolves_one_delivery_per_channel():
    """
    [B4-1] الـHub يبحث ولا يُنشئ.

    كل قناة تأخذ تسليمها هي — لا تسليم قناة أخرى، ولا تسليماً مُختلقاً عند
    الحاجة.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com", phone="+97455555555")
    dispatch = NotificationDispatch.objects.create(school=school, event_type="absence_alert")

    email_delivery = _delivery_for(school, user, "email", dispatch)
    sms_delivery = _delivery_for(school, user, "sms", dispatch)

    with (
        patch("notifications.tasks.send_email_task.delay") as email,
        patch("notifications.tasks.send_sms_task.delay") as sms,
    ):
        hub_send_notification_task.delay(
            user_id=str(user.id),
            school_id=str(school.id),
            channels=["email", "sms"],
            title="عنوان",
            body="نصّ",
            event_type="absence",
            dispatch_id=str(dispatch.id),
        )

    assert email.call_args.kwargs["delivery_id"] == str(email_delivery.id)
    assert sms.call_args.kwargs["delivery_id"] == str(sms_delivery.id)

    assert NotificationDispatch.objects.count() == 1
    assert NotificationDelivery.objects.count() == 2


@pytest.mark.django_db
def test_a_missing_delivery_stops_every_channel():
    """
    [B4-1] يفشل مغلقاً — ولا يُرسل قناةً واحدة.

    التسليم يُحلّ لكل القنوات قبل إطلاق أيّها. لولا ذلك لخرج البريد متتبَّعاً
    ثم اكتُشف نقص تسليم SMS، فبقيت حالة نصفية لا يصفها شيء — والأسوأ أن
    الإشعار يكون قد وصل فلا يمكن سحبه.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com", phone="+97455555555")
    dispatch = NotificationDispatch.objects.create(school=school, event_type="absence_alert")
    _delivery_for(school, user, "email", dispatch)  # SMS بلا تسليم

    with (
        patch("notifications.tasks.send_email_task.delay") as email,
        patch("notifications.tasks.send_sms_task.delay") as sms,
    ):
        with _expect_refusal():
            hub_send_notification_task.delay(
                user_id=str(user.id),
                school_id=str(school.id),
                channels=["email", "sms"],
                title="عنوان",
                body="نصّ",
                event_type="absence",
                dispatch_id=str(dispatch.id),
            )

    assert not email.called
    assert not sms.called


@pytest.mark.django_db
def test_a_channel_the_user_cannot_receive_needs_no_delivery():
    """
    القنوات المطلوبة ليست القنوات المُطابَرة.

    مستخدم بلا هاتف لا تُرسَل له SMS، فاشتراط تسليم لها كان سيُفشل مساراً
    مشروعاً بحجّة نقصٍ لا أثر له.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com", phone="")
    dispatch = NotificationDispatch.objects.create(school=school, event_type="absence_alert")
    email_delivery = _delivery_for(school, user, "email", dispatch)

    with patch("notifications.tasks.send_email_task.delay") as email:
        hub_send_notification_task.delay(
            user_id=str(user.id),
            school_id=str(school.id),
            channels=["email", "sms"],
            title="عنوان",
            body="نصّ",
            event_type="absence",
            dispatch_id=str(dispatch.id),
        )

    assert email.call_args.kwargs["delivery_id"] == str(email_delivery.id)


@pytest.mark.django_db
def test_a_tracked_attempt_is_linked_to_its_delivery():
    """المحاولة تُنسب إلى تسليمها — وهذا هو ما يجعل الإصدار مستهلكاً حقيقياً."""
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")
    delivery = _delivery_for(school, user, "email")

    with _silent_providers():
        send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    log = NotificationLog.objects.get()
    assert log.delivery_id == delivery.id
    assert log.status == "sent"


@pytest.mark.django_db
def test_a_tracked_push_links_every_attempt_to_one_delivery():
    """
    تسليم واحد للمستخدم على هذه القناة، ومحاولة لكل اشتراك.

    وهذا بالضبط ما يعنيه `Attempt N:1 Delivery` — لا تسليم لكل جهاز.
    """
    from notifications.models import PushSubscription

    school = SchoolFactory()
    user = UserFactory()
    delivery = _delivery_for(school, user, "push")

    for endpoint in ("https://push.example/a", "https://push.example/b"):
        PushSubscription.objects.create(
            school=school, user=user, endpoint=endpoint, p256dh="k", auth="a"
        )

    import sys
    import types

    module = types.ModuleType("pywebpush")
    module.webpush = lambda **kwargs: None
    module.WebPushException = type("WebPushException", (Exception,), {})

    with patch.dict(sys.modules, {"pywebpush": module}):
        send_push_task.delay(
            str(user.id),
            "عنوان",
            "نصّ",
            "/parents/",
            school_id=str(school.id),
            delivery_id=str(delivery.id),
        )

    assert NotificationLog.objects.count() == 2
    assert set(NotificationLog.objects.values_list("delivery_id", flat=True)) == {delivery.id}


# ══════════════════════════════════════════════════════════════════
# التحقّق — هويّة ليست هويّتها
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_delivery_from_another_school_is_refused():
    """مُعرِّف تسليم من مدرسة أخرى لا يُرسَل عليه شيء."""
    school = SchoolFactory()
    other = SchoolFactory()
    foreign = _delivery_for(other, UserFactory(), "email")

    with _silent_providers(), _expect_refusal():
        send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(foreign.id),
        )

    assert NotificationLog.objects.count() == 0


@pytest.mark.django_db
def test_a_delivery_for_another_channel_is_refused():
    """تسليم SMS لا يُنفَّذ كبريد ولو كان لنفس المدرسة والمستلم."""
    school = SchoolFactory()
    delivery = _delivery_for(school, UserFactory(), "sms")

    with _silent_providers(), _expect_refusal():
        send_email_task.delay(
            school_id=str(school.id),
            recipient_email="p@example.com",
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    assert NotificationLog.objects.count() == 0


@pytest.mark.django_db
def test_a_push_delivery_for_another_recipient_is_refused():
    """
    Push يحمل `user_id` في السلك، فيُفحص المستلم أيضاً.

    القنوات الأخرى لا تحمله — تحمل بريداً أو رقماً — فالفحص هناك يقف عند
    المدرسة والقناة.
    """
    school = SchoolFactory()
    someone_else = UserFactory()
    delivery = _delivery_for(school, someone_else, "push")

    with _expect_refusal():
        send_push_task.delay(
            str(UserFactory().id),
            "عنوان",
            "نصّ",
            "/parents/",
            school_id=str(school.id),
            delivery_id=str(delivery.id),
        )

    assert NotificationLog.objects.count() == 0


@pytest.mark.django_db
def test_an_unknown_delivery_is_refused():
    """مُعرِّف لا يقابل صفّاً: لا إرسال، ولا اختلاق تسليم ليطابقه."""
    import uuid

    school = SchoolFactory()

    with _silent_providers(), _expect_refusal():
        send_sms_task.delay(
            school_id=str(school.id),
            phone_number="+97455555555",
            message="نصّ",
            delivery_id=str(uuid.uuid4()),
        )

    assert NotificationLog.objects.count() == 0
    assert NotificationDelivery.objects.count() == 0


@pytest.mark.django_db
def test_a_tracked_whatsapp_attempt_is_linked():
    school = SchoolFactory()
    _twilio_settings(school)
    delivery = _delivery_for(school, UserFactory(), "whatsapp")

    with _silent_providers():
        send_whatsapp_task.delay(
            school_id=str(school.id),
            phone_number="+97455555555",
            title="عنوان",
            body="نصّ",
            delivery_id=str(delivery.id),
        )

    assert NotificationLog.objects.get().delivery_id == delivery.id


# ══════════════════════════════════════════════════════════════════
# لا منتج بعد
# ══════════════════════════════════════════════════════════════════


SKIPPED_DIRS = {
    ".venv",
    ".git",
    ".claude",
    "migrations",
    "tests",
    "staticfiles",
    "htmlcov",
    "_archive",
    "node_modules",
    "__pycache__",
}


def _application_sources():
    for path in ROOT.rglob("*.py"):
        if SKIPPED_DIRS & set(path.relative_to(ROOT).parts):
            continue
        yield path, path.read_text(encoding="utf-8")


def _call_blocks(source, marker):
    """نصّ كل استدعاء يبدأ بـmarker حتى قوس الإغلاق."""
    blocks = []
    lines = source.splitlines()

    for index, line in enumerate(lines):
        if marker not in line:
            continue
        depth = 0
        collected = []
        for candidate in lines[index:]:
            collected.append(candidate)
            depth += candidate.count("(") - candidate.count(")")
            if depth <= 0 and collected:
                break
        blocks.append("\n".join(collected))

    return blocks


def _hub_producer_blocks():
    blocks = []
    for path, text in _application_sources():
        for block in _call_blocks(text, "hub_send_notification_task.delay("):
            blocks.append((path.relative_to(ROOT), block))
    return blocks


def test_no_producer_sends_a_dispatch_id_yet():
    """
    [B4-1] الإصدار مستهلك لا منتج.

    الغرض من هذه الدفعة أن يفهم العامل السلك الجديد **قبل** أن يُرسله أحد.
    منتجٌ يسبق ذلك يُبطل الترتيب كلّه، فيصير عاملٌ قديم قد يستقبل رسالة لا
    يفهمها — وهي تُفقد بلا إعادة.
    """
    offenders = [f"{path}" for path, block in _hub_producer_blocks() if "dispatch_id" in block]

    assert not offenders, "منتج سابق لأوانه: " + ", ".join(offenders)


def test_the_producer_scanner_sees_the_real_call_site():
    """ماسح لا يجد شيئاً يمرّ دائماً — نُثبت أنه يرى استدعاء الـHub الفعلي."""
    blocks = _hub_producer_blocks()

    assert blocks, "لم يُعثر على أي استدعاء لـhub_send_notification_task.delay"
    assert any(str(path).endswith("hub.py") for path, _ in blocks)
    assert any("user_id=" in block for _, block in blocks)
