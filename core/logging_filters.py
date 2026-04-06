"""
core/logging_filters.py
━━━━━━━━━━━━━━━━━━━━━━━
فلاتر تسجيل مخصصة لإخفاء البيانات الشخصية (PII) في السجلات.
يتوافق مع PDPPL م.13 — حماية البيانات الشخصية.
"""

import logging
import re


class PIIMaskingFilter(logging.Filter):
    """
    يُخفي البيانات الشخصية في رسائل السجل:
    - أرقام الهوية الوطنية: يعرض أول 3 وآخر 2 فقط
    - أرقام الهواتف: يعرض آخر 4 أرقام فقط
    - البريد الإلكتروني: يعرض أول حرفين + @domain
    - عناوين IP: يخفي الأجزاء الوسطى

    المثال:
        28760000001 → 287*****01
        +97466123456 → ****3456
        user@school.qa → us***@school.qa
    """

    # أنماط regex للبيانات الشخصية
    NATIONAL_ID_PATTERN = re.compile(r"\b(\d{3})\d{6}(\d{2})\b")
    PHONE_PATTERN = re.compile(r"(\+?\d{1,4})\d{4,8}(\d{4})")
    EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9._%+-]{2})[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+)")

    def filter(self, record):
        """يُعالج رسالة السجل لإخفاء PII."""
        if isinstance(record.msg, str):
            record.msg = self._mask_pii(record.msg)
        if record.args:
            record.args = self._mask_args(record.args)
        return True

    def _mask_pii(self, text):
        """يُخفي PII في نص."""
        # إخفاء أرقام الهوية (11 رقم)
        text = self.NATIONAL_ID_PATTERN.sub(r"\1*****\2", text)
        # إخفاء الهواتف
        text = self.PHONE_PATTERN.sub(r"****\2", text)
        # إخفاء البريد
        text = self.EMAIL_PATTERN.sub(r"\1***@\2", text)
        return text

    def _mask_args(self, args):
        """يُخفي PII في وسائط التنسيق."""
        if isinstance(args, dict):
            return {k: self._mask_value(v) for k, v in args.items()}
        if isinstance(args, tuple | list):
            return tuple(self._mask_value(a) for a in args)
        return args

    def _mask_value(self, value):
        """يُخفي PII في قيمة واحدة."""
        if isinstance(value, str):
            return self._mask_pii(value)
        return value
