"""[B4-7P] رصد المُصالِح — قناةٌ واحدة ضيّقة إلى stdout.

مُعالِج `file` في الإنتاج يكتب داخل حاويةٍ زائلة لا تُقرأ بأي أداة عندنا. فما
لا يبلغ stdout لا يبلغ Railway، ولا يُقرأ أبداً — ومُصالِحٌ دوريّ لا يُرى يعمل
في الظلام.

والقناة **ضيّقة عمداً**: `notifications` كلّها تحمل سجلّات مهامّ التسليم
بتتبّعات استثناءات المزوّدين. فيُثبَت هنا الحدّان معاً — أن المُصالِح يظهر، وأن
غيره لا يظهر بسببنا.
"""

import io
import logging

import pytest
from django.conf import settings

from notifications import reconciler

CONSOLE_LOGGER = "notifications.reconciler"
QUIET_LOGGERS = ["notifications.tasks", "notifications.hub", "notifications"]


# ═══════════════════════════════════════════════════════════════════
#  إعداد الإنتاج — الحدّان الموجب والسالب
# ═══════════════════════════════════════════════════════════════════


def _production_loggers():
    """قاموس `LOGGING["loggers"]` من ملفّ الإنتاج — بالشجرة لا بالاستيراد.

    استيراد `production.py` يُنفّذها: تتحقّق من الأسرار، وتُقلع Sentry، وتفتح
    اتصالات. والمطلوب قراءة إعدادٍ ساكن، فالشجرة أصدق وأرخص. و`loggers` قيمٌ
    حرفية بالكامل — بخلاف `handlers` التي تحوي `BASE_DIR / …` وحسابات.
    """
    import ast
    import pathlib

    path = pathlib.Path(settings.BASE_DIR) / "shschool" / "settings" / "production.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)):
            continue
        if not any(getattr(t, "id", None) == "LOGGING" for t in node.targets):
            continue

        for key, value in zip(node.value.keys, node.value.values, strict=False):
            if isinstance(key, ast.Constant) and key.value == "loggers":
                return ast.literal_eval(value)

    raise AssertionError("لم يُعثر على LOGGING['loggers'] في production.py")


def test_the_reconciler_has_its_own_console_channel():
    """الحدّ الموجب — وسطرٌ في القاموس لا يكفي وحده، لكنه شرطٌ لازم."""
    config = _production_loggers()[CONSOLE_LOGGER]

    assert config["handlers"] == ["console"]
    assert config["level"] == "INFO"
    assert config["propagate"] is False, "الصعود إلى `notifications` يُنتج نسخةً في الملفّ"


def _effective_handlers(name, loggers):
    """المُعالِجات التي تُصيب هذا المُسجِّل فعلاً — كما يحلّها `logging`.

    `notifications.tasks` بلا إعدادٍ صريح، فيرث `notifications`. وفحصُ القاموس
    بالاسم وحده كان يرفع `KeyError` ويُخفي أن الإرث هو ما يحكم.
    """
    handlers = []
    parts = name.split(".")

    while parts:
        config = loggers.get(".".join(parts))

        if config:
            handlers.extend(config.get("handlers", []))
            if not config.get("propagate", True):
                return handlers

        parts.pop()

    return handlers


@pytest.mark.parametrize("name", QUIET_LOGGERS)
def test_no_other_notification_logger_gains_console(name):
    """الحدّ السالب — لا نفتح الوحدة كلّها من باب فتح المُصالِح."""
    handlers = _effective_handlers(name, _production_loggers())

    assert "console" not in handlers, f"{name} صار مرئياً على stdout — النطاق اتّسع"


def test_the_resolver_sees_inherited_configuration():
    """ضبطٌ موجب على الحلّال نفسه: حارسٌ يقرأ القاموس حرفياً لا يحرس الإرث."""
    loggers = {
        "notifications": {"handlers": ["file"], "propagate": False},
        "notifications.reconciler": {"handlers": ["console"], "propagate": False},
    }

    assert _effective_handlers("notifications.tasks", loggers) == ["file"]
    assert _effective_handlers("notifications.reconciler", loggers) == ["console"]


