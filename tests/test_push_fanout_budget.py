"""[B4-5] ميزانية زمن Push — حدٌّ بنيويّ لا رقمٌ مُختار.

`webpush()` بلا `timeout` ينتظر بلا حدّ. وحينها ينقضي استئجار التسليم والعامل
حيٌّ يعمل، فيكتب المُصالِح `unknown_outcome` على تسليمٍ لم يُحسم بعد — ثم يعود
العامل فيجد سياجه ساقطاً فلا يكتب شيئاً. نخسر نتيجةً كانت **معروفة** ونُسجّل
جهلاً لم يكن قائماً.

ورفعُ مدّة الاستئجار يؤجّل ولا يُصلح: العلّة أن الحدّ الأعلى للتنفيذ غير معرَّف.
"""

import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone

from notifications.delivery_state import claim_delivery
from notifications.models import NotificationDelivery, NotificationDispatch, PushSubscription
from notifications.push_subscriptions import register_subscription
from notifications.tasks import send_push_task
from tests.conftest import SchoolFactory, UserFactory


@pytest.fixture
def recipient(db):
    school = SchoolFactory()
    return school, UserFactory(email="p@example.com", phone="")


def _subscribe(user, school, n):
    """يُسجّل `n` اشتراكاً عبر المالك — فالسقف يُطبَّق كما في الإنتاج."""
    for index in range(n):
        register_subscription(
            user=user,
            school=school,
            endpoint=f"https://push.example.invalid/{user.pk}/{index}",
            p256dh="k" * 32,
            auth="a" * 16,
        )


def _delivery(school, user):
    dispatch = NotificationDispatch.objects.create(school=school, event_type="general")
    return NotificationDelivery.objects.create(
        dispatch=dispatch, school=school, recipient=user, channel="push"
    )


def _on_its_last_attempt(delivery):
    """يجعل الاستحواذ القادم يبلغ الميزانية.

    الغرض جعل النهاية **حاسمة**: عند الاستنفاد يكتب `_tracked_failure` نهايةً
    ويعود بقيمة، بدل `self.retry()` التي تُعيد رفع الاستثناء الأصلي حين تُستدعى
    المهمّة مباشرةً خارج سياق طلبٍ حقيقي. والثابت المُختبَر واحد في الحالتين:
    العامل يكتب نهايته وهو ما زال يملك سياجه.
    """
    NotificationDelivery.objects.filter(id=delivery.id).update(
        attempt_count=settings.NOTIFICATION_MAX_DELIVERY_ATTEMPTS - 1
    )


# ═══════════════════════════════════════════════════════════════════
#  السقف — ثابتٌ لا نصيحة
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_the_cap_cannot_be_exceeded(recipient):
    """أكثر من السقف ⇒ الأقدم استعمالاً يخرج، والعدد الفعّال يبقى عند الحدّ."""
    school, user = recipient
    cap = settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS

    _subscribe(user, school, cap + 3)

    active = PushSubscription.objects.filter(user=user, is_active=True).count()
    assert active == cap

    # ولا صفّ يُحذف — الأثر باقٍ وسجلّات المحاولات تشير إليه.
    assert PushSubscription.objects.filter(user=user).count() == cap + 3


@pytest.mark.django_db
def test_the_last_allowed_subscription_is_accepted(recipient):
    """السقف حدٌّ لا خصم: الاشتراك رقم `cap` يُقبل ولا يُخرج أحداً."""
    school, user = recipient
    cap = settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS

    _subscribe(user, school, cap - 1)

    _, created, evicted = register_subscription(
        user=user,
        school=school,
        endpoint="https://push.example.invalid/last",
        p256dh="k" * 32,
        auth="a" * 16,
    )

    assert created is True
    assert evicted == 0
    assert PushSubscription.objects.filter(user=user, is_active=True).count() == cap


@pytest.mark.django_db
def test_the_least_recently_used_is_the_one_evicted(recipient):
    """الإخراج سياسةٌ معلومة لا اعتباط: الأقدم استعمالاً أولاً."""
    school, user = recipient
    cap = settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS
    _subscribe(user, school, cap)

    rows = list(PushSubscription.objects.filter(user=user).order_by("created_at"))
    now = timezone.now()

    # الأول استُعمل قديماً، والباقي استُعملوا الآن.
    PushSubscription.objects.filter(pk=rows[0].pk).update(last_used=now - timedelta(days=9))
    PushSubscription.objects.exclude(pk=rows[0].pk).update(last_used=now)

    register_subscription(
        user=user,
        school=school,
        endpoint="https://push.example.invalid/newcomer",
        p256dh="k" * 32,
        auth="a" * 16,
    )

    rows[0].refresh_from_db()
    assert rows[0].is_active is False
    assert PushSubscription.objects.filter(user=user, is_active=True).count() == cap


