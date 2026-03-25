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
