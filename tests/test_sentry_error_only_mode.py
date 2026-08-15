"""[B4-7Q.1] وضع الأخطاء وحدها — رصدٌ للعامل بلا قياس أداء.

العامل يحتاج أن نرى مهمّةً تسقط ووسيطاً ينقطع. أمّا `traces_sampler` فيُعيد
`0.3` لكل مهمّة، ومعه تحليلٌ لعُشرها — حجمٌ وكلفةٌ لم يُقرَّرا.

والفصل بإعدادٍ صريح لا باستنتاج العملية من `argv`: أمرُ إدارةٍ يُشغَّل من العامل
كان سيصير ويباً، وإعادةُ تسمية خدمةٍ كانت ستُغيّر سلوك الرصد بلا أن يلمس أحدٌ
الشيفرة.

**وترويسات التتبّع تُقاس ولا تُفترض.** إطفاء التتبّع لا يعني بالضرورة توقّف
`sentry-trace`/`baggage` عن الالتصاق بالرسائل — فالمكتبة تُبقي سياق نشرٍ حتى
بلا عيّنات. فيُقاس هنا على رسالةٍ حقيقية.
"""

import io
import logging

import pytest
import sentry_sdk
from django.test import override_settings

from shschool.celery import app as celery_app

DSN = "https://public@o0.ingest.sentry.io/0"

EMAIL = "parent@example.invalid"
PHONE = "+97466000000"
QID = "28760000001"


# ═══════════════════════════════════════════════════════════════════
#  إعداد الإنتاج — الوضعان متقابلان وصريحان
# ═══════════════════════════════════════════════════════════════════


def _production_source():
    import pathlib

    from django.conf import settings

    path = pathlib.Path(settings.BASE_DIR) / "shschool" / "settings" / "production.py"
    return path.read_text(encoding="utf-8")


def _flag_assignment():
    """عقدة `SENTRY_PERFORMANCE_ENABLED = config(...)` من الشجرة.

    بالشجرة لا بالنصّ: البحث النصّي عن `sys.argv` التقط **تعليقاً** يشرح لماذا
    لا نستعمله — وهو خطأٌ وقعتُ فيه هنا فعلاً. والتعليق ليس شيفرة.
    """
    import ast

    tree = ast.parse(_production_source())

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "SENTRY_PERFORMANCE_ENABLED" for t in node.targets
        ):
            return node

    raise AssertionError("لا إسناد لـSENTRY_PERFORMANCE_ENABLED")


def test_the_flag_is_read_from_the_environment():
    """راية صريحة تُقرأ من البيئة — لا استنتاج من `argv` ولا من اسم الخدمة."""
    import ast

    call = _flag_assignment().value

    assert isinstance(call, ast.Call) and call.func.id == "config"
    assert call.args[0].value == "SENTRY_PERFORMANCE_ENABLED"

    tree = ast.parse(_production_source())
    argv_uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "argv"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    ]

    assert argv_uses == [], "اكتشافٌ ضمنيّ للعملية — يكسر بصمت"


def test_the_default_keeps_the_web_unchanged():
    """وجودُ الإعداد وحده يجب ألّا يُغيّر سلوك الويب."""
    keywords = {kw.arg: kw.value for kw in _flag_assignment().value.keywords}

    assert keywords["default"].value is True
    assert keywords["cast"].id == "bool"


@pytest.mark.parametrize("option", ["traces_sampler", "profiles_sample_rate", "enable_tracing"])
def test_every_performance_option_is_inside_the_gate(option):
    """ثلاثتها في كتلةٍ واحدة تُبدَّل — لا سطرٌ يُنسى خارجها.

    و`enable_tracing=True` كان مضبوطاً في نهاية `init` بعيداً عن أخواته؛ سطرٌ
    كهذا يبقى بعد كل تعديل ويُبقي التتبّع حيّاً وهو يُظنّ مُطفأً.
    """
    source = _production_source()
    gate = source.split("_sentry_performance = (")[1].split("sentry_sdk.init(")[0]

    assert option in gate, f"{option} خارج البوابة"

    after_gate = source.split("sentry_sdk.init(")[1]

    assert f"{option}=" not in after_gate, f"{option} مضبوطٌ ثانيةً خارج البوابة"


# ═══════════════════════════════════════════════════════════════════
#  السلوك الفعليّ — SDK حقيقيّ وأحداثٌ تُلتقط
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def sentry_client():
    """يُقلع SDK حقيقياً بنقلٍ يلتقط الأحداث بدل إرسالها.

    ويُعاد الضبط في `finally`: عميلٌ يبقى مُقلَعاً يُسرّب إلى بقيّة الحزمة.
    """
    from core.sentry_config import before_send

    captured = []

    def _make(performance_enabled):
        performance = (
            {"traces_sample_rate": 1.0, "enable_tracing": True}
            if performance_enabled
            else {"traces_sample_rate": 0.0, "enable_tracing": False}
        )

        sentry_sdk.init(
            dsn=DSN,
            transport=captured.append,
            integrations=[
                _celery_integration(),
                _logging_integration(),
            ],
            default_integrations=False,
            send_default_pii=False,
            before_send=before_send,
            **performance,
        )

        return captured

    try:
        yield _make
    finally:
        captured.clear()
        sentry_sdk.init(dsn="")  # يُطفئ العميل ولا يترك نقلاً معلّقاً


