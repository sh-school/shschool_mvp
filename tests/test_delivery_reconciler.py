"""[B4-4] المُصالِح — ما يُسترَدّ وما لا يُسترَدّ أبداً.

الحدّ الذي تحرسه هذه الاختبارات ليس عمر الصفّ بل **هل دخل عاملٌ منطقة
المزوّد**. `pending` لم يدخلها أحد فتُعاد بلا خوف؛ و`in_progress` منقضية قد
يكون المزوّد قبِل رسالتها قبل موت العامل، فإعادتها مقامرةٌ برسالة مكرّرة تصل
إلى إنسان.
"""

import inspect
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from notifications import hub, reconciler
from notifications.hub import NotificationHub
from notifications.models import (
    NotificationDelivery,
    NotificationEnqueueIntent,
)
from tests.conftest import SchoolFactory, UserFactory

TRACKED = override_settings(NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED=True)

PENDING_GRACE = 600
REQUEUE_INTERVAL = 900
RETRY_WAIT_GRACE = 1800


@pytest.fixture
def recipient(db):
    school = SchoolFactory()
    user = UserFactory(email="parent@example.com", phone="")
    return school, user


def _dispatch(school, user, event_type="plan_update"):
    return NotificationHub.dispatch(
        event_type=event_type,
        school=school,
        recipients=[user],
        title="عنوان معلّق",
        body="نصّ معلّق",
    )


@pytest.fixture
def tracked_dispatch(recipient, django_capture_on_commit_callbacks):
    """واقعةٌ متتبَّعة سقط وسيطها — تسليمٌ `pending` ونيّةٌ تحمل نصّه."""
    school, user = recipient

    with TRACKED:
        with patch(
            "notifications.tasks.hub_send_notification_task.delay",
            side_effect=OSError("broker down"),
        ):
            with django_capture_on_commit_callbacks(execute=True):
                with transaction.atomic():
                    _dispatch(school, user)

    return school, user, NotificationEnqueueIntent.objects.get(), NotificationDelivery.objects.get()


def _age(delivery, seconds, *, attempt_seconds=None):
    """يُقدّم عمر التسليم — واختيارياً عمر آخر محاولة طبر."""
    now = timezone.now()

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status_changed_at=now - timedelta(seconds=seconds)
    )

    if attempt_seconds is not None:
        NotificationEnqueueIntent.objects.filter(dispatch_id=delivery.dispatch_id).update(
            last_enqueue_attempt_at=now - timedelta(seconds=attempt_seconds)
        )


# ═══════════════════════════════════════════════════════════════════
#  الاستئجار المنقضي — إعلانٌ لا استرداد
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_expired_lease_becomes_unknown_outcome(tracked_dispatch):
    """`in_progress` انقضى استئجاره ⇒ `unknown_outcome`، لا `pending`."""
    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="in_progress",
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )

    assert reconciler.close_expired_leases(school.id) == 1

    delivery.refresh_from_db()
    assert delivery.status == "unknown_outcome"
    assert delivery.lease_token is None
    assert delivery.lease_expires_at is None


@pytest.mark.django_db(transaction=True)
def test_a_live_lease_is_never_touched(tracked_dispatch):
    """عاملٌ ما زال يملك الصفّ قد يكون في منتصف نداء المزوّد."""
    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="in_progress",
        lease_expires_at=timezone.now() + timedelta(seconds=300),
    )

    assert reconciler.close_expired_leases(school.id) == 0

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


@pytest.mark.django_db(transaction=True)
def test_unknown_outcome_is_never_requeued(tracked_dispatch):
    """النهائية هنا نهائيةُ أتمتة: لا إعادة طبر مهما طال العمر."""
    school, _, intent, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="unknown_outcome",
        status_changed_at=timezone.now() - timedelta(days=30),
    )
    NotificationEnqueueIntent.objects.filter(id=intent.id).update(last_enqueue_attempt_at=None)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        assert reconciler.requeue_stale_deliveries(school.id) == 0

    enqueue.assert_not_called()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("terminal", ["sent", "dead_lettered", "undeliverable", "unknown_outcome"])
