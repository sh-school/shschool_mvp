"""[B4-6] الحدّ اللين يسافر في الرسالة — فمصدره يجب أن يكون واحداً عند النشر.

عقد Celery، من مصدره المثبَّت:

    apply_async → extract_exec_options(task)      task.py:27
                → amqp.as_task_v2(...)            base.py:781
                → 'timelimit': [hard, soft]       amqp.py:335
    worker      → soft_timeout = soft_time_limit or task.soft_time_limit
                                                  request.py:363

فالشقّ الأخير يفصل حالتين:

    ترويسة `None`   ⇒ يسقط العامل إلى إعداده        آمن
    ترويسة صريحة    ⇒ **تتغلّب** على إعداد العامل

والخطر في الثانية: `soft=300` تجعل العامل ينتظر خمس دقائق بينما استئجاره محسوبٌ
على 120 ثانية — فينقضي والعامل حيٌّ، ويكتب المُصالِح `unknown_outcome` عن حالةٍ
كانت معروفة. أي علّة B4-5 نفسها، عائدةً من باب النشر.
"""

import ast
import pathlib

import pytest
from django.conf import settings
from django.test import override_settings

from notifications.push_publisher import canonical_soft_time_limit, enqueue_push
from notifications.tasks import send_push_task

OWNER = "notifications/push_publisher.py"


# ═══════════════════════════════════════════════════════════════════
#  عقد Celery — نُثبته لا نفترضه
# ═══════════════════════════════════════════════════════════════════


def test_the_worker_falls_back_to_its_own_setting_on_a_null_header():
    """ترويسة فارغة ليست خطراً: `soft_time_limit or task.soft_time_limit`.

    الرسائل السابقة لهذا الخطّ تحمل `[null, null]`، فيُنفّذها عاملٌ جديد بحدّه
    هو. الحارس هنا يُثبت أن الاعتماد على ذلك مبنيٌّ على مصدر Celery لا على ظنّ —
    فلو تغيّر السطر في ترقيةٍ لاحقة سقط هذا الاختبار قبل أن يسقط الإنتاج.
    """
    import celery
    from celery.worker import request as celery_request

    source = pathlib.Path(celery_request.__file__).read_text(encoding="utf-8")

    assert (
        "soft_timeout=soft_time_limit or task.soft_time_limit" in source
    ), f"تغيّر عقد Celery {celery.__version__} — أعد فحص فرضية السقوط إلى إعداد العامل"


def test_the_task_attribute_alone_is_not_the_source_of_truth():
    """السمة تُقرأ من إعدادات **عملية الناشر**، فهي ليست ضماناً موزَّعاً."""
    import celery.app.task as celery_task

    source = pathlib.Path(celery_task.__file__).read_text(encoding="utf-8")
    extractor = source[source.index("extract_exec_options = mattrgetter(") :][:400]

    assert "'soft_time_limit'" in extractor, "لم تعد السمة تُلتقط عند النشر"
    assert send_push_task.soft_time_limit == settings.PUSH_SOFT_TIME_LIMIT_SECONDS


# ═══════════════════════════════════════════════════════════════════
#  الضبط السالب — يُمنع قبل بلوغ الوسيط
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_longer_limit_is_refused_before_any_message_is_published(settings_broker_spy):
    """`soft_time_limit=300` — الحالة التي فتحت هذه البوابة."""
    with pytest.raises(ValueError, match="300"):
        enqueue_push(
            user_id="00000000-0000-0000-0000-000000000001",
            school_id="00000000-0000-0000-0000-000000000002",
            title="t",
            body="b",
            soft_time_limit=300,
        )

    assert settings_broker_spy.published == [], "وصلت رسالة إلى الوسيط رغم الرفض"


