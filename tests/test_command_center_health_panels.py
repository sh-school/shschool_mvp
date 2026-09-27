"""[COMMAND-CENTER] لوحتا «الإشعارات والرسائل» و«الأمان والدخول» — أعدادٌ لا أسماء (قرارُ المالك 2026-09-27).

الرسالةُ الفاشلةُ غيرُ المحلولةِ أحمرُ، والتسليمُ العالقُ أو المستنفَدُ «انتبه»، و«لا وجهةَ صالحةً» ليس فشلاً؛ ومحاولاتُ الدخول: عشرٌ «انتبه»
وقفزةٌ (30 وستّةُ أضعاف ما قبلها) أحمر. ولا اسمَ ولا مستلمَ ولا IP يصل الـcache.
"""

import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from command_center import collectors, contract
from command_center.collectors import messaging, security
from core.models import AuditLog
from notifications.models import DeadLetterMessage, NotificationDelivery, NotificationDispatch

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _panel(key):
    return next(p for p in contract.read_panels() if p["key"] == key)


def _delivery(school, user, status="sent", age_hours=0):
    dispatch = NotificationDispatch.objects.create(school=school, event_type="general")
    delivery = NotificationDelivery.objects.create(
        dispatch=dispatch, school=school, recipient=user, channel="email", status=status
    )
    NotificationDelivery.objects.filter(pk=delivery.pk).update(
        created_at=timezone.now() - timedelta(hours=age_hours)
    )
    return delivery


def _login_failures(school, count, hours_ago, action="login_failed"):
    """سجلُّ التدقيق غيرُ قابلٍ للتعديل حتى في القاعدة (trigger، PDPPL م.19) فلا `update` لتأريخ صفٍّ:
    نُعطّل `auto_now_add` لحظةَ الإنشاء وحدَها (وتُعاد بعدها) فيُكتب الوقتُ صريحاً — وتعطيلُه عامّاً يكسر ما يكتبه غيرُنا من سجلّات."""
    field = AuditLog._meta.get_field("timestamp")
    stamp = timezone.now() - timedelta(hours=hours_ago)
    field.auto_now_add = False
    try:
        for _ in range(count):
            AuditLog.objects.create(
                user=None,
                school=school,
                action=action,
                model_name="CustomUser",
                object_id="x",
                object_repr="محاولة",
                timestamp=stamp,
            )
    finally:
        field.auto_now_add = True


def test_both_panels_are_registered_and_collected_locally():
    keys = {p.key for p in contract.PANELS}
    assert {"messaging", "security"} <= keys
    assert {"messaging", "security"} <= set(collectors.LOCAL)


# ── الإشعارات ─────────────────────────────────────────────────────────────────


def test_messaging_level_rules():
    assert messaging.level(0, 0, 0, 0) == contract.OK
    assert messaging.level(0, 1, 0, 0) == contract.WARN
    assert messaging.level(0, 0, 2, 0) == contract.WARN
    assert messaging.level(0, 0, 0, 1) == contract.WARN
    assert messaging.level(1, 0, 0, 0) == contract.BAD


def test_healthy_delivery_is_green_and_undeliverable_is_not_a_fault(school, teacher_user):
    _delivery(school, teacher_user, "sent")
    _delivery(school, teacher_user, "undeliverable")
    messaging.collect()
    panel = _panel("messaging")
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert {"label": "سُلّمت / 24س", "value": "1 من 2"} in panel["metrics"]
    assert {"label": "بلا وجهةٍ صالحة", "value": "1"} in panel["metrics"]


def test_an_unresolved_dead_letter_makes_the_panel_red(school, teacher_user):
    delivery = _delivery(school, teacher_user, "dead_lettered")
    DeadLetterMessage.objects.create(school=school, delivery=delivery, kind="email")
    messaging.collect()
    panel = _panel("messaging")
    assert panel["status"] == contract.BAD
    assert panel["headline"] == "1 رسالةً فاشلةً غيرَ محلولة"