def test_no_terminal_status_is_ever_requeued(tracked_dispatch, terminal):
    """أربع نهايات لا يلمسها المُصالِح."""
    school, _, intent, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status=terminal, status_changed_at=timezone.now() - timedelta(days=7)
    )
    NotificationEnqueueIntent.objects.filter(id=intent.id).update(last_enqueue_attempt_at=None)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        reconciler.requeue_stale_deliveries(school.id)

    enqueue.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
#  المعيار المزدوج — عمر التسليم وعمر آخر محاولة معاً
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_stale_pending_with_quiet_enqueue_is_requeued(tracked_dispatch):
    """قديمٌ وهادئ ⇒ يُعاد طبره."""
    school, _, _, delivery = tracked_dispatch
    _age(delivery, PENDING_GRACE + 60, attempt_seconds=REQUEUE_INTERVAL + 60)

    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        assert reconciler.requeue_stale_deliveries(school.id) == 1

    delay.assert_called_once()
    assert delay.call_args.kwargs["title"] == "عنوان معلّق"


@pytest.mark.django_db(transaction=True)
def test_a_recent_enqueue_attempt_blocks_requeue(tracked_dispatch):
    """قديمٌ لكنه طُبر قبل قليل — العامل قد يكون في الطريق إليه."""
    school, _, _, delivery = tracked_dispatch
    _age(delivery, PENDING_GRACE + 600, attempt_seconds=10)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        assert reconciler.requeue_stale_deliveries(school.id) == 0

    enqueue.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_a_young_delivery_is_not_requeued_even_if_never_enqueued(tracked_dispatch):
    """لم يُطبر قطّ، لكنه وُلد قبل ثوانٍ — المهلة لم تنقضِ."""
    school, _, intent, delivery = tracked_dispatch

    _age(delivery, 5)
    NotificationEnqueueIntent.objects.filter(id=intent.id).update(last_enqueue_attempt_at=None)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        assert reconciler.requeue_stale_deliveries(school.id) == 0

    enqueue.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_a_never_attempted_stale_delivery_is_requeued(tracked_dispatch):
    """`last_enqueue_attempt_at IS NULL` تستوفي شرط الهدوء."""
    school, _, intent, delivery = tracked_dispatch

    _age(delivery, PENDING_GRACE + 60)
    NotificationEnqueueIntent.objects.filter(id=intent.id).update(last_enqueue_attempt_at=None)

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        assert reconciler.requeue_stale_deliveries(school.id) == 1


# ═══════════════════════════════════════════════════════════════════
#  retry_wait اليتيمة — عتبةٌ محافظة
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_orphaned_retry_wait_is_recovered_after_the_conservative_age(tracked_dispatch):
    """العامل كتب `retry_wait` ثم مات قبل أن تبلغ إعادتُه الوسيط."""
    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(status="retry_wait")
    _age(delivery, RETRY_WAIT_GRACE + 60, attempt_seconds=REQUEUE_INTERVAL + 60)

    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        assert reconciler.requeue_stale_deliveries(school.id) == 1

    assert delay.call_args.kwargs["channels"] == ["email"]


@pytest.mark.django_db(transaction=True)
def test_retry_wait_within_the_grace_is_left_to_celery(tracked_dispatch):
    """أقدم من عتبة `pending` وأحدث من عتبتها هي — الإعادة المجدولة قد تكون قادمة."""
    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(status="retry_wait")
    _age(delivery, PENDING_GRACE + 60, attempt_seconds=REQUEUE_INTERVAL + 60)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        assert reconciler.requeue_stale_deliveries(school.id) == 0

    enqueue.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
