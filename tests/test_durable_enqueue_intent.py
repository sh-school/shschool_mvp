"""[B4-PRE4] النيّة الدائمة — ما يبقى بعد أن تموت العملية.

قبل هذه الدفعة كان عنوان الرسالة ونصّها يعيشان في إغلاق `on_commit` وحده. فإن
سقط الوسيط أو ماتت العملية بين الالتزام والطبر، بقي في القاعدة تسليمٌ `pending`
لا يعرف أحد ماذا يُعيد إرساله — مُصالِحُ B4-4 كان سيجد صفّاً ولا يجد رسالة.

هذه الاختبارات تُثبّت العقد: النيّة تُنشأ مع التسليمات في المعاملة نفسها، والـ
callback لا يحمل إلّا مُعرِّفها، وإعادة المحاولة تقرأ من القاعدة لا من الذاكرة.
"""

import inspect
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from notifications import hub
from notifications.enqueue_state import claim_enqueue_intent, finish_enqueue_attempt
from notifications.hub import NotificationHub
from notifications.models import (
    NotificationDelivery,
    NotificationDispatch,
    NotificationEnqueueIntent,
)
from tests.conftest import SchoolFactory, UserFactory

TRACKED = override_settings(NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED=True)


@pytest.fixture
def recipient(db):
    """مستلم ببريد بلا هاتف — فقناته الوحيدة القابلة للتسليم هي البريد."""
    school = SchoolFactory()
    user = UserFactory(email="parent@example.com", phone="")
    return school, user


def _dispatch(school, user, event_type="plan_update"):
    """`plan_update` يطلب `in_app` والبريد وحدهما — قناةٌ خارجية واحدة تعتمد
    على وجهة اتصال، فلا يختلط الأمر بـ`push` المتاح لكل مستخدم."""
    return NotificationHub.dispatch(
        event_type=event_type,
        school=school,
        recipients=[user],
        title="عنوان دائم",
        body="نصّ دائم",
    )


# ═══════════════════════════════════════════════════════════════════
#  الذرّية — النيّة تعيش وتموت مع ما تصفه
# ═══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_rollback_removes_dispatch_deliveries_and_intent_together(recipient):
    """التراجع يُزيل الثلاثة معاً — لا نيّة يتيمة تصف واقعة لم تقع."""
    school, user = recipient

    class _SentinelError(RuntimeError):
        """يُجهض المعاملة بلا أن يختلط بخطأ حقيقي."""

    with pytest.raises(_SentinelError), transaction.atomic():
        _dispatch(school, user)
        assert NotificationEnqueueIntent.objects.count() == 1
        raise _SentinelError

    assert NotificationDispatch.objects.count() == 0
    assert NotificationDelivery.objects.count() == 0
    assert NotificationEnqueueIntent.objects.count() == 0


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_intent_created_only_for_recipients_with_deliveries(recipient):
    """بلا تسليم لا نيّة — النيّة تعني عملاً خارجياً."""
    school, _ = recipient
    contactless = UserFactory(email="", phone="")

    _dispatch(school, contactless)

    assert NotificationDelivery.objects.count() == 0
    assert NotificationEnqueueIntent.objects.count() == 0


# ═══════════════════════════════════════════════════════════════════
#  الـcallback — مُعرِّف وحده
# ═══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_tracked_callback_carries_intent_id_only(recipient, django_capture_on_commit_callbacks):
    """لا مستخدم ولا قنوات ولا عنوان في الإغلاق — مفتاحٌ إلى صفّ ملتزم فقط."""
    school, user = recipient

    with patch.object(hub, "_enqueue_intent_now", return_value=True) as spy:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()
    spy.assert_called_once_with(str(intent.id), str(school.id))

    # ولا حجّة من حجج النداء تسرّبت إلى التسجيل.
    (call,) = spy.call_args_list
    assert "عنوان دائم" not in str(call)
    assert "نصّ دائم" not in str(call)


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_tracked_path_does_not_use_the_legacy_closure_registrar(
    recipient, django_capture_on_commit_callbacks
):
    """المسار المتتبَّع لا يمرّ بـ`_queue_external_after_commit` إطلاقاً."""
    school, user = recipient

    with patch.object(hub, "_queue_external_after_commit") as legacy:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    legacy.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_legacy_path_still_carries_the_full_call(recipient, django_capture_on_commit_callbacks):
    """الراية مطفأة ⇒ المسار القديم حرفياً كما كان: إغلاقٌ يحمل كل شيء."""
    school, user = recipient

    with patch.object(hub, "_queue_external_after_commit") as legacy:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    legacy.assert_called_once()
    assert legacy.call_args.kwargs["title"] == "عنوان دائم"
    assert legacy.call_args.kwargs["dispatch_id"] is None
    assert NotificationEnqueueIntent.objects.count() == 0


