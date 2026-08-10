"""
tests/test_delivery_failure_unit.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[P2-B3] وحدة الفشل تسليم، لا مهمة.

    DISPATCH   نيّة إشعار مرتبطة بحدث أعمال ومستلم
    DELIVERY   (dispatch, recipient, channel)
    ATTEMPT    محاولة فعلية لإرسال delivery
    DLQ ENTRY  delivery واحد انتهت محاولاته القابلة للإعادة بالفشل

النظام مبنيّ على هذا المعنى أصلاً: `notify_absence` و`notify_fail` يُرجعان
نتيجة مستقلة لكل (مستلم، قناة)، وقد ينجح البريد ويفشل SMS لنفس الشخص. فجعل
المهمة هي الوحدة يعني أن إعادتها تُعيد إرسال ما نجح وتُنتج إشعاراً مكرّراً.

هذه الاختبارات تُثبت العقد في الشيفرة وتمنع ارتداده.
"""

from pathlib import Path

import pytest

from notifications import tasks as notification_tasks

ROOT = Path(__file__).resolve().parents[1]
TASKS_SOURCE = (ROOT / "notifications" / "tasks.py").read_text(encoding="utf-8")


def _hub_body():
    start = TASKS_SOURCE.index("def hub_send_notification_task")
    end = TASKS_SOURCE.index("def _hub_to_notif_type")
    return TASKS_SOURCE[start:end]


def _push_body():
    start = TASKS_SOURCE.index("def send_push_task")
    end = TASKS_SOURCE.index("def send_push_to_school_task")
    return TASKS_SOURCE[start:end]


# ══════════════════════════════════════════════════════════════════
# الـHub منسّق لا مُرسِل
# ══════════════════════════════════════════════════════════════════


def test_hub_dispatches_deliveries_instead_of_sending_them():
    """
    [P2-B3] الـHub كان يُرسل البريد وSMS بنفسه ويُفوّض Push وحده.

    فكان فشل قناة واحدة يضيع صامتاً — المهمة تنتهي بنجاح ما دام أحدهما نجح.
    الآن كل قناة مهمة تسليم مستقلّة، لها retry الخاص بها ومسارها إلى DLQ.
    """
    hub = _hub_body()

    assert "NotificationService." not in hub, "the hub must not deliver by itself"
    assert "send_email_task.delay" in hub
    assert "send_sms_task.delay" in hub
    assert "send_push_task.delay" in hub


def test_partial_channel_failure_does_not_retry_the_dispatch():
    """
    [P2-B3] فشل قناة واحدة لا يُعيد إرسال القنوات الناجحة.

    كان الكود يرفع `Exception` عامة عند فشل كل القنوات — و`except` الخاص به
    يمسك (OSError, RuntimeError, ValueError, KeyError) فقط، فلم يلتقطها ولم
    يُستدعَ self.retry() قط رغم أن التعليق يقول "→ retry". وحتى لو التقطها،
    إعادة المهمة كانت ستُعيد إرسال ما نجح.

    التمييز مقصود: إعادة **التنسيق** تبقى مشروعة (عطل قاعدة بيانات قبل أي
    إرسال)، وإعادة **التسليم** مسؤولية مهمة القناة وحدها.
    """
    hub = _hub_body()

    assert "raise Exception(f" not in hub, "partial failure must not raise a task-level error"

    # لا يبقى self.retry إلا في مسار التنسيق — بعد كتلة الفشل الجزئي.
    partial_block = hub[hub.index("failures = [r for r in results") :]
    orchestration_start = partial_block.index("except (OSError")

    assert "self.retry" not in partial_block[:orchestration_start]


def test_orchestration_failure_remains_retryable():
    """
    [P2-B3] عطل التنسيق ليس تسليماً فاشلاً — وإعادته صحيحة.

    فشل جلب المستخدم أو المدرسة يقع **قبل** أي إرسال، فإعادة المهمة لا تُكرّر
    شيئاً. إلغاء هذا المسار كان سيُضيع الإرسال كلّه بصمت عند خطأ عابر.
    """
    hub = _hub_body()

    assert "except (OSError, RuntimeError, ValueError, KeyError)" in hub
    assert "self.retry" in hub