#  السقف — القنوات القائمة حدٌّ في الاتجاهين
# ═══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_contact_removed_closes_the_pending_delivery(recipient, django_capture_on_commit_callbacks):
    """الهاتف اختفى بعد إنشاء الواقعة ⇒ تسليم SMS يصير `undeliverable`."""
    school, _ = recipient
    user = UserFactory(email="p@example.com", phone="+97455000000")

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user, event_type="behavior_l3")

    assert NotificationDelivery.objects.filter(channel="sms", status="pending").exists()

    user.phone = ""
    user.save(update_fields=["phone"])

    from notifications.tasks import hub_send_notification_task

    hub_send_notification_task(
        user_id=str(user.id),
        school_id=str(school.id),
        channels=["email", "sms", "whatsapp", "push"],
        title="عنوان",
        body="نصّ",
        event_type="behavior_l3",
        dispatch_id=str(NotificationDelivery.objects.first().dispatch_id),
    )

    assert NotificationDelivery.objects.get(channel="sms").status == "undeliverable"
    assert NotificationDelivery.objects.get(channel="whatsapp").status == "undeliverable"
    # وما بقيت له وجهة لم يُمَسّ.
    assert NotificationDelivery.objects.get(channel="email").status != "undeliverable"


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_contact_added_never_opens_a_new_channel(recipient, django_capture_on_commit_callbacks):
    """هاتفٌ أُضيف بعد الإنشاء لا يُنشئ تسليم SMS ولا يُرسله."""
    school, user = recipient

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user, event_type="behavior_l3")

    assert not NotificationDelivery.objects.filter(channel="sms").exists()

    user.phone = "+97455111111"
    user.save(update_fields=["phone"])

    intent = NotificationEnqueueIntent.objects.get()

    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        hub._enqueue_intent_now(str(intent.id), str(school.id))

    assert "sms" not in delay.call_args.kwargs["channels"]
    assert not NotificationDelivery.objects.filter(channel="sms").exists()


# ═══════════════════════════════════════════════════════════════════
#  مسح المحتوى — بعد أن ينتهي كل شيء
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("terminal", ["sent", "dead_lettered", "undeliverable", "unknown_outcome"])
def test_content_is_scrubbed_once_every_delivery_is_terminal(tracked_dispatch, terminal):
    """النصّ محفوظٌ لإعادة الطبر وحدها — فإذا لم يبقَ ما يُطابر أُزيل."""
    school, _, intent, _ = tracked_dispatch

    NotificationDelivery.objects.update(status=terminal)

    assert reconciler.scrub_completed_intents(school.id) == 1

    intent.refresh_from_db()
    assert intent.title is None
    assert intent.body is None
    assert intent.content_cleared_at is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("open_status", ["pending", "in_progress", "retry_wait"])
def test_an_open_delivery_blocks_the_scrub(tracked_dispatch, open_status):
    """ما قد يُطابر بعدُ يحتاج نصّه."""
    school, _, intent, _ = tracked_dispatch

    NotificationDelivery.objects.update(status=open_status)

    assert reconciler.scrub_completed_intents(school.id) == 0

    intent.refresh_from_db()
    assert intent.title == "عنوان معلّق"


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_one_open_delivery_among_many_blocks_the_whole_intent(
    recipient, django_capture_on_commit_callbacks
):
    """لا مسح جزئيّ: تسليمٌ واحد غير نهائيّ يحفظ النصّ كلّه."""
    school, user = recipient

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                _dispatch(school, user, event_type="behavior_l3")

    NotificationDelivery.objects.update(status="sent")
    NotificationDelivery.objects.filter(channel="push").update(status="pending")

    assert reconciler.scrub_completed_intents(school.id) == 0


@pytest.mark.django_db(transaction=True)
def test_scrubbing_is_idempotent(tracked_dispatch):
    """`content_cleared_at` يمنع المرور الثاني — ويبقى أثراً على أن محتوى كان."""
    school, _, intent, _ = tracked_dispatch

    NotificationDelivery.objects.update(status="sent")

    assert reconciler.scrub_completed_intents(school.id) == 1
    assert reconciler.scrub_completed_intents(school.id) == 0

    intent.refresh_from_db()
    assert intent.content_cleared_at is not None