# ═══════════════════════════════════════════════════════════════════
#  الديمومة — ما يبقى بعد فشل الوسيط
# ═══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_broker_failure_keeps_intent_content_and_pending_deliveries(
    recipient, django_capture_on_commit_callbacks
):
    """الطبر يسقط ⇒ النصّ باقٍ في القاعدة والتسليمات `pending` بانتظار المُصالِح."""
    school, user = recipient

    with patch(
        "notifications.tasks.hub_send_notification_task.delay",
        side_effect=OSError("broker down"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()
    assert intent.title == "عنوان دائم"
    assert intent.body == "نصّ دائم"
    assert intent.last_enqueue_attempt_at is not None  # المحاولة سُجّلت رغم فشلها
    assert intent.enqueue_token is None  # والاستئجار فُرّغ
    assert set(NotificationDelivery.objects.values_list("status", flat=True)) == {"pending"}


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_retry_reads_title_and_body_from_the_database(
    recipient, django_capture_on_commit_callbacks
):
    """إعادة المحاولة تبني النداء من الصفّ — لا من إغلاقٍ مات مع الطلب."""
    school, user = recipient

    with patch(
        "notifications.tasks.hub_send_notification_task.delay",
        side_effect=OSError("broker down"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()

    # عمليةٌ جديدة تماماً: لا إغلاق، لا مستخدم في الذاكرة — مُعرِّفان فقط.
    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        assert hub._enqueue_intent_now(str(intent.id), str(school.id)) is True

    delay.assert_called_once()
    assert delay.call_args.kwargs["title"] == "عنوان دائم"
    assert delay.call_args.kwargs["body"] == "نصّ دائم"
    assert delay.call_args.kwargs["user_id"] == str(user.id)
    assert delay.call_args.kwargs["channels"] == ["email"]


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_existing_deliveries_are_the_ceiling_of_what_may_be_sent(
    recipient, django_capture_on_commit_callbacks
):
    """القنوات تُشتقّ من التسليمات `pending`: ما نجح لا يُعاد، وما استُجدّ لا يُفتح."""
    school, user = recipient

    # `behavior_l3` يطلب أربع قنوات خارجية، لكن المستلم بلا هاتف — فالتسليمات
    # المُنشأة بريدٌ ودفعٌ فقط، وتلك هي مجموعة العمل المسموحة إلى الأبد.
    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user, event_type="behavior_l3")

    assert sorted(NotificationDelivery.objects.values_list("channel", flat=True)) == [
        "email",
        "push",
    ]

    # قناة نجحت بالفعل، ووجهةُ اتصال جديدة ظهرت بعد إنشاء الواقعة.
    NotificationDelivery.objects.filter(channel="email").update(status="sent")
    user.phone = "+97455111111"
    user.save(update_fields=["phone"])

    intent = NotificationEnqueueIntent.objects.get()

    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        hub._enqueue_intent_now(str(intent.id), str(school.id))

    assert delay.call_args.kwargs["channels"] == ["push"]


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_no_pending_delivery_means_no_enqueue(recipient, django_capture_on_commit_callbacks):
    """كل التسليمات انتهت ⇒ لا نداء، والمحاولة مع ذلك تُسجَّل فلا حلقة ساخنة."""
    school, user = recipient

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    NotificationDelivery.objects.update(status="sent")
    intent = NotificationEnqueueIntent.objects.get()

    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        assert hub._enqueue_intent_now(str(intent.id), str(school.id)) is False

    delay.assert_not_called()
    intent.refresh_from_db()
    assert intent.last_enqueue_attempt_at is not None


# ═══════════════════════════════════════════════════════════════════
#  الاستئجار — سياج الطبر
# ═══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_only_one_of_two_claimants_wins(recipient, django_capture_on_commit_callbacks):
    """مُصالِحان على نيّة واحدة — أحدهما يخسر، والخسارة ليست خطأً."""
    school, user = recipient

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()

    first = claim_enqueue_intent(intent.id, school.id)
    second = claim_enqueue_intent(intent.id, school.id)

    assert first is not None
    assert second is None


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_expired_enqueue_lease_is_reclaimable(recipient, django_capture_on_commit_callbacks):
    """خلافاً لاستئجار التسليم: المنقضي هنا يُستحوَذ عليه ثانيةً.

    عاملٌ فُقد أثناء الطبر لا يترك احتمالاً بأن المزوّد استقبل شيئاً — وأسوأ ما
    يقع رسالةٌ مكرّرة في الوسيط، يحتملها سياج التسليم.
    """
    school, user = recipient

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()
    claim_enqueue_intent(intent.id, school.id, lease_seconds=60)

    later = timezone.now() + timedelta(seconds=61)
    assert claim_enqueue_intent(intent.id, school.id, now=later) is not None


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_a_school_cannot_claim_another_schools_intent(
    recipient, django_capture_on_commit_callbacks
):
    """المدرسة شرطٌ صريح في الاستحواذ — لا يكفي المُعرِّف."""
    school, user = recipient
    other = SchoolFactory()

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()

    assert claim_enqueue_intent(intent.id, other.id) is None
    assert hub._enqueue_intent_now(str(intent.id), str(other.id)) is False


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_finish_requires_the_matching_token(recipient, django_capture_on_commit_callbacks):
    """رمزٌ غريب لا يُفرّغ استئجار غيره."""
    school, user = recipient

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user)

    intent = NotificationEnqueueIntent.objects.get()
    token = claim_enqueue_intent(intent.id, school.id)

    assert finish_enqueue_attempt(intent.id, school.id, uuid.uuid4()) is False
    assert finish_enqueue_attempt(intent.id, school.id, token) is True

    intent.refresh_from_db()
    assert intent.enqueue_token is None
    assert intent.enqueue_expires_at is None


@pytest.mark.django_db
def test_enqueue_lease_rejects_non_positive_seconds(recipient):
    """صفرٌ أو سالب يُنشئ استئجاراً منتهياً فور إنشائه — يُرفض عند المصدر."""
    school, _ = recipient

    for seconds in (0, -1, -60):
        with pytest.raises(ValueError):
            claim_enqueue_intent(uuid.uuid4(), school.id, lease_seconds=seconds)


# ═══════════════════════════════════════════════════════════════════
#  حارس البنية
# ═══════════════════════════════════════════════════════════════════


def test_intent_stores_no_channels_column():
    """القنوات تُشتقّ ولا تُخزَّن — نسخةٌ ثالثة تنحرف بلا قارئ يحتاجها."""
    names = {f.name for f in NotificationEnqueueIntent._meta.get_fields()}
    assert "channels" not in names


def test_enqueue_state_is_the_only_writer_of_the_enqueue_lease():
    """حقول الاستئجار لا تُكتب إلّا في `notifications/enqueue_state.py`."""
    import pathlib

    root = pathlib.Path(hub.__file__).parent
    owner = root / "enqueue_state.py"
    offenders = []

    for path in root.rglob("*.py"):
        if path == owner or "migrations" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "enqueue_token=" in text or "enqueue_expires_at=" in text:
            offenders.append(path.name)

    assert offenders == [], f"كتابة استئجار الطبر خارج مالكها: {offenders}"


def test_enqueue_intent_now_takes_identifiers_only():
    """توقيعُ الطبر نفسه يمنع تمرير كائنات حيّة أو نصّ الرسالة."""
    params = list(inspect.signature(hub._enqueue_intent_now).parameters)
    assert params == ["intent_id", "school_id"]
