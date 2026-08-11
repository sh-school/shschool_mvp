"""
tests/test_external_dispatch_after_commit.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-PRE2] ما يخرج إلى مزوّد خارجي لا يقع قبل أن يُصبح الحدث نهائياً.

جردُ B4-2A وجد عشرة مواضع تنادي الـHub من **داخل** `@transaction.atomic`:
تسجيل الغياب، وتبادل الحصص، والحصص التعويضية، ودورة حياة الزيارة الصفّية. وكان
الطبر يقع داخل تلك المعاملة، فإن تراجعت بقي في الطابور عملٌ يشير إلى صفوف لم
تُكتب.

ومع `CELERY_TASK_ALWAYS_EAGER` — وهو وضع الإنتاج اليوم — لا يبقى الأمر عند
الطابور: المزوّد يُنادى فوراً، فيصل البريد أو الرسالة عن حدث تراجع بعد ثوانٍ.
ورسالةٌ وصلت لا تُسحب.

هذا ليس تمهيداً لـB4 بل إصلاحُ عطب قائم. ولا شيء هنا يُنشئ `Dispatch` ولا
`Delivery`، ولا يتغيّر سلوك الإرسال نفسه — يتغيّر توقيته وحده.

`InAppNotification` تبقى داخل المعاملة عمداً: هي كتابةُ قاعدة، فمن الصواب أن
تتراجع مع ما تراجع. المؤجَّل هو الأثر الخارجي الذي لا رجعة فيه.
"""

from unittest.mock import patch

import pytest
from django.db import transaction

from notifications.hub import NotificationHub
from notifications.models import InAppNotification
from tests.conftest import SchoolFactory, UserFactory


class _SentinelError(Exception):
    """يُجهض المعاملة بلا أن يختلط بخطأ حقيقي."""


def _abort_the_business_transaction():
    """يُحاكي فشلاً يقع بعد الإشعار ويُجهض الطفرة.

    الرفع من دالّة لا من جسم `with` مباشرةً: محلّلات السكون لا تعرف أن
    `pytest.raises` يبتلع الاستثناء، فتُبلّغ عن التأكيدات التالية كأنها غير
    قابلة للبلوغ. المعنى واحد — استثناءٌ حقيقيّ يُنهي المعاملة — والشكل يُبقي
    التقرير صادقاً بدل أن يُسكَت.
    """
    raise _SentinelError


def _dispatch(school, recipients, event_type="absence"):
    return NotificationHub.dispatch(
        event_type=event_type,
        school=school,
        recipients=recipients,
        title="عنوان",
        body="نصّ",
    )


@pytest.fixture
def queued():
    """يعترض الطبر وحده — بقيّة الـHub تعمل كما هي."""
    with patch("notifications.tasks.hub_send_notification_task.delay") as mock:
        yield mock


# ══════════════════════════════════════════════════════════════════
# داخل معاملة
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_nothing_is_queued_before_commit(queued, django_capture_on_commit_callbacks):
    """
    [B4-PRE2] العطب نفسه: الطبر كان يقع داخل المعاملة.

    الاعتراض هنا يلتقط ما سُجِّل بلا تنفيذه، فيُظهر الحالة لحظة ما قبل
    الالتزام: نيّة مسجّلة، وصفر خروج.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        _dispatch(school, [user])

    assert not queued.called
    assert len(callbacks) == 1


@pytest.mark.django_db
def test_it_is_queued_exactly_once_after_commit(queued, django_capture_on_commit_callbacks):
    """وبعد الالتزام يخرج مرّة واحدة — لا صفراً ولا مرّتين."""
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with django_capture_on_commit_callbacks(execute=True):
        _dispatch(school, [user])

    assert queued.call_count == 1


@pytest.mark.django_db
def test_one_callback_per_recipient(queued, django_capture_on_commit_callbacks):
    """
    التأجيل لا يجمع المستلمين في نداء واحد.

    الـHub يمرّ على كل مستلم على حدة، فلكلٍّ نيّة خروج مستقلّة — ودمجها كان
    سيجعل فشل أحدها فشل الجميع.
    """
    school = SchoolFactory()
    recipients = [UserFactory(email="a@example.com"), UserFactory(email="b@example.com")]

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        _dispatch(school, recipients)

    assert len(callbacks) == 2

    with django_capture_on_commit_callbacks(execute=True):
        _dispatch(school, recipients)

    assert queued.call_count == 2


# ══════════════════════════════════════════════════════════════════
# التراجع — وهذا هو الاختبار الذي يصف العطب
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_a_rollback_sends_nothing(queued):
    """
    [B4-PRE2] معاملة تتراجع لا تُخرج شيئاً — لا إلى الطابور ولا إلى مزوّد.

    هذا هو الشكل الذي يقع فعلاً في الإنتاج: طفرةُ أعمال، ثم إشعار، ثم فشل
    يُجهض الطفرة. قبل هذا التغيير كان البريد قد خرج.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with patch("notifications.hub._send_sync") as sync, pytest.raises(_SentinelError):
        with transaction.atomic():
            _dispatch(school, [user])
            _abort_the_business_transaction()

    assert not queued.called, "خرج إلى الطابور رغم التراجع"
    assert not sync.called, "أرسل مباشرةً رغم التراجع"


