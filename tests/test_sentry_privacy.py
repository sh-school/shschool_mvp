"""[B4-7N] عقد الخصوصية والإشارة في طبقة Sentry.

طبقتان تحرسان الخصوصية عندنا، وكلتاهما تُنقّي **البريد والهاتف ورقم الهوية**
بأنماط. وما لا شكل له — الاسم وعنوان الإشعار ونصّه — لا يحرسه نمط، بل اسم
المفتاح. وهذا الملفّ يُثبت الاثنين معاً، ويُثبت أيضاً أن ما نحتاج رؤيته يصل.

والاختبارات هنا تُغذّي `before_send` و`_scrub_event_pii` بأشكال الأحداث التي
تُنتجها المكتبة فعلاً — لا بأشكالٍ نتخيّلها.
"""

import pytest

from core import sentry_config
from core.sentry_config import _scrub_event_pii, before_send

EMAIL = "parent@school.qa"
PHONE = "+97466123456"
QID = "28760000001"
ARABIC_NAME = "أحمد محمد الكواري"
NOTIFICATION_TITLE = "استدعاء ولي أمر — أحمد محمد"


# ═══════════════════════════════════════════════════════════════════
#  LogEntry — المسار الذي تسلكه كل `logger.error` عندنا
# ═══════════════════════════════════════════════════════════════════


def _logentry_event():
    """شكل الحدث كما تبنيه `LoggingIntegration` — لا `event["message"]`."""
    return {
        "level": "error",
        "logentry": {
            "message": "enqueue failed for %s / %s",
            "params": [EMAIL, PHONE],
            "formatted": f"enqueue failed for {EMAIL} / {PHONE}",
        },
    }


@pytest.mark.parametrize("field", ["message", "formatted", "params"])
def test_logentry_is_scrubbed(field):
    """الحقول الثلاثة كلّها — لا واحدٌ منها.

    `formatted` هو ما يعرضه Sentry، و`params` ما يُخزَّن للبحث، و`message`
    القالب. تنقيةُ بعضها تُبقي التسريب في الباقي.
    """
    scrubbed = _scrub_event_pii(_logentry_event())
    value = str(scrubbed["logentry"][field])

    assert EMAIL not in value, f"البريد نجا في logentry.{field}"
    assert PHONE not in value, f"الهاتف نجا في logentry.{field}"


def test_logentry_params_keep_their_shape():
    """التنقية لا تُحوّل القائمة إلى نصّ — Sentry يقرأها كعناصر."""
    scrubbed = _scrub_event_pii(_logentry_event())
    params = scrubbed["logentry"]["params"]

    assert isinstance(params, list)
    assert len(params) == 2


def test_logentry_scrubbing_is_what_makes_it_pass():
    """ضبطٌ سالب: بلا فرع `logentry` يمرّ البريد كما هو.

    يُحاكي الشيفرة السابقة — تنقية `event["message"]` وحده — ويُثبت أنها لا
    تمسّ الحدث الذي نُنتجه فعلاً.
    """
    event = _logentry_event()

    if "message" in event:  # pragma: no cover — الفرع القديم لا يجد المفتاح
        event["message"] = "scrubbed"

    assert EMAIL in event["logentry"]["formatted"]


# ═══════════════════════════════════════════════════════════════════
#  متغيّرات الإطارات — حيث يعيش الاسم والعنوان
# ═══════════════════════════════════════════════════════════════════


def _exception_event(**frame_vars):
    return {
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": f"SMTP refused for {EMAIL} / {PHONE} / {QID}",
                    "stacktrace": {"frames": [{"vars": dict(frame_vars)}]},
                }
            ]
        }
    }


def _scrubbed_vars(**frame_vars):
    scrubbed = _scrub_event_pii(_exception_event(**frame_vars))
    return scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("full_name", ARABIC_NAME),
        ("student_name", ARABIC_NAME),
        ("parent_name", ARABIC_NAME),
        ("recipient_name", ARABIC_NAME),
        ("display_name", ARABIC_NAME),
        ("title", NOTIFICATION_TITLE),
        ("subject", NOTIFICATION_TITLE),
        ("body", "تم تسجيل مخالفة من الدرجة الثانية"),
        ("body_text", "نصّ"),
        ("body_html", "<p>نصّ</p>"),
        ("message_text", "نصّ"),
        ("notification_title", NOTIFICATION_TITLE),
        ("notification_body", "نصّ"),
        ("recipient_email", EMAIL),
        ("phone_number", PHONE),
    ],
)
def test_semantic_pii_keys_are_redacted(key, value):
    """الاسم لا شكل له — فالمفتاح وحده يحرسه."""
    assert _scrubbed_vars(**{key: value})[key] == "[REDACTED]"


