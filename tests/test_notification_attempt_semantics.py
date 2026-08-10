"""
tests/test_notification_attempt_semantics.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-PRE1] `NotificationLog` سجلّ محاولة — على القنوات الخارجية كلّها.

الاسم يقول "سجل كل إشعار أُرسل"، لكن الدورة الفعلية في البريد وSMS دورةُ
محاولة: صفّ `pending` يُنشأ قبل نداء المزوّد ثم يُحسم `sent` أو `failed`.
وقد كان ذلك صحيحاً في هاتين القناتين وحدهما:

    WhatsApp   يكتب بعد نجاح `messages.create` فقط
               ⇒ محاولة فشلت لا تترك أثراً
               ⇒ ويُسجَّل `channel="sms"` لأن الخيار لم يكن موجوداً
    Push       لا يكتب شيئاً إطلاقاً

الاختبارات هنا **سلوكية لا نصّية**: كلٌّ منها يستبدل المزوّد بدالة تسأل
القاعدة لحظة النداء. فحصُ مصدرٍ يبحث عن `status="pending"` يمرّ لو كُتب السطر
بعد الإرسال؛ سؤالُ القاعدة **أثناء** النداء لا يمرّ إلا إذا كان الصفّ موجوداً
فعلاً قبله.

ولا `unknown` هنا. انهيارٌ بعد المزوّد وقبل الحسم يترك صفّاً `pending` عالقاً،
وهذا مقصود في هذه المرحلة: تفسيره يحتاج lease وآلة حالات لم تُبنَ بعد، وادّعاء
حلٍّ لم نصل إليه هو تحديداً ما نتجنّبه.
"""

from unittest.mock import patch

import pytest

from notifications.models import NotificationLog
from notifications.services import NotificationService
from notifications.tasks import _send_whatsapp
from tests.conftest import SchoolFactory

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════
# أدوات: التقاط ما تراه القاعدة لحظة نداء المزوّد
# ══════════════════════════════════════════════════════════════════


class _ProviderMessage:
    """ما يُعيده مزوّد Twilio — `_send_whatsapp` يقرأ منه `sid`."""

    sid = "SM-test"


class _ProviderSpy:
    """يسجّل حالة السجلّ كما تراها القاعدة **أثناء** نداء المزوّد."""

    def __init__(self, raises=None):
        self.raises = raises
        self.seen = None
        self.called = False

    def __call__(self, *args, **kwargs):
        self.called = True
        self.seen = list(
            NotificationLog.objects.values_list("channel", "status").order_by("sent_at")
        )
        if self.raises is not None:
            raise self.raises
        return _ProviderMessage()


def _only_log():
    logs = list(NotificationLog.objects.all())
    assert len(logs) == 1, f"توقّعنا سجلّاً واحداً، وُجد {len(logs)}"
    return logs[0]


# ══════════════════════════════════════════════════════════════════
# البريد
# ══════════════════════════════════════════════════════════════════


def test_email_log_exists_before_the_provider_is_called():
    """الصفّ موجود `pending` لحظة النداء — لا بعده."""
    school = SchoolFactory()
    spy = _ProviderSpy()

    with patch("django.core.mail.send_mail", spy):
        NotificationService.send_email(school, "parent@example.com", "عنوان", "نصّ")

    assert spy.called
    assert spy.seen == [("email", "pending")]


def test_email_success_resolves_to_sent():
    school = SchoolFactory()

    with patch("django.core.mail.send_mail", _ProviderSpy()):
        ok, error = NotificationService.send_email(school, "p@example.com", "عنوان", "نصّ")

    assert ok is True and error is None
    log = _only_log()
    assert log.channel == "email"
    assert log.status == "sent"


def test_email_provider_failure_resolves_to_failed():
    school = SchoolFactory()
    spy = _ProviderSpy(raises=OSError("smtp unreachable"))

    with patch("django.core.mail.send_mail", spy):
        ok, error = NotificationService.send_email(school, "p@example.com", "عنوان", "نصّ")

    assert ok is False and error
    log = _only_log()
    assert log.channel == "email"
    assert log.status == "failed"
    assert log.error_msg


# ══════════════════════════════════════════════════════════════════
# SMS
# ══════════════════════════════════════════════════════════════════


def _sms_settings(school, **overrides):
    from notifications.models import NotificationSettings

    values = {
        "sms_enabled": True,
        "sms_provider": "twilio",
        "sms_from_number": "+97400000000",
        "twilio_account_sid": "AC-test",
        "twilio_auth_token": "token",
    }
    values.update(overrides)
    return NotificationSettings.objects.create(school=school, **values)


class _FakeTwilioClient:
    """يقف مقام `twilio.rest.Client` ويمرّر النداء إلى جاسوس."""

    spy = None

    def __init__(self, *args, **kwargs):
        self.messages = self

    def create(self, **kwargs):
        return type(self).spy(**kwargs)


