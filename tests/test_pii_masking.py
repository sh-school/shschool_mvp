"""
tests/test_pii_masking.py
━━━━━━━━━━━━━━━━━━━━━━━━
اختبارات فلتر إخفاء البيانات الشخصية (PII) في السجلات.
"""

import logging

import pytest

from core.logging_filters import PIIMaskingFilter

pytestmark = pytest.mark.django_db


class TestPIIMaskingFilter:
    """اختبارات فلتر إخفاء PII."""

    def setup_method(self):
        self.filter = PIIMaskingFilter()

    def test_masks_national_id_11_digits(self):
        """يُخفي رقم الهوية الوطنية (11 رقم)."""
        result = self.filter._mask_pii("المستخدم 28760000001 سجّل دخول")
        assert "28760000001" not in result
        assert "287" in result  # أول 3 أرقام
        assert "01" in result  # آخر رقمين
        assert "*****" in result

    def test_masks_phone_number(self):
        """يُخفي رقم الهاتف."""
        result = self.filter._mask_pii("هاتف: +97466123456")
        assert "66123456" not in result
        assert "****" in result

    def test_masks_email(self):
        """يُخفي البريد الإلكتروني."""
        result = self.filter._mask_pii("البريد: user@school.qa")
        assert "user@" not in result
        assert "us***@school.qa" in result

    def test_preserves_non_pii_text(self):
        """يحتفظ بالنص العادي."""
        text = "هذا نص عادي بدون بيانات شخصية"
        result = self.filter._mask_pii(text)
        assert result == text

    def test_masks_multiple_pii_in_same_message(self):
        """يُخفي عدة بيانات شخصية في نفس الرسالة."""
        text = "المستخدم 28760000001 بريده user@school.qa"
        result = self.filter._mask_pii(text)
        assert "28760000001" not in result
        assert "user@" not in result

    def test_filter_modifies_log_record(self):
        """الفلتر يعدّل سجل الـ log."""
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="مستخدم 28760000001 فشل في الدخول",
            args=None,
            exc_info=None,
        )
        self.filter.filter(record)
        assert "28760000001" not in record.msg
        assert "287" in record.msg

    def test_filter_masks_args(self):
        """الفلتر يُخفي PII في وسائط التنسيق."""
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="فشل تسجيل دخول: %s",
            args=("28760000001",),
            exc_info=None,
        )
        self.filter.filter(record)
        assert "28760000001" not in str(record.args)

    def test_filter_handles_dict_args(self):
        """الفلتر يتعامل مع وسائط dict."""
        f = self.filter
        masked = f._mask_args({"user": "28760000001", "ip": "192.168.1.1"})
        assert "28760000001" not in str(masked)
        assert "287" in str(masked)


# ══════════════════════════════════════════════════════════════════
#  [B4-7N2] التتبّع — الحكم على النصّ الخارج لا على خصائص السجلّ
# ══════════════════════════════════════════════════════════════════

EMAIL = "parent@school.qa"
PHONE = "+97466123456"
QID = "28760000001"


@pytest.fixture
def emitted():
    """مُسجِّلٌ حقيقيّ ⇒ مُعالِج ⇒ فلتر ⇒ مُنسِّق ⇒ نصّ.

    الحكم على ما يخرج من المُعالِج لا على `LogRecord`: خاصّيةٌ نظيفة ومُنسِّقٌ
    يُعيد بناء التتبّع من `exc_info` تُنتجان تسريباً لا يراه اختبارُ الخاصّية.
    """
    import io
    import uuid

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handler.addFilter(PIIMaskingFilter())

    logger = logging.getLogger(f"pii-probe-{uuid.uuid4()}")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False

    def _text():
        handler.flush()
        return stream.getvalue()

    return logger, _text


def _assert_clean(text):
    assert EMAIL not in text, "البريد نجا في المخرَج"
    assert PHONE not in text, "الهاتف نجا في المخرَج"
    assert QID not in text, "رقم الهوية نجا في المخرَج"


