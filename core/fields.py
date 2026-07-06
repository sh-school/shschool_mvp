"""
core/fields.py — حقول نماذج مخصّصة.

EncryptedTextField: يشفّر النصّ at-rest بـ Fernet بشكل شفّاف — القراءة تفكّ التشفير
والكتابة تشفّر، فلا يتغيّر كود القراءة/الكتابة (تبقى obj.field نصّاً صريحاً برمجياً).

تحذير: غير صالح للفلترة/البحث على النصّ (التشفير غير حتمي) — استخدمه لحقول لا
تُستعلَم بمحتواها (مثل بيانات العيادة الحسّاسة م.8 PDPPL).
"""

from django.db import models


class EncryptedTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        from core.models import decrypt_field

        # fail-open: قيمة غير مشفّرة (بيانات قديمة) تُعاد كما هي حتى تُشفَّر بالهجرة
        return decrypt_field(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        from core.models import encrypt_field

        enc = encrypt_field(str(value))
        # [PII-10] fail-closed: إن أُعيدت القيمة كما هي رغم وجود مفتاح فالتشفير فشل.
        # (في التطوير بلا FERNET_KEY يبقى السلوك fail-open كما كان.)
        if enc == str(value):
            from django.conf import settings

            if getattr(settings, "FERNET_KEY", ""):
                from django.core.exceptions import ImproperlyConfigured

                raise ImproperlyConfigured(
                    "فشل تشفير حقل حسّاس رغم وجود FERNET_KEY — رُفض الحفظ (fail-closed)"
                )
        return enc