def _with_twilio(spy):
    _FakeTwilioClient.spy = spy
    return patch("twilio.rest.Client", _FakeTwilioClient)


def test_sms_log_exists_before_the_provider_is_called():
    school = SchoolFactory()
    _sms_settings(school)
    spy = _ProviderSpy()

    with _with_twilio(spy):
        NotificationService.send_sms(school, "+97455555555", "نصّ")

    assert spy.called
    assert spy.seen == [("sms", "pending")]


def test_sms_success_resolves_to_sent():
    school = SchoolFactory()
    _sms_settings(school)

    with _with_twilio(_ProviderSpy()):
        ok, error = NotificationService.send_sms(school, "+97455555555", "نصّ")

    assert ok is True and error is None
    log = _only_log()
    assert log.channel == "sms"
    assert log.status == "sent"


def test_sms_provider_failure_resolves_to_failed():
    school = SchoolFactory()
    _sms_settings(school)
    spy = _ProviderSpy(raises=RuntimeError("twilio rejected"))

    with _with_twilio(spy):
        ok, error = NotificationService.send_sms(school, "+97455555555", "نصّ")

    assert ok is False and error
    log = _only_log()
    assert log.channel == "sms"
    assert log.status == "failed"


# ══════════════════════════════════════════════════════════════════
# WhatsApp — القناة التي كانت تُسجّل نجاحها وحده
# ══════════════════════════════════════════════════════════════════


def _whatsapp_settings(school):
    from notifications.models import NotificationSettings

    return NotificationSettings.objects.create(
        school=school,
        sms_from_number="+97400000000",
        twilio_account_sid="AC-test",
        twilio_auth_token="token",
    )


def test_whatsapp_log_exists_before_the_provider_is_called():
    """
    [B4-PRE1] هذا هو التغيير الجوهري في هذه القناة.

    قبله كان الصفّ يُكتب بعد عودة `messages.create` بنجاح، فلا وجود له لحظة
    النداء — والجاسوس كان سيرى قائمة فارغة.
    """
    school = SchoolFactory()
    _whatsapp_settings(school)
    spy = _ProviderSpy()

    with _with_twilio(spy):
        _send_whatsapp(school, "+97455555555", "عنوان", "نصّ")

    assert spy.called
    assert spy.seen == [("whatsapp", "pending")]


def test_whatsapp_success_resolves_to_sent():
    school = SchoolFactory()
    _whatsapp_settings(school)

    with _with_twilio(_ProviderSpy()):
        _send_whatsapp(school, "+97455555555", "عنوان", "نصّ")

    log = _only_log()
    assert log.channel == "whatsapp"
    assert log.status == "sent"


def test_whatsapp_provider_failure_leaves_a_failed_row():
    """
    [B4-PRE1] محاولة فاشلة تترك أثراً.

    كانت لا تترك شيئاً إطلاقاً: سجلّ WhatsApp الذي يبدو نظيفاً دائماً كان
    نظيفاً لأنه لا يسجّل إلا النجاح.
    """
    school = SchoolFactory()
    _whatsapp_settings(school)
    spy = _ProviderSpy(raises=ValueError("twilio blew up"))

    with _with_twilio(spy), pytest.raises(RuntimeError):
        _send_whatsapp(school, "+97455555555", "عنوان", "نصّ")

    log = _only_log()
    assert log.channel == "whatsapp"
    assert log.status == "failed"
    assert log.error_msg


def test_whatsapp_configuration_failure_leaves_a_failed_row():
    """رقم غير مضبوط سببُ عدم وصول رسالة — تماماً كرفض المزوّد."""
    school = SchoolFactory()

    with pytest.raises(RuntimeError):
        _send_whatsapp(school, "+97455555555", "عنوان", "نصّ")

    log = _only_log()
    assert log.channel == "whatsapp"
    assert log.status == "failed"


def test_whatsapp_is_never_recorded_as_sms():
    """
    [B4-PRE1] انحدار: القناة كانت تُسجَّل `sms` مع تعليق يعترف بذلك.

    التعليق في الكود لا يصل إلى من يقرأ الجدول ولا إلى من يحسب الإحصاءات.
    """
    school = SchoolFactory()
    _whatsapp_settings(school)

    with _with_twilio(_ProviderSpy()):
        _send_whatsapp(school, "+97455555555", "عنوان", "نصّ")

    spy = _ProviderSpy(raises=ValueError("boom"))
    with _with_twilio(spy), pytest.raises(RuntimeError):
        _send_whatsapp(school, "+97466666666", "عنوان", "نصّ")

    channels = set(NotificationLog.objects.values_list("channel", flat=True))
    assert channels == {"whatsapp"}
    assert not NotificationLog.objects.filter(channel="sms").exists()


