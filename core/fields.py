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

        return encrypt_field(str(value))