# ══════════════════════════════════════════════════════════════════
# Push: اشتراك ميّت ≠ تسليم فاشل
# ══════════════════════════════════════════════════════════════════


def test_dead_subscriptions_are_invalidated_not_dead_lettered():
    """
    [P2-B3] 404/410 يعني أن المتصفّح ألغى الاشتراك.

    إعادة المحاولة عليه لن تنجح أبداً، وتسجيله في DLQ يملؤها بضجيج لا إجراء
    له. التعطيل هو الإجراء الصحيح، والعدّ منفصل عن الفشل العابر.
    """
    push = _push_body()

    assert "invalidated" in push
    assert "is_active = False" in push
    assert "continue" in push, "an invalidated subscription must not fall through to failure"


def test_transient_push_failures_are_retryable_deliveries():
    """
    [P2-B3] فشل المزوّد على اشتراك صالح تسليمٌ فاشل قابل للإعادة.

    كان يُبتلع في عدّاد `failed` ثم تنتهي المهمة بنجاح على مستوى Celery —
    فلا retry ولا DLQ، ويختفي الفشل تماماً.
    """
    push = _push_body()

    assert "transient" in push
    assert "raise RuntimeError" in push, "a transient failure must reach the retry path"


def test_push_reaches_the_dead_letter_queue():
    """
    [P2-B3] النموذج يُعرّف kind="push" منذ إنشائه ولم يُكتب قط.

    القيمة كانت في الـchoices ولا تظهر في أي صفّ أبداً — تصميمٌ توقّع الالتقاط
    وتنفيذٌ لم يفعل.
    """
    push = _push_body()

    assert '_to_dlq(\n                "push"' in push or '"push",' in push
    assert "MaxRetriesExceededError" in push


def test_push_does_not_dead_letter_when_some_deliveries_succeeded():
    """
    [P2-B3] لا نُعيد ما نجح.

    الرفع مشروط بـ`sent == 0`: لو نجح اشتراك واحد فإعادة المهمة كانت ستُرسل
    له مرّة ثانية. هذا هو الفارق بين وحدة المهمة ووحدة التسليم عملياً.
    """
    push = _push_body()

    assert "sent == 0" in push


# ══════════════════════════════════════════════════════════════════
# الفهم المشترك للعقد
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("channel", ["email", "sms", "push"])
def test_every_channel_has_its_own_dead_letter_path(channel):
    """كل قناة تُسجّل فشلها النهائي بنفسها — لا قناة تتحدّث نيابةً عن أخرى."""
    assert f'"{channel}",' in TASKS_SOURCE


def test_dead_letter_kinds_match_the_model():
    """قيم kind في الشيفرة هي نفسها المعرَّفة في النموذج."""
    from notifications.models import DeadLetterMessage

    declared = {value for value, _label in DeadLetterMessage.KIND}

    assert declared == {"email", "sms", "push"}


def test_the_dlq_docstring_agrees_with_the_writer():
    """
    التوثيق لا يجوز أن يناقض الشيفرة.

    بقي النموذج بعد #32 يقول إن الـpayload "بيانات إعادة تشغيل" بينما صُحّحت
    tasks.py لتقول إنها تشخيصية — وmain كان يناقض نفسه.
    """
    from notifications.models import DeadLetterMessage

    doc = DeadLetterMessage.__doc__ or ""

    assert "تشخيصية" in doc
    assert "بيانات إعادة تشغيل" not in doc


def test_source_anchors_still_resolve():
    """
    الماسح نفسه يحتاج برهاناً.

    لو أُعيدت تسمية المهام لأصبحت كل التأكيدات أعلاه تقرأ نصاً فارغاً وتمرّ
    خضراء بلا أن تفحص شيئاً.
    """
    assert len(_hub_body()) > 500
    assert len(_push_body()) > 500
    assert "hub_send_notification_task" in TASKS_SOURCE
    assert hasattr(notification_tasks, "send_push_task")