def test_whatsapp_error_text_carries_no_phone_number():
    """[P2-B2] نصّ استثناء المزوّد يحمل عادةً الرقم الذي فشل."""
    school = SchoolFactory()
    _whatsapp_settings(school)
    spy = _ProviderSpy(raises=ValueError("failed to deliver to +97455555555"))

    with _with_twilio(spy), pytest.raises(RuntimeError):
        _send_whatsapp(school, "+97455555555", "عنوان", "نصّ")

    assert "97455555555" not in _only_log().error_msg


# ══════════════════════════════════════════════════════════════════
# Push — محاولة لكل نداء مزوّد
# ══════════════════════════════════════════════════════════════════
#
# هذه القناة وحدها تُنادي المزوّد أكثر من مرّة في المهمّة الواحدة: مرّة لكل
# اشتراك فعّال. ولذلك وحدة المحاولة هنا الاشتراك لا المهمّة — وهو ما يجعل
# النجاح الجزئي قابلاً للتمثيل بلا اختراع حالة رابعة.


def _subscription(school, user, endpoint):
    from notifications.models import PushSubscription

    return PushSubscription.objects.create(
        school=school,
        user=user,
        endpoint=endpoint,
        p256dh="p256dh-key",
        auth="auth-secret",
    )


class _WebPushSpy:
    """يقف مقام `webpush`، ويُقرّر لكل اشتراك على حدة."""

    def __init__(self, outcomes):
        #: endpoint -> None للنجاح، أو استثناء يُرفع
        self.outcomes = outcomes
        self.seen_at_call = []

    def __call__(self, subscription_info, **kwargs):
        endpoint = subscription_info["endpoint"]
        self.seen_at_call.append(set(NotificationLog.objects.values_list("recipient", "status")))

        outcome = self.outcomes[endpoint]
        if outcome is not None:
            raise outcome


class _FakeWebPushError(Exception):
    """`WebPushException` بديلة — الكود يفحص نصّها لا نوعها."""


def _push_failure(message="push provider refused"):
    return _FakeWebPushError(message)


def _push_module(spy):
    """يستبدل رمزَي `pywebpush` اللذين تستوردهما المهمّة."""
    import sys
    import types

    module = types.ModuleType("pywebpush")
    module.webpush = spy
    module.WebPushException = _FakeWebPushError
    return patch.dict(sys.modules, {"pywebpush": module})


def _run_push(user, school):
    from notifications.tasks import send_push_task

    return send_push_task(str(user.id), "عنوان", "نصّ", "/parents/", school_id=str(school.id))


def _push_logs():
    return dict(NotificationLog.objects.values_list("recipient", "status"))


def test_push_single_subscription_success_writes_one_sent_attempt():
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    sub = _subscription(school, user, "https://push.example/a")
    spy = _WebPushSpy({"https://push.example/a": None})

    with _push_module(spy):
        result = _run_push(user, school)

    assert result["sent"] == 1
    assert _push_logs() == {f"push:{sub.id}": "sent"}


def test_push_log_exists_pending_before_the_provider_is_called():
    """الصفّ موجود لحظة نداء `webpush` — لا بعد عودته."""
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    sub = _subscription(school, user, "https://push.example/a")
    spy = _WebPushSpy({"https://push.example/a": None})

    with _push_module(spy):
        _run_push(user, school)

    assert spy.seen_at_call == [{(f"push:{sub.id}", "pending")}]


def test_push_sole_subscription_failing_still_leaves_a_failed_attempt():
    """
    اشتراك وحيد فشل ⇒ `sent == 0` ⇒ المهمّة ترفع وتُعاد.

    هذا سلوك B3 ولم يتغيّر: إذا لم ينجح شيء فالإعادة لا تُكرّر تسليماً. ما
    يضيفه PRE1 أن المحاولة تُسجَّل قبل ذلك، فالإعادة لا تمحو أثر الأولى.
    """
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    sub = _subscription(school, user, "https://push.example/a")
    spy = _WebPushSpy({"https://push.example/a": _push_failure()})

    with _push_module(spy), pytest.raises(RuntimeError):
        _run_push(user, school)

    assert spy.seen_at_call == [{(f"push:{sub.id}", "pending")}]
    assert _push_logs() == {f"push:{sub.id}": "failed"}


def test_push_two_subscriptions_both_succeed_write_two_attempts():
    """محاولة لكل جهاز — لا صفّ واحد يلخّص الاثنين."""
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    first = _subscription(school, user, "https://push.example/a")
    second = _subscription(school, user, "https://push.example/b")
    spy = _WebPushSpy({"https://push.example/a": None, "https://push.example/b": None})

    with _push_module(spy):
        result = _run_push(user, school)

    assert result["sent"] == 2
    assert _push_logs() == {
        f"push:{first.id}": "sent",
        f"push:{second.id}": "sent",
    }