@pytest.mark.django_db(transaction=True)
def test_a_scrubbed_intent_is_not_requeued_with_empty_content(tracked_dispatch):
    """الترتيب داخل `reconcile_school` يمنع هذا، والحارس يمنعه لو تغيّر الترتيب."""
    school, _, intent, delivery = tracked_dispatch

    NotificationDelivery.objects.update(status="sent")
    reconciler.scrub_completed_intents(school.id)

    _age(delivery, PENDING_GRACE + 600, attempt_seconds=REQUEUE_INTERVAL + 600)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        reconciler.requeue_stale_deliveries(school.id)

    enqueue.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
#  الحدّ المستأجَر
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_a_school_reconciles_only_its_own_rows(tracked_dispatch):
    """مدرسةٌ أخرى لا تُغلق ولا تُعيد طبر ما ليس لها."""
    school, _, _, delivery = tracked_dispatch
    other = SchoolFactory()

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="in_progress",
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )

    assert reconciler.close_expired_leases(other.id) == 0
    assert reconciler.requeue_stale_deliveries(other.id) == 0
    assert reconciler.scrub_completed_intents(other.id) == 0

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


def test_the_reconciler_task_takes_one_school():
    """النطاق مدرسةٌ واحدة لكل استدعاء — يفرضه التوقيع لا العادة."""
    from notifications.tasks import reconcile_deliveries_task

    params = list(inspect.signature(reconcile_deliveries_task.run).parameters)
    assert params == ["school_id"]


def test_no_beat_entry_schedules_the_reconciler():
    """`BEAT_DEPLOY` غير مصرَّح به — فلا مُشغّل دوريّ للمهمّة بعد."""
    from shschool.celery import app

    scheduled = {entry.get("task") for entry in app.conf.beat_schedule.values()}
    assert "notifications.reconcile_deliveries" not in scheduled


# ═══════════════════════════════════════════════════════════════════
#  حارس الملكيّة
# ═══════════════════════════════════════════════════════════════════


def test_unknown_outcome_has_exactly_one_writer():
    """لا أحد يكتب هذه الحالة خارج `delivery_state.mark_unknown_outcome`."""
    import pathlib

    root = pathlib.Path(hub.__file__).parent
    owner = root / "delivery_state.py"
    offenders = []

    for path in root.rglob("*.py"):
        if path == owner or "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if 'status="unknown_outcome"' in text or "status='unknown_outcome'" in text:
            offenders.append(path.name)

    assert offenders == [], f"كتابة `unknown_outcome` خارج مالكها: {offenders}"


def test_unknown_outcome_is_not_worker_finalizable():
    """العامل لا يكتبها: الميت لا يُعلن موته."""
    from notifications.delivery_state import FINALIZABLE, TERMINAL

    assert "unknown_outcome" not in FINALIZABLE
    assert "unknown_outcome" in TERMINAL


def test_recoverable_and_terminal_do_not_overlap():
    """كل حالة إمّا تُسترَدّ وإمّا لا — ولا حالة في الصنفين."""
    from notifications.delivery_state import TERMINAL
    from notifications.models import NotificationDelivery

    assert set(reconciler.RECOVERABLE) & set(TERMINAL) == set()

    known = {value for value, _ in NotificationDelivery.STATUS}
    classified = set(reconciler.RECOVERABLE) | set(TERMINAL) | {"in_progress"}
    assert known == classified, f"حالة بلا تصنيف: {known ^ classified}"


# ═══════════════════════════════════════════════════════════════════
#  المانع الأول — الميزانية الدائمة
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_recovering_retry_wait_does_not_reset_the_durable_budget(tracked_dispatch):
    """كل استحواذ يستهلك محاولة — ولو جاء من رسالة Celery جديدة.

    قبل هذا العمود كانت الميزانية `request.retries` داخل الرسالة وحدها، فرسالةٌ
    ينشئها المُصالِح تبدأ من صفر. وذلك يعني أن فشلاً متكرّراً في نشر الإعادة
    يمنح دورةً كاملة كلّ مرّة: **لا حدّ للمحاولات إطلاقاً**.
    """
    from notifications.delivery_state import attempts_used, claim_delivery, finalize_delivery

    school, _, _, delivery = tracked_dispatch

    assert attempts_used(delivery.id, school.id) == 0

    # ثلاث دورات، كلٌّ منها استحواذٌ من عاملٍ في رسالة جديدة ثم `retry_wait`.
    for expected in (1, 2, 3):
        token = claim_delivery(delivery.id, school.id)
        assert token is not None
        assert attempts_used(delivery.id, school.id) == expected
        assert finalize_delivery(delivery.id, school.id, token, "retry_wait")

    # والعدّاد لم يعد إلى الصفر رغم أن كل دورة رسالةٌ مستقلّة.
    assert attempts_used(delivery.id, school.id) == 3