def test_a_resolved_dead_letter_no_longer_reds_but_the_exhausted_delivery_is_amber(
    school, teacher_user
):
    delivery = _delivery(school, teacher_user, "dead_lettered")
    DeadLetterMessage.objects.create(school=school, delivery=delivery, kind="email", resolved=True)
    messaging.collect()
    assert _panel("messaging")["status"] == contract.WARN


def test_a_delivery_stuck_over_an_hour_is_amber_and_a_fresh_waiting_one_is_not(
    school, teacher_user
):
    _delivery(school, teacher_user, "pending", age_hours=0)
    messaging.collect()
    assert _panel("messaging")["status"] == contract.OK
    _delivery(school, teacher_user, "retry_wait", age_hours=2)
    messaging.collect()
    panel = _panel("messaging")
    assert panel["status"] == contract.WARN
    assert any(m["label"] == "بانتظار" and "1 عالقة" in m["value"] for m in panel["metrics"])


def test_an_unknown_outcome_is_amber(school, teacher_user):
    _delivery(school, teacher_user, "unknown_outcome")
    messaging.collect()
    assert _panel("messaging")["status"] == contract.WARN


def test_messaging_stores_no_recipient_or_text(school, teacher_user):
    _delivery(school, teacher_user, "sent")
    messaging.collect()
    blob = json.dumps(_panel("messaging"), ensure_ascii=False)
    assert teacher_user.full_name not in blob and str(teacher_user.pk) not in blob


# ── الأمان ────────────────────────────────────────────────────────────────────


def test_security_level_rules():
    assert security.level(0, 0, 0) == contract.OK
    assert security.level(9, 0, 0) == contract.OK
    assert security.level(10, 2, 0) == contract.WARN
    assert security.level(0, 0, 1) == contract.WARN
    assert security.level(29, 0, 0) == contract.WARN  # دون حدّ القفزة
    assert security.level(30, 0, 0) == contract.BAD
    assert security.level(30, 6, 0) == contract.WARN  # ستّةُ أضعاف السابق = 36
    assert security.level(37, 6, 0) == contract.BAD


def test_a_quiet_day_is_green(school):
    security.collect()
    panel = _panel("security")
    assert panel["status"] == contract.OK and panel["headline"] == "لا نشاطَ دخولٍ مريباً"


def test_ten_failures_are_amber_and_old_ones_are_not_counted(school):
    _login_failures(school, 10, hours_ago=2)
    _login_failures(school, 50, hours_ago=30)  # الأربعُ والعشرون قبلها
    security.collect()
    panel = _panel("security")
    assert panel["status"] == contract.WARN
    assert {"label": "دخولٌ فاشل / 24س", "value": "10"} in panel["metrics"]
    assert {"label": "الأربعُ والعشرون قبلها", "value": "50"} in panel["metrics"]


def test_a_spike_is_red(school):
    _login_failures(school, 40, hours_ago=1)
    security.collect()
    panel = _panel("security")
    assert panel["status"] == contract.BAD
    assert panel["headline"] == "قفزةٌ في محاولات الدخول الفاشلة"


def test_mfa_failures_count_as_failures_and_are_shown_separately(school):
    _login_failures(school, 3, hours_ago=1, action="mfa_failed")
    _login_failures(school, 2, hours_ago=1)
    security.collect()
    panel = _panel("security")
    assert {"label": "دخولٌ فاشل / 24س", "value": "5"} in panel["metrics"]
    assert {"label": "رمزُ تحقّقٍ خاطئ / 24س", "value": "3"} in panel["metrics"]


def test_security_stores_no_username_or_ip(school):
    _login_failures(school, 3, hours_ago=1)
    security.collect()
    blob = json.dumps(_panel("security"), ensure_ascii=False)
    assert "محاولة" not in blob and "x" not in {m["value"] for m in _panel("security")["metrics"]}