@pytest.mark.django_db
def test_renewing_a_known_endpoint_does_not_grow_the_count(recipient):
    """المتصفّح يُعيد إرسال نفس الاشتراك دورياً — ولا يُخرج ذلك أحداً."""
    school, user = recipient
    _subscribe(user, school, 2)

    before = PushSubscription.objects.filter(user=user, is_active=True).count()

    _, created, evicted = register_subscription(
        user=user,
        school=school,
        endpoint=f"https://push.example.invalid/{user.pk}/0",
        p256dh="k" * 32,
        auth="a" * 16,
    )

    assert created is False
    assert evicted == 0
    assert PushSubscription.objects.filter(user=user, is_active=True).count() == before


def test_no_writer_bypasses_the_cap_owner():
    """حارس: لا إنشاء اشتراك خارج `push_subscriptions.py`."""
    import pathlib

    root = pathlib.Path(settings.BASE_DIR)
    owner = "notifications/push_subscriptions.py"
    offenders = []

    for path in root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")

        if (
            rel == owner
            # `.claude/worktrees` نسخٌ من المستودع نفسه — فحصُها يُبلّغ عن
            # الملفّ الواحد مرّتين، وبكودٍ قد يكون قديماً.
            or rel.startswith((".venv", ".claude/", "tests/", "staticfiles/"))
            or "migrations" in rel
        ):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")

        if (
            "PushSubscription.objects.create" in text
            or "PushSubscription.objects.update_or_create" in text
        ):
            offenders.append(rel)

    assert offenders == [], f"إنشاء اشتراك خارج مالك السقف: {offenders}"


# ═══════════════════════════════════════════════════════════════════
#  المهلة — كل نداء محدودٌ بحكم البناء
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_every_provider_call_carries_an_explicit_timeout(recipient):
    """بلا `timeout` ينتظر `requests` بلا حدّ — وهذا أصل العلّة كلّها."""
    school, user = recipient
    _subscribe(user, school, 2)
    delivery = _delivery(school, user)

    with patch("pywebpush.webpush") as provider:
        send_push_task(
            str(user.id), "عنوان", "نصّ", "/", school_id=str(school.id), delivery_id=str(delivery.id)
        )

    assert provider.call_count == 2

    for call in provider.call_args_list:
        assert call.kwargs["timeout"] == settings.PUSH_PROVIDER_TIMEOUT_SECONDS


@pytest.mark.django_db
def test_a_hung_subscription_raises_instead_of_hanging(recipient):
    """اشتراكٌ لا يردّ: المزوّد يرفع مهلته، والتسليم يُنهى ولا يُترك معلّقاً."""
    school, user = recipient
    _subscribe(user, school, 1)
    delivery = _delivery(school, user)
    _on_its_last_attempt(delivery)

    class _TimeoutError(OSError):
        """ما يرفعه `requests` عند انقضاء المهلة."""

    with patch("pywebpush.webpush", side_effect=_TimeoutError("read timed out")):
        result = send_push_task(
            str(user.id), "عنوان", "نصّ", "/", school_id=str(school.id), delivery_id=str(delivery.id)
        )

    delivery.refresh_from_db()
    assert result["status"] == "dead_letter"
    assert delivery.status == "dead_lettered"
    assert delivery.status != "in_progress", "تُرك التسليم بلا نهاية مكتوبة"
    assert delivery.lease_token is None


@pytest.mark.django_db
def test_provider_calls_stop_once_the_budget_is_spent(recipient):
    """الميزانية تُفحص قبل كل نداء — فلا نداء بعد نفادها."""
    school, user = recipient
    _subscribe(user, school, settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS)
    delivery = _delivery(school, user)
    _on_its_last_attempt(delivery)

    calls = []

    def _slow(*args, **kwargs):
        calls.append(1)
        # النداء الأول وحده يستهلك الميزانية كلّها.
        time.sleep(0.3)

    with override_settings(PUSH_WORST_CASE_BUDGET_SECONDS=0.2):
        with patch("pywebpush.webpush", side_effect=_slow):
            send_push_task(
                str(user.id),
                "عنوان",
                "نصّ",
                "/",
                school_id=str(school.id),
                delivery_id=str(delivery.id),
            )

    assert len(calls) == 1, f"استمرّت النداءات بعد نفاد الميزانية: {len(calls)}"