@pytest.mark.django_db
@pytest.mark.parametrize("value", [300, 5, 0, None])
def test_no_noncanonical_soft_limit_survives(settings_broker_spy, value):
    """أطولُ من المعتمد وأقصرُ منه وصفرٌ و`None` — كلّها ليست المعتمد."""
    if value == canonical_soft_time_limit():
        pytest.skip("هذه هي القيمة المعتمدة نفسها")

    with pytest.raises(ValueError):
        enqueue_push(
            user_id="00000000-0000-0000-0000-000000000001",
            school_id="00000000-0000-0000-0000-000000000002",
            title="t",
            body="b",
            soft_time_limit=value,
        )

    assert settings_broker_spy.published == []


@pytest.mark.django_db
def test_a_hard_limit_is_refused_too(settings_broker_spy):
    """الحدّ الصلب يقتل بـ`SIGKILL` فلا يترك للعامل فرصة كتابة نهايته."""
    with pytest.raises(ValueError, match="time_limit"):
        enqueue_push(
            user_id="00000000-0000-0000-0000-000000000001",
            school_id="00000000-0000-0000-0000-000000000002",
            title="t",
            body="b",
            time_limit=60,
        )

    assert settings_broker_spy.published == []


@pytest.mark.django_db
def test_the_canonical_value_is_accepted(settings_broker_spy):
    """التمريرُ الصريح المطابق مقبول — الرفض للاختلاف لا للتصريح."""
    enqueue_push(
        user_id="00000000-0000-0000-0000-000000000001",
        school_id="00000000-0000-0000-0000-000000000002",
        title="t",
        body="b",
        soft_time_limit=canonical_soft_time_limit(),
    )

    assert len(settings_broker_spy.published) == 1


# ═══════════════════════════════════════════════════════════════════
#  ما يُشحن فعلاً
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_normal_publish_carries_the_canonical_limit(settings_broker_spy):
    """`enqueue_push` العادي يشحن المعتمد صراحةً — لا يتركه للسمة."""
    enqueue_push(
        user_id="00000000-0000-0000-0000-000000000001",
        school_id="00000000-0000-0000-0000-000000000002",
        title="t",
        body="b",
    )

    (options,) = settings_broker_spy.published
    assert options["soft_time_limit"] == settings.PUSH_SOFT_TIME_LIMIT_SECONDS
    assert options.get("time_limit") is None


@override_settings(PUSH_SOFT_TIME_LIMIT_SECONDS=90)
@pytest.mark.django_db
def test_the_shipped_limit_follows_the_setting_not_a_constant(settings_broker_spy):
    """لا رقم مكرّر في الناشر: تغييرُ الإعداد يُغيّر ما يُشحن."""
    enqueue_push(
        user_id="00000000-0000-0000-0000-000000000001",
        school_id="00000000-0000-0000-0000-000000000002",
        title="t",
        body="b",
    )

    (options,) = settings_broker_spy.published
    assert options["soft_time_limit"] == 90


# ═══════════════════════════════════════════════════════════════════
#  حارس المنتجين
# ═══════════════════════════════════════════════════════════════════


def _direct_publishes(text):
    """`send_push_task.delay(...)` أو `.apply_async(...)` أو `.s(...)`."""
    published = []

    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue

        if node.func.attr not in ("delay", "apply_async", "s", "signature"):
            continue

        target = node.func.value

        if isinstance(target, ast.Name) and target.id == "send_push_task":
            published.append(f"{node.lineno} .{node.func.attr}()")

    return published