@pytest.mark.django_db(transaction=True)
def test_a_rollback_takes_the_in_app_notification_with_it(queued):
    """
    [B4-PRE2] إشعار المنصّة كتابةُ قاعدة، فيتراجع مع ما تراجع.

    وهذا ليس أثراً جانبياً بل الترتيب المقصود: ما يمكن التراجع عنه يبقى داخل
    المعاملة، وما لا يمكن يُؤجَّل إلى ما بعدها.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with pytest.raises(_SentinelError), transaction.atomic():
        _dispatch(school, [user])
        assert InAppNotification.objects.filter(user=user).exists()
        _abort_the_business_transaction()

    assert not InAppNotification.objects.filter(user=user).exists()


# ══════════════════════════════════════════════════════════════════
# خارج معاملة — التوافق مع المسار القديم
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_outside_a_transaction_it_runs_immediately(queued):
    """
    مستدعٍ بلا معاملة يسلك كما كان.

    Django يُنفّذ الـcallback فوراً حين لا توجد معاملة معلّقة، فالمسارات غير
    المعامليّة — وهي سبعة في الجرد — لا تنتظر شيئاً.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    _dispatch(school, [user])

    assert queued.call_count == 1


# ══════════════════════════════════════════════════════════════════
# الارتداد القديم — باقٍ، لكن بعد الالتزام
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_the_legacy_sync_fallback_still_runs(django_capture_on_commit_callbacks):
    """
    [B4-PRE2] الارتداد المتزامن لم يُمَسّ — تغيّر توقيته وحده.

    قرارنا أن الارتداد المتزامن ممنوع في المسار المتتبَّع، ولا منتج متتبَّع
    بعد. فإزالته هنا كانت ستُغيّر سلوك الإرسال القديم في دفعة غرضها التوقيت.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with (
        patch(
            "notifications.tasks.hub_send_notification_task.delay",
            side_effect=RuntimeError("broker down"),
        ),
        patch("notifications.hub._send_sync") as sync,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            _dispatch(school, [user])

    assert sync.called


@pytest.mark.django_db
def test_the_legacy_sync_fallback_waits_for_the_commit_too(
    django_capture_on_commit_callbacks,
):
    """
    الارتداد ليس مخرجاً من التأجيل.

    لو بقي داخل المعاملة لكان فشلُ الوسيط طريقاً لإرسال بريد عن حدث يتراجع —
    وهو نفس العطب من باب آخر.
    """
    school = SchoolFactory()
    user = UserFactory(email="p@example.com")

    with (
        patch(
            "notifications.tasks.hub_send_notification_task.delay",
            side_effect=RuntimeError("broker down"),
        ),
        patch("notifications.hub._send_sync") as sync,
    ):
        with django_capture_on_commit_callbacks(execute=False):
            _dispatch(school, [user])

        assert not sync.called, "أرسل مباشرةً قبل الالتزام"


# ══════════════════════════════════════════════════════════════════
# الطبقتان مسمّاتان
# ══════════════════════════════════════════════════════════════════


def test_registration_and_execution_are_separate_names():
    """
    [B4-PRE2] اسمان لا اسم واحد.

    خلط التسجيل بالتنفيذ تحت `_queue_external` كان يُخفي أيّ طبقة تنشر فعلاً،
    وهو تمييز سيصير حاسماً حين يدخل المصالِح.
    """
    from notifications import hub

    assert callable(hub._queue_external_after_commit)
    assert callable(hub._queue_external_now)
    assert not hasattr(hub, "_queue_external")


def test_the_hub_registers_rather_than_publishes():
    """`dispatch` لا يُنادي طبقة النشر مباشرةً."""
    import inspect

    source = inspect.getsource(NotificationHub.dispatch)

    assert "_queue_external_after_commit(" in source
    assert "_queue_external_now(" not in source