def test_logger_exception_masks_the_traceback(emitted):
    """`logger.exception` — أشهر مسارٍ يحمل نصّ المزوّد."""
    logger, text = emitted

    try:
        raise ValueError(f"SMTP refused {EMAIL} / {PHONE} / {QID}")
    except ValueError:
        logger.exception("send failed")

    output = text()

    _assert_clean(output)
    assert "ValueError" in output, "ضاع نوع الاستثناء"
    assert "Traceback (most recent call last)" in output, "ضاع التتبّع"
    assert "***@school.qa" in output, "لم يُخفَ البريد بل حُذف"


def test_error_with_exc_info_masks_the_traceback(emitted):
    """`exc_info=True` — الصيغة التي استعملناها في 7O و7G."""
    logger, text = emitted

    try:
        raise RuntimeError(f"provider rejected {EMAIL}")
    except RuntimeError:
        logger.error("publish failed error=%s", "RuntimeError", exc_info=True)

    output = text()

    _assert_clean(output)
    assert "publish failed error=RuntimeError" in output


def test_the_whole_exception_chain_is_masked(emitted):
    """`raise X from Y` — التسريب قد يكون في السبب لا في الأثر."""
    logger, text = emitted

    try:
        try:
            raise KeyError(QID)
        except KeyError as cause:
            raise ValueError(f"lookup failed for {EMAIL}") from cause
    except ValueError:
        logger.exception("chained")

    output = text()

    _assert_clean(output)
    assert "KeyError" in output and "ValueError" in output, "ضاعت إحدى حلقتي السلسلة"


def test_a_prepopulated_exc_text_is_masked_too(emitted):
    """مُعالِجٌ سابق بنى `exc_text` — لا نثق بأنه بناه نظيفاً.

    وهذا يقع فعلاً عندنا: `file` و`console` معاً، فأوّلهما يبني والثاني يرث.
    """
    logger, text = emitted

    record = logger.makeRecord(logger.name, logging.ERROR, __file__, 0, "prebuilt", None, None)
    record.exc_text = f"Traceback…\nValueError: {EMAIL} / {PHONE}"

    logger.handle(record)

    _assert_clean(text())


def test_stack_info_is_masked(emitted):
    """`stack_info=True` نصٌّ آخر يُلحقه المُنسِّق."""
    logger, text = emitted

    record = logger.makeRecord(logger.name, logging.ERROR, __file__, 0, "with stack", None, None)
    record.stack_info = f"Stack (most recent call last):\n  value = {EMAIL}"

    logger.handle(record)

    _assert_clean(text())


def test_a_record_without_an_exception_is_unchanged(emitted):
    """السلوك القديم لا يتغيّر: لا تتبّع ⇒ لا `exc_text` مُختلَق."""
    logger, text = emitted

    logger.info("plain line with no pii")

    output = text()

    assert "plain line with no pii" in output
    assert "Traceback" not in output


def test_exc_info_true_outside_an_except_block_does_not_break(emitted):
    """`exc_info=True` بلا استثناءٍ جارٍ ⇒ `(None, None, None)`.

    الإخفاء لا يجوز أن يُسقط السجلّ — سطرٌ ناقص أهون من عمليةٍ تنهار.
    """
    logger, text = emitted

    logger.error("no active exception", exc_info=True)

    assert "no active exception" in text()


@pytest.mark.parametrize(
    "args",
    [
        (EMAIL,),
        (12345,),
        (None,),
        ({"recipient": EMAIL},),
    ],
    ids=["string", "int", "none", "dict_value"],
)
def test_arguments_still_work_alongside_traceback_masking(emitted, args):
    """التنقية القائمة على الوسائط لم تنكسر — ومعها أنواعٌ غير نصّية."""
    logger, text = emitted

    try:
        raise ValueError(f"boom {PHONE}")
    except ValueError:
        logger.error("value=%s", *args, exc_info=True)

    output = text()

    assert PHONE not in output
    assert EMAIL not in output


def test_masking_is_idempotent():
    """مُعالِجان ⇒ الفلتر يمرّ على النصّ مرّتين. الثانية يجب ألّا تُفسده."""
    masker = PIIMaskingFilter()

    once = masker._mask_pii(f"to {EMAIL} and {PHONE}")
    twice = masker._mask_pii(once)

    assert once == twice