def test_no_producer_publishes_send_push_directly():
    """حارس: الطريق إلى الوسيط واحد.

    الجرد اليدوي لا يكفي — منتجٌ رابع قد يظهر غداً في View أو أمر إدارة، فينشر
    بإعدادات عمليته هو. والحارس يمسكه في المراجعة لا في الإنتاج.
    """
    root = pathlib.Path(settings.BASE_DIR)
    offenders = []

    for path in root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")

        if (
            rel == OWNER
            or rel.startswith((".venv", ".claude/", "tests/", "staticfiles/"))
            or "migrations" in rel
        ):
            continue

        for hit in _direct_publishes(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(f"{rel}:{hit}")

    assert offenders == [], f"نشرٌ مباشر خارج المالك: {offenders}"


def test_the_producer_guard_catches_a_real_violation():
    """ضبطٌ سالب: حارسٌ لا يسقط أمام مخالفة ليس حارساً."""
    violations = (
        "send_push_task.delay('u', 't', 'b')",
        "send_push_task.apply_async(args=('u',), soft_time_limit=300)",
        "send_push_task.s('u', 't', 'b')",
        "send_push_task.signature(('u',))",
    )

    for source in violations:
        assert _direct_publishes(source), f"لم يُمسك: {source}"

    # ولا يُعاقب النشر عبر المالك ولا استيراد المهمّة لقراءتها.
    for source in (
        "enqueue_push(user_id=u, school_id=s, title='t', body='b')",
        "print(send_push_task.name)",
    ):
        assert not _direct_publishes(source), f"عوقب مشروع: {source}"


# ═══════════════════════════════════════════════════════════════════
#  صفرُ نشرٍ — عند آخر نقطة قبل الوسيط
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def amqp_spy():
    """يراقب `AMQP.send_task_message` — آخر ما يسبق اتصال الوسيط.

    مراقبةُ `apply_async` تُثبت أن **مسار النشر لم يُدخَل**، وهي أضعف: لو نشر
    الكود يوماً بطريقٍ آخر لبقي الحارس أخضر. وهذه الطبقة تلتقط كل نشرٍ مهما كان
    طريقه، فالادّعاء يصير "لم تُنشأ رسالة" لا "لم تُستدعَ دالّة".
    """
    from unittest.mock import patch

    # الوضع الفوري يجعل `apply_async` تُنفّذ محلياً بلا نشر إطلاقاً — فيصير
    # "صفر رسائل" صحيحاً بلا معنى. إطفاؤه هنا هو ما يجعل هذا الشاهد شاهداً.
    #
    # والإطفاء عبر إعداد Django لا عبر `app.conf`: الأخير مربوطٌ بـ
    # `config_from_object("django.conf:settings")`، فالكتابة عليه مباشرةً
    # يبتلعها إعداد Django عند القراءة التالية — جرّبتُها فبقيت `True`.
    app = send_push_task.app

    messages = []

    def _spy(producer, name, message, **options):
        messages.append({"task": name, "options": options})

        class _Result:
            id = "amqp-spy"

        return _Result()

    # `send_task_message` خاصيّةٌ مُخزَّنة على **النسخة** لا دالّة على الصنف
    # (`@cached_property` تُعيد إغلاقاً من `_create_task_sender`)، فالترقيع على
    # الصنف لا يصلها.
    with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
        with patch.object(app.amqp, "send_task_message", _spy):
            yield messages


@pytest.mark.django_db
def test_a_rejected_publish_creates_no_message_at_all(amqp_spy):
    """`soft=300`: لا رسالة تُبنى ولا تُسلَّم إلى مُنتِج الوسيط."""
    with pytest.raises(ValueError, match="300"):
        enqueue_push(
            user_id="00000000-0000-0000-0000-000000000001",
            school_id="00000000-0000-0000-0000-000000000002",
            title="t",
            body="b",
            soft_time_limit=300,
        )

    assert amqp_spy == [], f"بُنيت رسالة رغم الرفض: {amqp_spy}"


@pytest.mark.django_db
def test_an_accepted_publish_does_reach_the_broker_layer(amqp_spy):
    """الضبط الموجب: الحارس أعلاه يُثبت شيئاً فقط إن كان النشر يصل أصلاً."""
    enqueue_push(
        user_id="00000000-0000-0000-0000-000000000001",
        school_id="00000000-0000-0000-0000-000000000002",
        title="t",
        body="b",
    )

    assert len(amqp_spy) == 1
    assert amqp_spy[0]["task"] == "notifications.send_push"