# ═══════════════════════════════════════════════════════════════════
#  المهلة اللينة — نهايةٌ يكتبها العامل لا المُصالِح
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_soft_timeout_is_written_by_the_worker_while_it_owns_the_lease(recipient):
    """
    هذا هو بيت القصيد.

    لو خرج `SoftTimeLimitExceeded` فوق المسار المالك للاستئجار، لانتهت المهمّة
    بلا `finalize_delivery` — فبقي التسليم `in_progress` حتى ينقضي استئجاره،
    وكتب المُصالِح `unknown_outcome` عن حالةٍ كان العامل يعرفها. أي عدنا إلى
    المشكلة نفسها باسمٍ آخر.
    """
    school, user = recipient
    _subscribe(user, school, 1)
    delivery = _delivery(school, user)
    _on_its_last_attempt(delivery)

    with patch("pywebpush.webpush", side_effect=SoftTimeLimitExceeded()):
        result = send_push_task(
            str(user.id), "عنوان", "نصّ", "/", school_id=str(school.id), delivery_id=str(delivery.id)
        )

    delivery.refresh_from_db()

    assert delivery.status == "dead_lettered"
    assert delivery.status != "unknown_outcome"
    assert delivery.lease_token is None, "بقي الاستئجار معلّقاً بعد كتابة النهاية"
    assert result["status"] == "dead_letter"


@pytest.mark.django_db
def test_the_lease_is_still_valid_when_the_soft_timeout_lands(recipient):
    """المهلة اللينة تقع قبل انقضاء الاستئجار بهامش — لا في اللحظة نفسها."""
    school, user = recipient
    _subscribe(user, school, 1)
    delivery = _delivery(school, user)

    token = claim_delivery(delivery.id, school.id)
    delivery.refresh_from_db()

    remaining = (delivery.lease_expires_at - timezone.now()).total_seconds()

    assert token is not None
    assert (
        settings.PUSH_SOFT_TIME_LIMIT_SECONDS < remaining
    ), "المهلة اللينة تتجاوز عمر الاستئجار — فقد ينقضي قبل أن يكتب العامل نهايته"


def test_the_task_declares_a_soft_time_limit():
    """حدٌّ مُعلَن على المهمّة، لا اعتمادٌ على أن الشبكة ستتصرّف بأدب."""
    assert send_push_task.soft_time_limit == settings.PUSH_SOFT_TIME_LIMIT_SECONDS


# ═══════════════════════════════════════════════════════════════════
#  سلسلة الحدود — تُفحص عند الإقلاع
# ═══════════════════════════════════════════════════════════════════


def test_the_budget_chain_holds_in_the_current_configuration():
    """أسوأ حالة < المهلة اللينة < (الاستئجار − هامش الأمان)."""
    worst = settings.PUSH_WORST_CASE_BUDGET_SECONDS
    soft = settings.PUSH_SOFT_TIME_LIMIT_SECONDS
    ceiling = (
        settings.NOTIFICATION_DELIVERY_LEASE_SECONDS - settings.PUSH_LEASE_SAFETY_MARGIN_SECONDS
    )

    assert worst < soft < ceiling, f"worst={worst} soft={soft} ceiling={ceiling}"


def test_the_worst_case_is_derived_from_the_cap_not_from_measurement():
    """الرقم مُشتقّ من السقف والمهل — فيبقى صادقاً مهما تغيّر سلوك الشبكة."""
    expected = (
        settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS
        * (settings.PUSH_PROVIDER_TIMEOUT_SECONDS + settings.PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS)
        + settings.PUSH_TASK_MARGIN_SECONDS
    )

    assert settings.PUSH_WORST_CASE_BUDGET_SECONDS == expected