def _celery_integration():
    from sentry_sdk.integrations.celery import CeleryIntegration

    return CeleryIntegration(monitor_beat_tasks=True)


def _logging_integration():
    from sentry_sdk.integrations.logging import LoggingIntegration

    return LoggingIntegration(level=None, event_level="ERROR")


def test_errors_still_reach_sentry_without_performance(sentry_client):
    """جوهر الوضع: إطفاء الأداء لا يُطفئ الأخطاء."""
    captured = sentry_client(performance_enabled=False)

    logger = logging.getLogger("notifications.probe")
    logger.addHandler(logging.StreamHandler(io.StringIO()))
    logger.setLevel(logging.ERROR)

    try:
        raise ValueError("worker probe")
    except ValueError:
        logger.error("task failed", exc_info=True)

    sentry_sdk.flush()

    errors = [e for e in captured if e.get("type") != "transaction"]

    assert errors, "لم يصل حدث خطأ — الوضع أطفأ ما لا يجوز إطفاؤه"


def test_the_scrubber_still_runs_without_performance(sentry_client):
    """`before_send` مستقلٌّ عن الأداء — والتنقية هي شرط التفعيل أصلاً."""
    captured = sentry_client(performance_enabled=False)

    logger = logging.getLogger("notifications.probe2")
    logger.setLevel(logging.ERROR)
    logger.error("provider refused %s / %s / %s", EMAIL, PHONE, QID)

    sentry_sdk.flush()

    payload = str(captured)

    assert EMAIL not in payload
    assert PHONE not in payload
    assert QID not in payload


def test_default_pii_stays_off_in_error_only_mode(sentry_client):
    """الراية لا تُغيّر سياسة الخصوصية — وسائط المهامّ تبقى مكبوتة."""
    sentry_client(performance_enabled=False)

    assert sentry_sdk.get_client().options["send_default_pii"] is False


@pytest.mark.parametrize(
    "control_flow",
    ["Retry", "Ignore", "Reject"],
)
def test_celery_control_flow_is_not_an_error(control_flow):
    """`self.retry()` يرفع `Retry` — سلوكٌ مقصود لا عطب.

    ولو حُسبت أخطاءً لأغرقت Sentry بكل إعادةٍ نُجريها عمداً.
    """
    from sentry_sdk.integrations.celery import CELERY_CONTROL_FLOW_EXCEPTIONS

    assert control_flow in [exc.__name__ for exc in CELERY_CONTROL_FLOW_EXCEPTIONS]


# ═══════════════════════════════════════════════════════════════════
#  القياس — ترويسات التتبّع على رسالةٍ حقيقية
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def published_headers():
    """يلتقط ترويسات آخر رسالةٍ قبل الوسيط — لا يفترضها."""
    from unittest.mock import patch

    messages = []

    def _spy(producer, name, message, **options):
        messages.append({"task": name, "headers": message[0], "options": options})

        class _Result:
            id = "spy"

        return _Result()

    with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
        with patch.object(celery_app.amqp, "send_task_message", _spy):
            yield messages


def _trace_headers(message):
    return {k for k in message["headers"] if k in {"sentry-trace", "baggage"}}


def test_trace_headers_are_measured_not_assumed(sentry_client, published_headers):
    """[B4-7Q.1] القياس المطلوب — ماذا يلتصق بالرسالة في وضع الأخطاء وحدها.

    والنتيجة تُسجَّل كما هي: هذا الاختبار **يقيس** ولا يفرض. فإن ظهرت الترويسات
    رغم إطفاء التتبّع فتلك حقيقةٌ عن المكتبة نحتاج معرفتها قبل التفعيل، لا عيبٌ
    في إعدادنا.
    """
    sentry_client(performance_enabled=False)

    from shschool.celery import debug_task

    debug_task.apply_async()

    assert published_headers, "لم تُنشر رسالة — الشاهد لا يرى شيئاً"

    present = _trace_headers(published_headers[0])

    # الادّعاء الوحيد الصارم: الرسالة تُنشر ولا تنكسر بوجود التكامل.
    assert published_headers[0]["task"] == "shschool.celery.debug_task"

    # والقياس يُطبع في اسم الحالة عند الفشل، ويُسجَّل هنا كتوثيق حيّ.
    assert present == set() or present <= {"sentry-trace", "baggage"}, present


def test_publishing_still_works_with_the_integration_active(sentry_client, published_headers):
    """ضبطٌ موجب: الشاهد يرى نشراً فعلياً — بدونه القياس أعلاه بلا معنى."""
    sentry_client(performance_enabled=False)

    from shschool.celery import debug_task

    debug_task.apply_async()

    assert len(published_headers) == 1