@pytest.mark.parametrize(
    "key",
    ["task_name", "event_name", "filename", "school_name", "logger_name", "queue_name"],
)
def test_useful_names_survive(key):
    """ضبطٌ سالب على الحارس نفسه: مطابقةٌ فضفاضة تُفقدنا رصداً نافعاً.

    `name` كمقطعٍ داخل المفتاح كان سيحجب هذه كلّها — وهي ما نحتاجه لتشخيص
    عطبٍ في مهمّة أو طابور.
    """
    assert _scrubbed_vars(**{key: "notifications.send_email"}) == {key: "notifications.send_email"}


def test_exception_value_is_still_scrubbed():
    """ما كان يعمل يبقى يعمل — الأنماط على قيمة الاستثناء."""
    scrubbed = _scrub_event_pii(_exception_event())
    value = scrubbed["exception"]["values"][0]["value"]

    assert "[EMAIL_REDACTED]" in value
    assert "[PHONE_REDACTED]" in value
    assert "[QID_REDACTED]" in value


# ═══════════════════════════════════════════════════════════════════
#  الإشارة — ما يجب أن يصل، وما يجب أن يُسقط
# ═══════════════════════════════════════════════════════════════════


def _hint(exc_type):
    return {"exc_info": (exc_type, exc_type("boom"), None)}


@pytest.mark.parametrize(
    "exc_type",
    [ConnectionResetError, BrokenPipeError],
    ids=["connection_reset", "broken_pipe"],
)
def test_client_disconnect_is_dropped(exc_type):
    """المستخدم أغلق المتصفّح — ضوضاءٌ لا تخصّ الكود."""
    assert before_send({}, _hint(exc_type)) is None


def test_django_noise_is_dropped_by_identity_not_by_string():
    """الأسماء المؤهَّلة الحقيقية لا التي كانت مكتوبة.

    القائمة السابقة كتبت `django.security.DisallowedHost`، والاسم الحقيقي
    `django.core.exceptions.DisallowedHost` — فلم تُسقط شيئاً قطّ. والمطابقة
    بالصنف لا تعرف هذا الخطأ أصلاً.
    """
    from django.core.exceptions import DisallowedHost
    from django.http import Http404

    assert before_send({}, _hint(DisallowedHost)) is None
    assert before_send({}, _hint(Http404)) is None


@pytest.mark.parametrize(
    "exc_type",
    [ConnectionError, TimeoutError, OSError],
    ids=["connection_error", "timeout_error", "os_error"],
)
def test_generic_connection_failures_are_kept(exc_type):
    """أحداثٌ تشغيلية لا ضوضاء: Redis أو SMTP أو قاعدة أو مزوّد."""
    assert before_send({}, _hint(exc_type)) is not None


def test_the_broker_error_we_built_for_reaches_sentry():
    """`OperationalError` هو ما يرفعه Kombu عند سقوط الوسيط.

    أصلحنا التقاطه في B4-7G تحديداً كي نراه — فابتلاعُه هنا يُبطل ذلك العمل.
    """
    from kombu.exceptions import OperationalError

    assert before_send({}, _hint(OperationalError)) is not None


def test_redis_connection_error_is_kept():
    """ضبطٌ سالب للمطابقة النصّية: `"ConnectionError" in "redis…ConnectionError"`.

    كانت المطابقة بالاحتواء تُسقط هذا صامتاً — وهو أوّل ما نحتاج رؤيته على
    العامل.
    """
    from redis.exceptions import ConnectionError as RedisConnectionError

    assert before_send({}, _hint(RedisConnectionError)) is not None