def test_push_partial_success_is_recorded_as_it_happened():
    """
    [B4-PRE1] هذا هو سبب اختيار الاشتراك وحدةً للمحاولة.

    جهاز وصلته الرسالة وآخر لم تصله. صفٌّ واحد كان سيقول "أُرسل" فيُخفي
    الثاني، أو "فشل" فينفي الأول. صفّان يقولان ما حدث بلا حالة رابعة.

    وسلوك المهمّة لم يتغيّر: النجاح الجزئي يبقى نجاحاً كما قرّرنا في B3 —
    PRE1 يوحّد الرصد ولا يُعيد فتح قرار الإعادة.
    """
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    delivered = _subscription(school, user, "https://push.example/a")
    refused = _subscription(school, user, "https://push.example/b")
    spy = _WebPushSpy(
        {
            "https://push.example/a": None,
            "https://push.example/b": _push_failure(),
        }
    )

    with _push_module(spy):
        result = _run_push(user, school)

    assert result["sent"] == 1
    assert result["transient"] == 1
    assert _push_logs() == {
        f"push:{delivered.id}": "sent",
        f"push:{refused.id}": "failed",
    }


@pytest.mark.parametrize("code", ["410", "404"])
def test_push_gone_subscription_leaves_a_failed_attempt_and_is_deactivated(code):
    """
    الاشتراك يُعطَّل، والمحاولة تبقى مسجّلة.

    تعطيل الاشتراك إجراء على المستقبل؛ محو أثر المحاولة يجعل الماضي يبدو
    كأن شيئاً لم يُحاوَل.
    """
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    sub = _subscription(school, user, "https://push.example/a")
    spy = _WebPushSpy({"https://push.example/a": _push_failure(f"gone {code}")})

    with _push_module(spy):
        result = _run_push(user, school)

    assert result["invalidated"] == 1
    assert result["transient"] == 0
    assert _push_logs() == {f"push:{sub.id}": "failed"}

    sub.refresh_from_db()
    assert sub.is_active is False


def test_push_without_subscriptions_writes_no_attempt():
    """لا نداء مزوّد ⇒ لا محاولة. صفٌّ هنا يصف حدثاً لم يقع."""
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    spy = _WebPushSpy({})

    with _push_module(spy):
        result = _run_push(user, school)

    assert result["status"] == "no_subscriptions"
    assert NotificationLog.objects.count() == 0
    assert spy.seen_at_call == []


def test_push_attempt_never_stores_the_endpoint():
    """
    [P2-B2] الـendpoint عنوان جهاز — لا في `recipient` ولا في `error_msg`.

    ونصّ `WebPushException` يحمله عادةً، فالتنقية ليست احتياطاً نظرياً.
    """
    from tests.conftest import UserFactory

    school = SchoolFactory()
    user = UserFactory()
    endpoint = "https://push.example/device-abc123"
    _subscription(school, user, endpoint)
    spy = _WebPushSpy({endpoint: _push_failure(f"delivery refused for {endpoint}")})

    # اشتراك وحيد فشل ⇒ المهمّة ترفع (سلوك B3)، والصفّ مكتوب قبل ذلك.
    with _push_module(spy), pytest.raises(RuntimeError):
        _run_push(user, school)

    log = _only_log()
    assert "push.example" not in log.recipient
    assert "device-abc123" not in log.recipient
    assert "device-abc123" not in log.error_msg


# ══════════════════════════════════════════════════════════════════
# النموذج
# ══════════════════════════════════════════════════════════════════


def test_every_external_channel_is_a_valid_choice():
    """قناة تُرسل ولا يمثّلها العمود تُسجَّل تحت اسم قناة أخرى."""
    codes = {code for code, _ in NotificationLog.CHANNEL}

    assert codes == {"email", "sms", "whatsapp", "push"}


def test_in_app_is_not_a_delivery_channel():
    """`InAppNotification` هي الكيان المُرسَل نفسه لا تسليماً خارجياً له مزوّد."""
    codes = {code for code, _ in NotificationLog.CHANNEL}

    assert "in_app" not in codes


def test_statuses_stay_at_three():
    """
    [B4-PRE1] لا `unknown` بعد.

    خيارٌ بلا انتقال يُنتجه يخلق دلالة ميتة. `UNKNOWN_OUTCOME` يصير حقيقة
    قابلة للتسجيل حين تدخل آلة الحالات والـlease في B4-3، لا قبلها.
    """
    codes = {code for code, _ in NotificationLog.STATUS}

    assert codes == {"pending", "sent", "failed"}