@pytest.mark.django_db(transaction=True)
def test_the_budget_is_enforced_even_with_no_worker_to_enforce_it(tracked_dispatch):
    """عاملٌ مات بعد `retry_wait` وقبل نشر إعادته — المُصالِح يُنهي الأمر."""
    from notifications.models import DeadLetterMessage

    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="retry_wait",
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS,
    )

    assert reconciler.close_exhausted_deliveries(school.id) == 1

    delivery.refresh_from_db()
    assert delivery.status == "dead_lettered"
    assert DeadLetterMessage.objects.filter(delivery_id=delivery.id).exists()


@pytest.mark.django_db(transaction=True)
def test_an_exhausted_delivery_is_never_requeued(tracked_dispatch):
    """المستنفدة تخرج من الأهلية — لا محاولة أخيرة بلا معنى عند المزوّد."""
    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS
    )
    _age(delivery, PENDING_GRACE + 600, attempt_seconds=REQUEUE_INTERVAL + 600)

    with patch.object(hub, "_enqueue_intent_now") as enqueue:
        assert reconciler.requeue_stale_deliveries(school.id) == 0

    enqueue.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_the_worker_decides_exhaustion_from_the_row_not_the_message(tracked_dispatch):
    """`_tracked_failure` تقرأ العدّاد الدائم لا `request.retries`.

    الرسالة الجديدة تحمل `retries = 0` دائماً، فلو بقي القرار عليها لما مات
    تسليمٌ أبداً ما دام المُصالِح يُعيد طبره.
    """
    from notifications.delivery_state import claim_delivery
    from notifications.tasks import _tracked_failure

    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS - 1
    )
    token = claim_delivery(delivery.id, school.id)  # يبلغ بها الحدّ

    task = type("_Task", (), {"request": type("_R", (), {"retries": 0})(), "max_retries": 3})()

    result = _tracked_failure(
        task,
        delivery,
        token,
        OSError("provider down"),
        kind="email",
        school_id=str(school.id),
        payload={"dispatch_id": str(delivery.dispatch_id)},
    )

    assert result == {"status": "dead_letter"}
    delivery.refresh_from_db()
    assert delivery.status == "dead_lettered"