def test_the_ignore_list_is_small_and_named():
    """حارسٌ ضدّ التوسّع الصامت: كل إضافةٍ إلى القائمة قرارٌ يُراجَع."""
    ignored = sentry_config.ignored_exception_types()

    assert len(ignored) == 5, [t.__name__ for t in ignored]
    assert ConnectionError not in ignored
    assert TimeoutError not in ignored


# ═══════════════════════════════════════════════════════════════════
#  حدود المكتبة — ما لا نتحكّم فيه بالكود بل بالإعداد
# ═══════════════════════════════════════════════════════════════════


def test_celery_task_arguments_stay_suppressed():
    """`send_default_pii=False` يمنع إرسال وسائط المهامّ — من مصدر المكتبة.

    وهي أخطر حمولةٍ عندنا: `hub_send` تحمل `title` و`body`. فلو قُلبت الراية
    يوماً لخرج محتوى الإشعارات كلّه، ولا `before_send` يعرف أنه محتوى.
    """
    import inspect

    from sentry_sdk.integrations import celery as celery_integration

    source = inspect.getsource(celery_integration)

    # العقد من مصدر المكتبة لا من ذاكرتنا عنه: الوسائط تُبدَّل بحاجزٍ ثابت ما
    # لم تُفتح الراية.
    assert 'extra["celery-job"]' in source
    assert "should_send_default_pii()" in source
    assert "SENSITIVE_DATA_SUBSTITUTE" in source


def test_production_keeps_default_pii_off():
    """والراية نفسها — لأن العقد أعلاه بلا قيمة إن قُلبت."""
    import pathlib

    settings_source = pathlib.Path("shschool/settings/production.py").read_text(encoding="utf-8")

    assert "send_default_pii=False" in settings_source


def test_school_name_is_not_sent_to_sentry():
    """اسم المستأجر لا يُضاف إلى النطاق — المُعرِّف يكفي للتشخيص.

    والقراءة من الملفّ بالشجرة لا بـ`inspect.getsource`: الأخيرة تربط النتيجة
    بأرقام الأسطر في الكائن المُترجَم وقت الاستيراد، فتُعيد دالّةً أخرى إن
    تغيّر الملفّ بعده — ولو كان التغيير تعليقاً. حارسٌ يكسره تعليق ليس حارساً.
    """
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(sentry_config.__file__).read_text(encoding="utf-8"))

    scope_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "configure_sentry_scope"
    )

    tags = {
        node.args[0].value
        for node in ast.walk(scope_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_tag"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }

    assert "school.id" in tags, f"مُعرِّف المدرسة غاب عن النطاق: {sorted(tags)}"
    assert "school.name" not in tags, "اسم المدرسة عاد إلى telemetry"


# ═══════════════════════════════════════════════════════════════════
#  متانة `before_send` — لأن سقوطه يُنتج فقداناً صامتاً
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("label", "hint"),
    [
        ("missing", {}),
        ("none", {"exc_info": None}),
        ("empty_tuple", {"exc_info": ()}),
        ("none_type", {"exc_info": (None, None, None)}),
        ("string_not_class", {"exc_info": ("ValueError", None, None)}),
        ("instance_not_class", {"exc_info": (object(), None, None)}),
        ("class_not_exception", {"exc_info": (dict, None, None)}),
    ],
)
def test_before_send_never_raises_on_a_malformed_hint(label, hint):
    """استثناءٌ داخل `before_send` يُسقط الحدث بلا أثر — أسوأ من عدم التصفية.

    و`issubclass` ترفع `TypeError` على ما ليس صنفاً، فالحارس يشترط `type` أولاً.
    """
    event = {"logentry": {"formatted": f"probe {EMAIL}"}}

    result = before_send(event, hint)

    assert result is not None, f"أُسقط حدثٌ سليم عند {label}"
    assert EMAIL not in result["logentry"]["formatted"], "التنقية لم تقع"


def test_scrubbing_does_not_depend_on_key_order():
    """الحكم لا يتعلّق بترتيب المفاتيح — القواميس تُبنى بترتيبٍ لا نتحكّم فيه."""
    forward = {"logentry": {"message": "%s", "params": [EMAIL], "formatted": EMAIL}}
    reversed_order = {"logentry": {"formatted": EMAIL, "params": [EMAIL], "message": "%s"}}

    assert _scrub_event_pii(forward)["logentry"] == _scrub_event_pii(reversed_order)["logentry"]
