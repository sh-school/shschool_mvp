"""
tests/test_delivery_lease.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-3A] الاستحواذ والسياج — بدائيّ الحالة قبل أن تُوصَّل بأي عامل.

لا مهمّة تستدعي هذه الدوالّ بعد؛ B4-3B هي التي تُوصّلها. المُختبَر هنا هو
الثوابت التي ستعتمد عليها: من يملك الصفّ، ومن يُمنَع من كتابته، وماذا يحدث حين
تنقضي الملكيّة.

والاستحواذ يُختبَر بأثره على القاعدة لا بقراءة كوده: `UPDATE` مشروط ينجح لواحد
ويفشل للآخر، وهذا ما لا يقوله إلا تنفيذٌ فعليّ.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from notifications.delivery_state import (
    CLAIMABLE,
    FINALIZABLE,
    claim_delivery,
    finalize_delivery,
)
from notifications.models import (
    NotificationDelivery,
    NotificationDispatch,
)
from tests.conftest import SchoolFactory, UserFactory


def _delivery(school=None, status="pending", channel="email"):
    school = school or SchoolFactory()
    dispatch = NotificationDispatch.objects.create(school=school, event_type="absence")
    return NotificationDelivery.objects.create(
        dispatch=dispatch,
        school=school,
        recipient=UserFactory(),
        channel=channel,
        status=status,
    )


# ══════════════════════════════════════════════════════════════════
# الاستحواذ
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.parametrize("status", CLAIMABLE)
def test_a_claimable_delivery_can_be_claimed(status):
    """`pending` بداية و`retry_wait` انتظار إعادة — كلاهما يُستحوَذ عليه."""
    delivery = _delivery(status=status)

    token = claim_delivery(delivery.id, delivery.school_id)

    assert token is not None
    delivery.refresh_from_db()
    assert delivery.status == "in_progress"
    assert delivery.lease_token == token
    assert delivery.lease_expires_at > timezone.now()


@pytest.mark.django_db
def test_a_second_claim_is_refused():
    """
    [B4-3A] عاملان على صفّ واحد — أحدهما يخسر.

    والرفض ليس خطأً بل الجواب المطلوب. لو كان الاستحواذ قراءةً ثم كتابة لمرّ
    الاثنان من النافذة بينهما وظنّ كلٌّ منهما أنه المالك.
    """
    delivery = _delivery()

    first = claim_delivery(delivery.id, delivery.school_id)
    second = claim_delivery(delivery.id, delivery.school_id)

    assert first is not None
    assert second is None

    delivery.refresh_from_db()
    assert delivery.lease_token == first, "الاستحواذ الثاني بدّل المالك"


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["sent", "dead_lettered"])
def test_a_terminal_delivery_cannot_be_claimed(status):
    """ما انتهى لا يُستأنَف — والنهاية تعني نهاية."""
    delivery = _delivery(status=status)

    assert claim_delivery(delivery.id, delivery.school_id) is None

    delivery.refresh_from_db()
    assert delivery.status == status


@pytest.mark.django_db
def test_a_delivery_of_another_school_cannot_be_claimed():
    """
    المدرسة شرطٌ صريح في المُسنَد رغم وجود RLS.

    الاعتماد على أن المُعرِّف وحده لن يقود إلى مستأجر آخر يجعل التوقّع ضمنياً
    في المكان الذي يجب أن يكون فيه مكتوباً.
    """
    delivery = _delivery()
    other = SchoolFactory()

    assert claim_delivery(delivery.id, other.id) is None

    delivery.refresh_from_db()
    assert delivery.status == "pending"


@pytest.mark.django_db
def test_each_claim_mints_a_fresh_token():
    """رمزٌ مُعاد استعماله يُبطل السياج: عاملٌ قديم يحمل رمزاً صار صالحاً ثانيةً."""
    first = _delivery()
    second = _delivery(school=first.school)

    assert claim_delivery(first.id, first.school_id) != claim_delivery(second.id, second.school_id)


@pytest.mark.django_db
def test_claiming_records_the_moment_of_the_transition():
    """`status_changed_at` يُكتب صراحةً — لا `auto_now` مع `update()`."""
    delivery = _delivery()
    before = delivery.status_changed_at

    claim_delivery(delivery.id, delivery.school_id)

    delivery.refresh_from_db()
    assert delivery.status_changed_at > before


# ══════════════════════════════════════════════════════════════════
# الإنهاء المُسيَّج
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.parametrize("status", FINALIZABLE)
def test_the_holder_of_the_token_may_finalize(status):
    """صاحب الرمز الحيّ يكتب النهاية، ويُفرَّغ الاستئجار معها."""
    delivery = _delivery()
    token = claim_delivery(delivery.id, delivery.school_id)

    assert finalize_delivery(delivery.id, delivery.school_id, token, status) is True

    delivery.refresh_from_db()
    assert delivery.status == status
    assert delivery.lease_token is None
    assert delivery.lease_expires_at is None


@pytest.mark.django_db
def test_a_stale_token_changes_nothing():
    """
    [B4-3A] رمز السياج — وهذا هو سبب وجوده.

    عاملٌ بطيء يعود بعد أن انتقلت الملكيّة لا يهدم الحالة الأحدث. وليس فشلاً
    في الإرسال بل فقدانٌ للسلطة على الصفّ.
    """
    delivery = _delivery()
    stale = uuid.uuid4()
    claim_delivery(delivery.id, delivery.school_id)

    assert finalize_delivery(delivery.id, delivery.school_id, stale, "sent") is False

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


@pytest.mark.django_db
def test_the_right_token_after_the_lease_expired_changes_nothing():
    """
    [B4-3A] الرمز الصحيح لا يكفي — الاستئجار يجب أن يكون حيّاً.

    لولا شرط المهلة لاستطاع عاملٌ عاد متأخّراً أن يسبق المُصالِح إلى الصفّ
    فيكتب `sent` عن نتيجة لم يعد يعرفها.
    """
    delivery = _delivery()
    token = claim_delivery(delivery.id, delivery.school_id)

    NotificationDelivery.objects.filter(id=delivery.id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )

    assert finalize_delivery(delivery.id, delivery.school_id, token, "sent") is False

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


@pytest.mark.django_db
def test_an_expired_lease_is_not_reclaimed_in_this_stage():
    """
    [B4-3A] ما انقضى استئجاره يبقى عالقاً — عمداً.

    عاملٌ مات بعد أن قبِل المزوّد الرسالة لا يترك ما يقول إن كانت وصلت، فإعادةُ
    الإرسال احتمالُ تكرار حقيقي. تفسيرُ الصفّ شأن المُصالِح في B4-4، وبقاؤه
    عالقاً حتى ذلك الحين هو نفسه الدليل على أن المُصالِح شرطٌ قبل التفعيل.
    """
    delivery = _delivery()
    claim_delivery(delivery.id, delivery.school_id)

    NotificationDelivery.objects.filter(id=delivery.id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )

    assert claim_delivery(delivery.id, delivery.school_id) is None

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


@pytest.mark.django_db
def test_finalizing_a_delivery_of_another_school_changes_nothing():
    delivery = _delivery()
    other = SchoolFactory()
    token = claim_delivery(delivery.id, delivery.school_id)

    assert finalize_delivery(delivery.id, other.id, token, "sent") is False

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


@pytest.mark.django_db
def test_finalizing_something_never_claimed_changes_nothing():
    """لا نهاية بلا استحواذ سبقها."""
    delivery = _delivery()

    assert finalize_delivery(delivery.id, delivery.school_id, uuid.uuid4(), "sent") is False

    delivery.refresh_from_db()
    assert delivery.status == "pending"


@pytest.mark.django_db
def test_a_retry_wait_delivery_can_be_claimed_again():
    """دورة كاملة: استحواذ ← انتظار إعادة ← استحواذ جديد برمز جديد."""
    delivery = _delivery()

    first = claim_delivery(delivery.id, delivery.school_id)
    finalize_delivery(delivery.id, delivery.school_id, first, "retry_wait")

    second = claim_delivery(delivery.id, delivery.school_id)

    assert second is not None
    assert second != first


# ══════════════════════════════════════════════════════════════════
# ما لا تستطيع هذه المرحلة كتابته
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["undeliverable", "unknown_outcome", "pending", "in_progress"])
def test_this_stage_refuses_to_write_a_status_it_cannot_mean(status):
    """
    [B4-3A] لا حالة بلا منتج لها — والعكس أيضاً.

    `undeliverable` تنتظر B4-3B و`unknown_outcome` تنتظر B4-4. وقبولُ اسمٍ
    هنا لأنه سيصير صالحاً لاحقاً يجعل المرحلة تدّعي دلالةً لا تملكها.
    """
    delivery = _delivery()
    token = claim_delivery(delivery.id, delivery.school_id)

    with pytest.raises(ValueError):
        finalize_delivery(delivery.id, delivery.school_id, token, status)

    delivery.refresh_from_db()
    assert delivery.status == "in_progress"


def test_the_model_still_carries_only_the_five_states():
    """`undeliverable` و`unknown_outcome` تدخلان مع من يكتبهما لا قبله."""
    codes = {code for code, _ in NotificationDelivery.STATUS}

    assert codes == {"pending", "in_progress", "sent", "retry_wait", "dead_lettered"}


# ══════════════════════════════════════════════════════════════════
# الإعداد
# ══════════════════════════════════════════════════════════════════


def test_the_lease_duration_is_configurable_and_positive():
    """
    مهلة صفرية أو سالبة تجعل كل استئجار منتهياً لحظة إنشائه.

    والإعداد مستقلّ عن راية الخطّ: المهلة تصف زمن التنفيذ لا تشغيله.
    """
    from django.conf import settings

    assert settings.NOTIFICATION_DELIVERY_LEASE_SECONDS > 0
    assert settings.NOTIFICATION_DELIVERY_LEASE_SECONDS == 900


@pytest.mark.django_db
def test_the_lease_window_follows_the_configured_duration():
    delivery = _delivery()
    now = timezone.now()

    claim_delivery(delivery.id, delivery.school_id, now=now, lease_seconds=60)

    delivery.refresh_from_db()
    assert delivery.lease_expires_at == now + timedelta(seconds=60)


@pytest.mark.django_db
@pytest.mark.parametrize("seconds", [0, -1, -900])
def test_a_non_positive_lease_is_refused_at_the_call_site(seconds):
    """
    [B4-3A] فحصُ الإعداد لا يبلغ مُستدعياً يُمرّر القيمة مباشرةً.

    والصيغة الأولى `lease_seconds or settings...` كانت تُخفي حالتين: الصفر
    قيمة كاذبة فيتحوّل صامتاً إلى الافتراضي بدل أن يُرفض — وهو أخطر من السالب
    لأنه يبدو ناجحاً — والسالب قيمة صادقة فيُقبل، فيُنشئ استئجاراً منتهياً
    لحظة إنشائه يلتقطه المُصالِح كأن عاملاً مات.
    """
    delivery = _delivery()

    with pytest.raises(ValueError):
        claim_delivery(delivery.id, delivery.school_id, lease_seconds=seconds)

    delivery.refresh_from_db()
    assert delivery.status == "pending", "كُتب استحواذ رغم رفض المهلة"
    assert delivery.lease_token is None


# ══════════════════════════════════════════════════════════════════
# مالك واحد للحالة
# ══════════════════════════════════════════════════════════════════


STATE_OWNER = "notifications/delivery_state.py"

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

#: حقول الاستئجار — أسماء لا يحملها غير هذا الجدول، فذكرُها خارج المالك انحراف.
LEASE_FIELDS = ("lease_token", "lease_expires_at")


def _application_sources():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    for path in root.rglob("*.py"):
        if SKIPPED_DIRS & set(path.relative_to(root).parts):
            continue
        yield str(path.relative_to(root)).replace("\\", "/"), path.read_text(encoding="utf-8")


def _delivery_state_updates(text):
    """`NotificationDelivery.objects...update(...)` — تعديلُ حالة لا إنشاء.

    `bulk_create` في الكاتب المتتبَّع إنشاءٌ لا انتقال، ويحرسه حارسُ الكاتب في
    B4-0. المقصود هنا من يُحرّك صفّاً قائماً من حالة إلى أخرى.
    """
    import ast

    found = []

    def _root_name(node):
        while isinstance(node, ast.Attribute | ast.Call):
            node = node.func if isinstance(node, ast.Call) else node.value
        return getattr(node, "id", None)

    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and _root_name(node.func.value) == "NotificationDelivery"
        ):
            found.append(node.lineno)

    return found


def test_only_the_state_owner_writes_the_lease():
    """
    [B4-3A] مالك واحد للحالة — من الآن لا بعد اكتشاف الانحراف.

    المهامّ الأربع ستُوصَّل في B4-3B، ولو كتب كلٌّ منها استحواذه بنفسه لتكرّر
    المنطق أربع مرّات وانحرفت نسخة عن أخرى في الدفعة التي لا ينتبه فيها أحد.
    """
    offenders = []

    for path, text in _application_sources():
        if path in (STATE_OWNER, "notifications/models.py"):
            continue

        offenders += [f"{path}: {field}" for field in LEASE_FIELDS if field in text]
        offenders += [f"{path}:{line} update()" for line in _delivery_state_updates(text)]

    assert not offenders, "كتابةُ حالة خارج مالكها: " + ", ".join(offenders)


def test_the_state_owner_guard_reads_the_owner_itself():
    """
    حارس لا يجد المالك يمرّ دائماً.

    وصيغته الأولى كانت تبحث عن `status="in_progress"` نصّاً، فالتقطت نماذج لا
    علاقة لها بالتسليم — جلسةً وطلبَ تبديل. حارسٌ يُنذر عن غير موضعه يُدرَّب
    الناس على تجاهله.
    """
    sources = dict(_application_sources())

    assert len(sources) > 100
    assert STATE_OWNER in sources
    assert all(field in sources[STATE_OWNER] for field in LEASE_FIELDS)
    assert _delivery_state_updates(sources[STATE_OWNER]), "المالك لا يُحرّك حالةً — الحارس بلا موضوع"
