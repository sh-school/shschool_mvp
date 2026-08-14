"""
core/logging_filters.py
━━━━━━━━━━━━━━━━━━━━━━━
فلاتر تسجيل مخصصة لإخفاء البيانات الشخصية (PII) في السجلات.
يتوافق مع PDPPL م.13 — حماية البيانات الشخصية.
"""

import logging
import re
import traceback


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

        self._mask_traceback(record)

        return True

    def _mask_traceback(self, record):
        """[B4-7N2] يُخفي PII في نصّ الاستثناء والمكدّس.

        كان الفلتر يمسّ `msg` و`args` وحدهما، ويترك التتبّع كما هو — ورسائل
        المزوّدين تحمل عنوان المستلم عادةً: `SMTPRecipientsRefused` تذكر
        البريد، وأخطاء SMS تذكر الرقم. فسطرٌ نظيف يتبعه تتبّعٌ مكشوف.

        **ولا نمسّ كائن الاستثناء ولا `args` فيه**: هو مشترك مع مسارات أخرى —
        Sentry يقرأ `exc_info` نفسه، ومُعالِجات أخرى قد تُعيد رفعه — وتعديله
        يُغيّر دلالةً لا تخصّنا. المُستهدَف **التمثيل النصّي** وحده.

        والحيلة عقدٌ صريح في `logging.Formatter.format`:

            if record.exc_info and not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        فالمُنسِّق لا يُعيد البناء إن وجد `exc_text` مضبوطاً. فنبنيه نحن هنا —
        والفلاتر تعمل قبل التنسيق — ثم نُخفيه، فيستعمل المُنسِّق نسختنا.

        ويُخفى الموجود مسبقاً أيضاً: مع عدّة مُعالِجات يبني أوّلُها `exc_text`
        فيرثه الثاني. والإخفاء مُتماثل — النصّ المُخفى لا يُطابق الأنماط ثانيةً.
        """
        exc_info = getattr(record, "exc_info", None)

        if exc_info and not getattr(record, "exc_text", None):
            record.exc_text = self._format_exception(exc_info)

        if getattr(record, "exc_text", None):
            record.exc_text = self._mask_pii(record.exc_text)

        # `stack_info=True` نصٌّ جاهز يُلحقه المُنسِّق كما هو.
        if getattr(record, "stack_info", None):
            record.stack_info = self._mask_pii(record.stack_info)

    @staticmethod
    def _format_exception(exc_info):
        """نصّ التتبّع — أو `None` إن تعذّر.

        فشلُ الإخفاء يجب ألّا يُسقط السجلّ: سطرٌ مفقود أهون من عمليةٍ تنهار،
        وترك `exc_text` فارغاً يجعل المُنسِّق يبنيه بنفسه — بلا إخفاء، لكن
        بلا انهيار. والحالة الوحيدة المعروفة `exc_info=(None, None, None)`
        حين يُطلب `exc_info=True` خارج `except`.
        """
        try:
            return "".join(traceback.format_exception(*exc_info)).rstrip("\n")
        except (TypeError, ValueError, AttributeError):
            return None

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