@pytest.mark.parametrize(
    "broken",
    [
        {"PUSH_SOFT_TIME_LIMIT_SECONDS": 5},  # أصغر من أسوأ حالة
        {"PUSH_MAX_ACTIVE_SUBSCRIPTIONS": 0},  # سقفٌ غير موجب
        {"PUSH_PROVIDER_TIMEOUT_SECONDS": 0},  # مهلةٌ غير موجبة
        {"PUSH_LEASE_SAFETY_MARGIN_SECONDS": 0},  # هامشٌ غير موجب
        # وحدّان يدخلان الحساب **جمعاً**، فالسالب فيهما يُقلّص أسوأ حالة
        # فتمرّ المتباينة كذباً — وهو أخطر من تجاوزها صراحةً.
        {"PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS": -5},
        {"PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS": 0},
        {"PUSH_TASK_MARGIN_SECONDS": -60},
        {"PUSH_TASK_MARGIN_SECONDS": 0},
    ],
)
def test_a_broken_budget_chain_refuses_to_boot(broken):
    """الخلل يُرفض حيث يُقرأ الإعداد — لا يظهر كـ`unknown_outcome` في الإنتاج."""
    import importlib

    base = importlib.import_module("shschool.settings.base")

    with override_settings(**broken):
        merged = {
            name: broken.get(name, getattr(settings, name))
            for name in (
                "PUSH_PROVIDER_TIMEOUT_SECONDS",
                "PUSH_MAX_ACTIVE_SUBSCRIPTIONS",
                "PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS",
                "PUSH_TASK_MARGIN_SECONDS",
                "PUSH_SOFT_TIME_LIMIT_SECONDS",
                "PUSH_LEASE_SAFETY_MARGIN_SECONDS",
                "NOTIFICATION_DELIVERY_LEASE_SECONDS",
            )
        }
        merged["PUSH_WORST_CASE_BUDGET_SECONDS"] = (
            merged["PUSH_MAX_ACTIVE_SUBSCRIPTIONS"]
            * (
                merged["PUSH_PROVIDER_TIMEOUT_SECONDS"]
                + merged["PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS"]
            )
            + merged["PUSH_TASK_MARGIN_SECONDS"]
        )

        with patch.multiple(base, **merged):
            with pytest.raises(ImproperlyConfigured):
                base._validate_push_budget()


# ═══════════════════════════════════════════════════════════════════
#  القياس — يُحدّد الهامش، ولا يُقيم السلامة
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_the_configured_overhead_exceeds_the_measured_one(recipient):
    """يقيس ما لا تُغطّيه مهلة المزوّد: كتابات القاعدة والانتقال بين الاشتراكات.

    السلامة لا تأتي من هذا القياس بل من السقف والمهل — والقياس يُحدّد الهامش
    وحده. ولذلك يُقارَن بالقيمة المضبوطة لا بحدٍّ مطلق: انحدارٌ يُضاعف كلفة
    الاشتراك الواحد يظهر هنا قبل أن يظهر كاستئجارٍ ينقضي في الإنتاج.
    """
    school, user = recipient
    n = settings.PUSH_MAX_ACTIVE_SUBSCRIPTIONS
    _subscribe(user, school, n)
    delivery = _delivery(school, user)

    with patch("pywebpush.webpush"):  # مزوّدٌ لحظيّ — فالمقيس هو ما حوله
        started = time.monotonic()
        send_push_task(
            str(user.id), "عنوان", "نصّ", "/", school_id=str(school.id), delivery_id=str(delivery.id)
        )
        elapsed = time.monotonic() - started

    per_subscription = elapsed / n

    assert per_subscription < settings.PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS, (
        f"الكلفة المقيسة لكل اشتراك {per_subscription:.3f}s تجاوزت الميزانية "
        f"{settings.PUSH_PER_SUBSCRIPTION_OVERHEAD_SECONDS}s — أعد حساب الحدود"
    )


# ═══════════════════════════════════════════════════════════════════
#  التسلسل — السقف تحت تنافسٍ حقيقيّ
# ═══════════════════════════════════════════════════════════════════


@override_settings(PUSH_MAX_ACTIVE_SUBSCRIPTIONS=1)
@pytest.mark.django_db(transaction=True)
def test_two_concurrent_first_time_registrations_cannot_break_the_cap():
    """أول جهازين لمستخدمٍ بلا اشتراكات — وهي الحالة التي يسقط فيها القفل الساذج.

    `select_for_update()` على اشتراكات المستخدم وحدها لا يقفل شيئاً حين لا صفَّ
    له بعد: المجموعة فارغة، و"عدم وجود صفّ" ليس شيئاً يُقفل. فيقرأ الخيطان صفراً
    ثم يكتبان معاً. ولذلك يُقفل صفّ المستخدم نفسه — وهو موجودٌ دائماً.

    والاختبار خيطان فعليّان لا محاكاة: القفل لا يظهر أثره إلا في اشتباك حقيقي.
    """
    import threading

    from django.db import connections

    school = SchoolFactory()
    user = UserFactory(email="race@example.com", phone="")

    barrier = threading.Barrier(2)
    errors = []

    def _register(index):
        try:
            barrier.wait(timeout=10)
            register_subscription(
                user=user,
                school=school,
                endpoint=f"https://push.example.invalid/race/{index}",
                p256dh="k" * 32,
                auth="a" * 16,
            )
        except Exception as exc:  # noqa: BLE001 — يُجمع ليظهر لا ليُبتلع
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=_register, args=(i,)) for i in range(2)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], errors

    active = PushSubscription.objects.filter(user=user, is_active=True).count()
    assert active == 1, f"تجاوز السقف تحت التنافس: {active} اشتراكات فعّالة"
    assert PushSubscription.objects.filter(user=user).count() == 2
