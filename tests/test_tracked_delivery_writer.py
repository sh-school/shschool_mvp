"""
tests/test_tracked_delivery_writer.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-2B] أول كاتب حقيقي لـ`NotificationDispatch` و`NotificationDelivery`.

خلف راية مُطفأة افتراضياً وفي الإنتاج، وفي نطاق `NotificationHub` وحده — منتجا
Push المباشران ما زالا legacy، ولهذا يُسمّي اسمُ الراية الـHub ولا يدّعي تغطية
النظام كلّه.

ودمج الكاتب ليس تفعيله: آلة الحالات في B4-3 والمصالِح في B4-4، فتشغيلُه اليوم
يُنتج تسليمات قد تبقى `pending` بعد وصول الرسالة ولا أحد يلتقطها.
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import override_settings

from notifications.hub import NotificationHub
from notifications.models import (
    InAppNotification,
    NotificationDelivery,
    NotificationDispatch,
    UserNotificationPreference,
)
from tests.conftest import SchoolFactory, UserFactory

TRACKED = override_settings(NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED=True)


class _SentinelError(Exception):
    """يُجهض المعاملة بلا أن يختلط بخطأ حقيقي."""


def _abort_the_business_transaction():
    raise _SentinelError


@pytest.fixture
def queued():
    with patch("notifications.tasks.hub_send_notification_task.delay") as mock:
        yield mock


def _reachable_user(**overrides):
    """مستلم يملك بريداً وهاتفاً — كل القنوات قابلة له."""
    values = {"email": "p@example.com", "phone": "+97455555555"}
    values.update(overrides)
    return UserFactory(**values)


def _dispatch(school, recipients, event_type="behavior_l3"):
    """`behavior_l3` يطلب القنوات الخارجية الأربع كلّها."""
    return NotificationHub.dispatch(
        event_type=event_type,
        school=school,
        recipients=recipients,
        title="عنوان",
        body="نصّ",
    )


def _channels_for(user):
    return set(
        NotificationDelivery.objects.filter(recipient=user).values_list("channel", flat=True)
    )


# ══════════════════════════════════════════════════════════════════
# الراية مُطفأة — لا شيء يتغيّر
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_nothing_is_written_while_the_flag_is_off(queued, django_capture_on_commit_callbacks):
    """[B4-2B] الافتراضي: الخطّ خامد كما تركته B4-0."""
    school = SchoolFactory()

    with django_capture_on_commit_callbacks(execute=True):
        _dispatch(school, [_reachable_user()])

    assert NotificationDispatch.objects.count() == 0
    assert NotificationDelivery.objects.count() == 0
    assert queued.call_args.kwargs["dispatch_id"] is None


@pytest.mark.django_db
def test_the_flag_is_off_by_default():
    """راية تُشحن مُشعَلة ليست راية."""
    from django.conf import settings

    assert settings.NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED is False


@pytest.mark.django_db
def test_the_legacy_fallback_still_runs_when_the_broker_fails(django_capture_on_commit_callbacks):
    """المسار القديم يحتفظ بارتداده المتزامن — لا شيء يتتبّعه، فالإتاحة أولى."""
    school = SchoolFactory()

    with (
        patch(
            "notifications.tasks.hub_send_notification_task.delay",
            side_effect=RuntimeError("broker down"),
        ),
        patch("notifications.hub._send_sync") as sync,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            _dispatch(school, [_reachable_user()])

    assert sync.called


@pytest.mark.django_db(transaction=True)
def test_the_flag_off_path_registers_between_recipients_not_after_them(queued):
    """
    [B4-2B] الراية المُطفأة لا يُلاحَظ لها أثر — ولا حتى في الترتيب.

    الصيغة الأولى لفّت حلقة المستلمين كلّها بـ`transaction.atomic()` مهما كانت
    الراية، فصار التسجيل يُنتظر إلى نهاية النداء بدل أن يُنفَّذ فور معالجة كل
    مستلم خارج أي معاملة. هذا تغييرٌ في سلوك قائم لا في خطٍّ جديد.

    والقياس هنا هو ما تراه القاعدة لحظة أول خروج: مستلم واحد مُعالَج، لا
    الاثنان.
    """
    school = SchoolFactory()
    recipients = [_reachable_user(), _reachable_user(email="q@example.com")]

    seen = []
    queued.side_effect = lambda **kwargs: seen.append(InAppNotification.objects.count())

    _dispatch(school, recipients)

    assert len(seen) == 2, "لم يخرج نداء لكل مستلم"
    assert seen[0] == 1, "انتظر التسجيلُ نهاية النداء بدل أن يقع بين المستلمين"
    assert seen[1] == 2


@pytest.mark.django_db(transaction=True)
def test_the_flag_off_path_keeps_an_earlier_recipient_when_a_later_one_fails(queued):
    """
    [B4-2B] ولا يُسقط فشلُ مستلم أثرَ من سبقه.

    المعاملة التي أضافتها الصيغة الأولى كانت تجعل إشعارات المنصّة لعدّة
    مستلمين وحدةً واحدة، فيُلغي خطأٌ في الأخير إشعارَ الأول — وهو سلوك لم يكن
    قائماً ولم يطلبه أحد.
    """
    school = SchoolFactory()
    first, second = _reachable_user(), _reachable_user(email="q@example.com")

    def _fail_for_the_second(user, notif):
        if user.id == second.id:
            raise _SentinelError

    with patch("notifications.hub._push_websocket", side_effect=_fail_for_the_second):
        with pytest.raises(_SentinelError):
            _dispatch(school, [first, second])

    # الصفّان مكتوبان قبل نداء الـWebSocket، وبلا معاملة يلتزم كلٌّ منهما فور
    # كتابته. فالمنتظَر أن ينجو الاثنان — وتحت الصيغة التي لفّت الحلقة بمعاملة
    # كان الفشل الأخير يُلغيهما معاً.
    assert InAppNotification.objects.filter(
        user=first
    ).exists(), "تراجع إشعار مستلم سابق بسبب فشل مستلم لاحق"
    assert InAppNotification.objects.filter(
        user=second
    ).exists(), "تراجع صفٌّ كُتب قبل الفشل — لا معاملة هنا تُبرّر ذلك"


# ══════════════════════════════════════════════════════════════════
# الراية مُشعَلة — الواقعة والتسليمات
# ══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db
def test_one_hub_call_writes_one_dispatch_for_all_recipients(queued):
    """
    [B4-2B] واقعة واحدة للنداء لا واحدة لكل مستلم.

    `dispatch` نداءٌ يمثّل حدثاً واحداً بلغ عدّة أشخاص؛ تمييز المستلمين في
    التسليم لا في الواقعة.
    """
    school = SchoolFactory()
    first, second = _reachable_user(), _reachable_user(email="q@example.com")

    _dispatch(school, [first, second])

    assert NotificationDispatch.objects.count() == 1

    dispatch = NotificationDispatch.objects.get()
    assert dispatch.deliveries.filter(recipient=first).exists()
    assert dispatch.deliveries.filter(recipient=second).exists()


@TRACKED
@pytest.mark.django_db
def test_one_delivery_per_recipient_and_deliverable_channel(queued):
    """تسليم لكل (مستلم، قناة قابلة للتسليم) — لا أكثر ولا أقل."""
    school = SchoolFactory()
    user = _reachable_user()

    _dispatch(school, [user])

    assert _channels_for(user) == {"email", "sms", "whatsapp", "push"}
    assert NotificationDelivery.objects.filter(recipient=user).count() == 4


@TRACKED
@pytest.mark.django_db
def test_a_user_without_an_email_gets_no_email_delivery(queued):
    """القناة التي لا عنوان لها ليست نيّة تسليم."""
    school = SchoolFactory()
    user = _reachable_user(email="")

    _dispatch(school, [user])

    assert "email" not in _channels_for(user)
    assert {"sms", "whatsapp", "push"} <= _channels_for(user)


@TRACKED
@pytest.mark.django_db
def test_a_user_without_a_phone_gets_no_sms_or_whatsapp_delivery(queued):
    school = SchoolFactory()
    user = _reachable_user(phone="")

    _dispatch(school, [user])

    assert _channels_for(user) == {"email", "push"}


@TRACKED
@pytest.mark.django_db
def test_push_needs_no_subscription_at_write_time(queued):
    """
    [B4-2B] Push قابلة للتسليم بمجرّد طلبها.

    العامل نفسه يقرّر لاحقاً `no_subscriptions`. اشتراط الاشتراك هنا كان
    تغييراً في الدلالة لا توحيداً لها — ولأن العامل يفشل مغلقاً عند نقص تسليم،
    كان سيمنع Push من الخروج أصلاً.
    """
    school = SchoolFactory()
    user = _reachable_user()

    _dispatch(school, [user])

    assert "push" in _channels_for(user)


@TRACKED
@pytest.mark.django_db
def test_quiet_hours_leave_a_dispatch_with_no_deliveries(queued):
    """
    [B4-2B] الواقعة تصف الحدث لا الطابور.

    ساعات الهدوء تمنع الخروج الخارجي، فلا تسليم — لكن الحدث وقع وبلغ المستلم
    على المنصّة، فالواقعة تُسجَّل.
    """
    from datetime import time

    school = SchoolFactory()
    user = _reachable_user()
    UserNotificationPreference.objects.create(
        user=user, quiet_hours_start=time(0, 0), quiet_hours_end=time(23, 59)
    )

    _dispatch(school, [user])

    assert NotificationDispatch.objects.count() == 1
    assert NotificationDelivery.objects.count() == 0
    assert not queued.called


@TRACKED
@pytest.mark.django_db
def test_no_recipients_writes_no_dispatch(queued):
    """لا مستلم ⇒ لا واقعة. إشعارٌ لا يخصّ أحداً ليس حدثاً."""
    school = SchoolFactory()

    _dispatch(school, [])

    assert NotificationDispatch.objects.count() == 0


@TRACKED
@pytest.mark.django_db
def test_a_delivery_carries_its_dispatch_school(queued):
    """المفتاح المركّب في B4-0 يفرضه، وهذا يُثبت أن الكاتب لا يخالفه."""
    school = SchoolFactory()

    _dispatch(school, [_reachable_user()])

    dispatch = NotificationDispatch.objects.get()
    assert set(dispatch.deliveries.values_list("school_id", flat=True)) == {school.id}


# ══════════════════════════════════════════════════════════════════
# الترتيب — كل التسليمات قبل أي تسجيل
# ══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db
def test_every_delivery_exists_before_the_first_callback_is_registered():
    """
    [B4-2B] المرحلتان — وهذا هو الثابت الذي يجعلهما أكثر من ترتيب.

    العامل يفشل مغلقاً إن نقص تسليم لقناة طُلبت. تسجيلُ نداء قبل اكتمال صفوفه
    يعني عقداً يتّكئ على أن الـcallback لن يُنفَّذ قبل الالتزام — صحيحٌ اليوم
    وهشٌّ غداً.

    [B4-PRE4] المُسجِّل في المسار المتتبَّع صار `_enqueue_intent_after_commit`،
    فالحارس يتبع المُسجِّل الجديد. الثابت لم يتغيّر — تغيّر من يُسجّل.
    """
    school = SchoolFactory()
    recipients = [_reachable_user(), _reachable_user(email="q@example.com")]

    seen = []
    real = NotificationHub.dispatch.__globals__["_enqueue_intent_after_commit"]

    def _spy(*args, **kwargs):
        seen.append(NotificationDelivery.objects.count())
        return real(*args, **kwargs)

    with patch("notifications.hub._enqueue_intent_after_commit", _spy):
        _dispatch(school, recipients)

    total = NotificationDelivery.objects.count()

    assert total == 8, "المهيّأ للاختبار تغيّر — أربع قنوات لمستلمين"
    assert seen, "لم يُسجَّل أي نداء"
    assert seen[0] == total, "سُجِّل نداء قبل اكتمال صفوف التسليم"


# ══════════════════════════════════════════════════════════════════
# السلك والالتزام
# ══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db
def test_the_callback_carries_the_dispatch_id(queued, django_capture_on_commit_callbacks):
    """بعد الالتزام يحمل النداء هويّة الواقعة — وهو ما ينتظره العامل منذ B4-1."""
    school = SchoolFactory()

    with django_capture_on_commit_callbacks(execute=True):
        _dispatch(school, [_reachable_user()])

    dispatch = NotificationDispatch.objects.get()
    assert queued.call_args.kwargs["dispatch_id"] == str(dispatch.id)


@TRACKED
@pytest.mark.django_db(transaction=True)
def test_a_rollback_leaves_no_dispatch_and_no_delivery(queued):
    """[B4-2B] الواقعة والتسليمات كتابةُ قاعدة — تتراجع مع ما تراجع."""
    school = SchoolFactory()

    with patch("notifications.hub._send_sync") as sync:
        with pytest.raises(_SentinelError), transaction.atomic():
            _dispatch(school, [_reachable_user()])
            assert NotificationDispatch.objects.count() == 1
            _abort_the_business_transaction()

    assert NotificationDispatch.objects.count() == 0
    assert NotificationDelivery.objects.count() == 0
    assert not queued.called
    assert not sync.called


# ══════════════════════════════════════════════════════════════════
# فشل الوسيط في المسار المتتبَّع
# ══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db
def test_a_tracked_broker_failure_does_not_fall_back_to_a_direct_send(
    django_capture_on_commit_callbacks,
):
    """
    [B4-2B] المتتبَّع لا يرتدّ.

    صفّ التسليم مُلتزم، فالقاعدة مصدر الحقيقة والطبر أفضل جهد. إرسالٌ متزامن
    هنا كان سيُخرج رسالةً خارج آلة الحالات: تسليمٌ يقول "معلّق" ورسالةٌ وصلت.
    """
    school = SchoolFactory()

    with (
        patch(
            "notifications.tasks.hub_send_notification_task.delay",
            side_effect=RuntimeError("broker down"),
        ),
        patch("notifications.hub._send_sync") as sync,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            _dispatch(school, [_reachable_user()])

    assert not sync.called, "ارتدّ إلى إرسال متزامن في مسار متتبَّع"

    assert NotificationDispatch.objects.count() == 1
    assert NotificationDelivery.objects.filter(status="pending").count() == 4


@TRACKED
@pytest.mark.django_db
def test_a_tracked_broker_failure_does_not_escape_the_callback(
    django_capture_on_commit_callbacks,
):
    """
    [B4-2B] ولا يُعاد رفعه.

    المعاملة التزمت فعلاً، فرفعُ الخطأ يُنتج فشلاً ظاهرياً عن عمليةٍ قبلتها
    القاعدة — فيُعيدها المستخدم ظنّاً أنها لم تقع.
    """
    school = SchoolFactory()

    with patch(
        "notifications.tasks.hub_send_notification_task.delay",
        side_effect=RuntimeError("broker down"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            _dispatch(school, [_reachable_user()])

    assert NotificationDispatch.objects.count() == 1


# ══════════════════════════════════════════════════════════════════
# مصدر واحد لمنطق القنوات
# ══════════════════════════════════════════════════════════════════


def test_the_writer_and_the_worker_share_one_channel_helper():
    """
    [B4-2B] لا نسختان تنحرفان.

    العامل يفشل مغلقاً عند نقص تسليم، فانحرافُ نسختين يظهر كإشعارٍ لا يخرج لا
    كخطأ يُقرأ. المُثبَت هنا أن كليهما يستدعي المساعد نفسه.
    """
    import inspect

    from notifications import hub, tasks

    assert "deliverable_external_channels" in inspect.getsource(hub._create_dispatch)
    assert "deliverable_external_channels" in inspect.getsource(
        tasks.hub_send_notification_task.run
    )


def test_neither_side_keeps_a_private_copy_of_the_channel_rules():
    """
    نسخةٌ ثانية تُكتب بسهولة ولا تُلاحَظ.

    الشرط المميّز — `bool(user.phone)` بجانب `whatsapp` — لا يجوز أن يظهر خارج
    المساعد المشترك.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    marker = '("whatsapp", "whatsapp" in channels'

    for module in ("notifications/hub.py", "notifications/tasks.py"):
        assert marker not in (root / module).read_text(
            encoding="utf-8"
        ), f"{module}: نسخة ثانية من منطق القنوات"

    assert marker in (root / "notifications" / "channels.py").read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# الهويّة تبقى فريدة رغم bulk_create
# ══════════════════════════════════════════════════════════════════


@TRACKED
@pytest.mark.django_db
def test_the_identity_constraint_survives_bulk_create(queued):
    """
    الكاتب يستخدم `bulk_create`، والقيد يبقى قيد قاعدة بيانات.

    B4-0 يُثبّت القيد نفسه؛ المُثبَت هنا أن مسار الكتابة الجديد يمرّ به ولا
    يلتفّ حوله.
    """
    from django.db import IntegrityError

    school = SchoolFactory()
    user = _reachable_user()

    _dispatch(school, [user])
    dispatch = NotificationDispatch.objects.get()

    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationDelivery.objects.bulk_create(
            [
                NotificationDelivery(
                    dispatch=dispatch, school=school, recipient=user, channel="email"
                )
            ]
        )