# ═══════════════════════════════════════════════════════════════════
#  المانع الثاني — الأهلية مرتبطة بالمستلم
# ═══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_a_stale_recipient_does_not_make_a_fresh_recipient_eligible(
    recipient, django_capture_on_commit_callbacks
):
    """واقعةٌ واحدة، مستلمان: القديم لا يجرّ الحديث معه.

    الانضمام عبر `dispatch__deliveries` وحده كان يجعل تسليم «أ» القديم يُؤهّل
    نيّة «ب»، فيُطابر تسليمَ «ب» الحديث وهو في مهلته — وتسقط `PENDING_GRACE`
    عملياً في كل واقعة متعدّدة المستلمين.
    """
    school, _ = recipient
    stale_user = UserFactory(email="stale@example.com", phone="")
    fresh_user = UserFactory(email="fresh@example.com", phone="")

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                NotificationHub.dispatch(
                    event_type="plan_update",
                    school=school,
                    recipients=[stale_user, fresh_user],
                    title="عنوان مشترك",
                    body="نصّ مشترك",
                )

    assert NotificationEnqueueIntent.objects.count() == 2

    stale = NotificationDelivery.objects.get(recipient=stale_user)
    fresh = NotificationDelivery.objects.get(recipient=fresh_user)

    # «أ» قديمٌ ومستحقّ، و«ب» وُلد الآن — وكلاهما في نفس الواقعة.
    _age(stale, PENDING_GRACE + 600)
    NotificationEnqueueIntent.objects.update(last_enqueue_attempt_at=None)
    NotificationDelivery.objects.filter(id=fresh.id).update(status_changed_at=timezone.now())

    with patch("notifications.tasks.hub_send_notification_task.delay") as delay:
        assert reconciler.requeue_stale_deliveries(school.id) == 1

    # ولم يُطابر إلا «أ».
    assert delay.call_count == 1
    assert delay.call_args.kwargs["user_id"] == str(stale_user.id)


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_scrub_is_scoped_to_the_recipient_not_the_dispatch(
    recipient, django_capture_on_commit_callbacks
):
    """مستلمٌ انتهى أمرُه يُمسح محتواه ولو بقي شريكه في الواقعة مفتوحاً."""
    school, _ = recipient
    done_user = UserFactory(email="done@example.com", phone="")
    open_user = UserFactory(email="open@example.com", phone="")

    with patch("notifications.tasks.hub_send_notification_task.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                NotificationHub.dispatch(
                    event_type="plan_update",
                    school=school,
                    recipients=[done_user, open_user],
                    title="عنوان مشترك",
                    body="نصّ مشترك",
                )

    NotificationDelivery.objects.filter(recipient=done_user).update(status="sent")

    assert reconciler.scrub_completed_intents(school.id) == 1

    assert NotificationEnqueueIntent.objects.get(recipient=done_user).title is None
    assert NotificationEnqueueIntent.objects.get(recipient=open_user).title == "عنوان مشترك"


@pytest.mark.django_db(transaction=True)
def test_a_stale_broker_message_cannot_overspend_the_budget(tracked_dispatch):
    """رسالةٌ قديمة في الوسيط تصل إلى العامل مباشرةً — والاستحواذ يرفضها.

    المُصالِح يمنع **إعادة الطبر**، ولا يملك شيئاً تجاه رسالةٍ نُشرت سلفاً
    وتنتظر عاملاً. فلو لم يكن الحدّ داخل شرط الـCAS، لاستحوذت تلك الرسالة على
    صفٍّ عند حدّه وأنفقت محاولةً زائدة **عند المزوّد** قبل أن يكتشف أحدٌ شيئاً.
    """
    from notifications.delivery_state import attempts_used, claim_delivery

    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="retry_wait",
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS,
    )

    assert claim_delivery(delivery.id, school.id) is None

    delivery.refresh_from_db()
    assert delivery.status == "retry_wait"  # لم يُنقل إلى `in_progress`
    assert attempts_used(delivery.id, school.id) == settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS


@pytest.mark.django_db(transaction=True)
def test_the_last_attempt_within_budget_is_still_claimable(tracked_dispatch):
    """الحدّ سقفٌ لا يُتجاوَز، لا خصمٌ من المسموح: المحاولة الأخيرة تُنفَّذ."""
    from notifications.delivery_state import attempts_used, claim_delivery

    school, _, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS - 1
    )

    assert claim_delivery(delivery.id, school.id) is not None
    assert attempts_used(delivery.id, school.id) == settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS


@pytest.mark.django_db(transaction=True)
def test_the_provider_is_never_called_for_an_exhausted_delivery(tracked_dispatch):
    """البرهان من طرف المهمّة لا من طرف البدائيّة: لا نداء مزوّد إطلاقاً."""
    from notifications.tasks import send_email_task

    school, user, _, delivery = tracked_dispatch

    NotificationDelivery.objects.filter(id=delivery.id).update(
        status="retry_wait",
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS,
    )

    with patch("django.core.mail.send_mail") as provider:
        result = send_email_task(
            school_id=str(school.id),
            recipient_email=user.email,
            subject="عنوان",
            body_text="نصّ",
            delivery_id=str(delivery.id),
        )

    provider.assert_not_called()
    assert result["status"] == "not_claimed"