# ═══════════════════════════════════════════════════════════════════
#  السلوك الفعليّ — مُسجِّلٌ حقيقيّ ونصٌّ خارج
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def console():
    """يُحاكي إعداد الإنتاج: `console` على المُصالِح وحده، بلا صعود.

    ويُعاد الضبط في `finally` كي لا يتسرّب إلى بقيّة الحزمة.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))

    target = logging.getLogger(CONSOLE_LOGGER)
    previous_handlers = target.handlers[:]
    previous_propagate = target.propagate
    previous_level = target.level

    target.handlers = [handler]
    target.propagate = False
    target.setLevel(logging.INFO)

    try:
        yield stream
    finally:
        target.handlers = previous_handlers
        target.propagate = previous_propagate
        target.setLevel(previous_level)


def _emit(monkeypatch, counts, limit=200):
    """يُشغّل `reconcile_school` بمراحل مُستبدَلة تُعيد أعداداً معلومة.

    الغرض رصدُ ما يُكتب لا اختبار المراحل — ولها اختباراتها. والاستبدال يجعل
    الاختبار بلا قاعدة بيانات، فيبقى سريعاً ومركّزاً على السطر الخارج.
    """
    for stage, value in counts.items():
        monkeypatch.setattr(reconciler, stage, lambda *a, value=value, **k: value)

    return reconciler.reconcile_school("7457eaed-1111-2222-3333-444455556666", limit=limit)


ZERO = {
    "close_expired_leases": 0,
    "close_exhausted_deliveries": 0,
    "requeue_stale_deliveries": 0,
    "scrub_completed_intents": 0,
}


def test_the_summary_reaches_the_console(console, monkeypatch):
    """السطر الدوريّ — بحقولٍ مسمّاة تُقرأ ويُبحَث فيها."""
    _emit(monkeypatch, {**ZERO, "requeue_stale_deliveries": 3})

    output = console.getvalue()

    assert "INFO" in output
    assert "reconcile school_id=7457eaed-1111-2222-3333-444455556666" in output
    assert "requeued=3" in output
    assert "batch=200" in output
    assert "saturated=none" in output


def test_saturation_raises_a_warning_that_names_the_stage(console, monkeypatch):
    """«حجمٌ كبير» لا يقول أين — والمراحل الأربع أسبابها مختلفة تماماً."""
    _emit(monkeypatch, {**ZERO, "requeue_stale_deliveries": 200})

    output = console.getvalue()

    assert "WARNING" in output
    assert "reconcile saturated" in output
    assert "stage=requeued" in output
    assert "count=200" in output
    assert "batch=200" in output


def test_every_saturated_stage_gets_its_own_warning(console, monkeypatch):
    """تشبّع `requeued` يعني وسيطاً يسقط، وتشبّع `scrubbed` تراكمَ محتوى.

    فتحذيرٌ واحد جامع كان يُخفي أيّهما وقع — وعلاجهما مختلف.
    """
    _emit(
        monkeypatch,
        {**ZERO, "requeue_stale_deliveries": 200, "scrub_completed_intents": 200},
    )

    output = console.getvalue()

    assert output.count("reconcile saturated") == 2
    assert "stage=requeued" in output
    assert "stage=scrubbed" in output
    assert "saturated=requeued,scrubbed" in output, "الملخّص لا يُسمّي المتشبّع"


def test_a_stage_below_the_batch_does_not_warn(console, monkeypatch):
    """ضبطٌ سالب: 199 من 200 عملٌ كثيرٌ لا تشبّع."""
    _emit(monkeypatch, {**ZERO, "requeue_stale_deliveries": 199})

    output = console.getvalue()

    assert "saturated" not in output.replace("saturated=none", "")
    assert "WARNING" not in output


def test_the_summary_carries_no_personal_data(console, monkeypatch):
    """مُعرِّفٌ وأعدادٌ فقط — لا اسم ولا عنوان ولا وجهة اتصال.

    ولهذا لا يحتاج هذا السطر قناعاً: ما يُكتب فيه لا يحتمل PII بالبناء.
    """
    _emit(monkeypatch, {**ZERO, "close_expired_leases": 2})

    output = console.getvalue()

    assert "@" not in output, "عنوان بريد في سجلّ المُصالِح"
    assert "+974" not in output

    # كل رمزٍ في السطر إمّا كلمةٌ إنجليزية أو مُعرِّف أو رقم — لا نصّ عربيّ
    # (وهو ما يحمل الأسماء والعناوين عندنا).
    assert not any("؀" <= ch <= "ۿ" for ch in output), "نصّ عربيّ في سجلّ المُصالِح"


def test_the_returned_summary_shape_did_not_change(console, monkeypatch):
    """الرصد إضافةٌ لا تغيير: مَن يقرأ الملخّص برمجياً لا يتأثّر."""
    summary = _emit(monkeypatch, {**ZERO, "scrub_completed_intents": 1})

    assert set(summary) == {"unknown_outcome", "exhausted", "requeued", "scrubbed"}
    assert summary["scrubbed"] == 1
