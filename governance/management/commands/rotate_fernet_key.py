"""
rotate_fernet_key — إعادة تشفير كل الحقول المشفّرة بالمفتاح الجديد (FERNET_KEY).

[PII-01] مُصحَّح: كان الأمر السابق (أ) يقرأ حقول HealthRecord بأسماء خاطئة
(`_allergies`) فلا يعيد تشفير أي سجل صحي، (ب) يُهمل `phone_encrypted`، (ج) يُهمل
`ClinicVisit` كلياً (أخطر بيانات م.16).

[W-20261020-024، W-20261021-003] الشمولُ بالاستقراء: كلُّ نموذجٍ في المشروع فيه `EncryptedTextField` يُدوَّر
(`core.fields.encrypted_field_names` على `apps.get_models()`) لا بقائمةٍ مكتوبة، وحقلا `CustomUser` الإضافيّان
(كهرماء وتاريخ الميلاد) معهما. ويحرس ذلك `tests/test_encrypted_fields_covered_by_rotation.py`: يسقط إن أُضيف
حقلٌ مشفَّر لا يُدوَّر. و`NotificationSettings` (حقولُ Twilio بأسماءٍ خاصّة) يبقى بمساره اليدويّ.

الاستخدام:
  1. أنشئ مفتاحاً جديداً: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. انقل المفتاح القديم من FERNET_KEY إلى FERNET_OLD_KEYS في .env
  3. ضع المفتاح الجديد في FERNET_KEY
  4. شغّل: python manage.py rotate_fernet_key
  5. تحقّق بـ verify_encryption ثم أزل المفتاح القديم من FERNET_OLD_KEYS
"""

import logging
from typing import Any

from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand

from core.fields import encrypted_field_names
from core.models.crypto import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "إعادة تشفير جميع الحقول المشفّرة بالمفتاح الجديد (FERNET_KEY)"

    def _reencrypt_attr(self, obj: Any, attr: str) -> bool:
        """يفكّ حقلاً يخزّن نصاً مشفّراً بالمفتاح القديم ويعيد تشفيره بالحالي."""
        val = getattr(obj, attr, "") or ""
        if not val:
            return False
        plain = decrypt_field(val)
        if plain and plain != val:  # كان مشفّراً بمفتاح قديم
            setattr(obj, attr, encrypt_field(plain))
            return True
        return False

    @staticmethod
    def rotated_models() -> list[Any]:
        """النماذجُ الحقيقيّة (لا الوكيلة) ذاتُ حقلٍ مشفَّر، عدا `CustomUser` فمساره الأوّل أدناه يعيد حسابَ الهاش."""
        from django.apps import apps

        from core.models import CustomUser

        return [
            m
            for m in apps.get_models()
            if not m._meta.proxy and m is not CustomUser and encrypted_field_names(m)
        ]

    def handle(self, *args: Any, **options: Any) -> None:
        total = 0
        errors = 0

        # ── 1. CustomUser: national_id + phone (أعمدة *_encrypted) + totp_secret ──
        # save() يعيد تشفير national_id_encrypted/phone_encrypted من العمودين الخامين
        # بالمفتاح الحالي؛ totp_secret يُعاد تشفيره يدوياً لأنه غير محسوب في save().
        from core.models import CustomUser

        # أعمدةُ `EncryptedTextField` في المستخدم (كهرماء وتاريخ الميلاد) تُستقرأ ولا تُكتب بالاسم.
        user_fields = [
            "national_id_encrypted",
            "national_id_hmac",
            "phone_encrypted",
            "phone_hmac",
            "totp_secret",
            *[n for n in encrypted_field_names(CustomUser) if n != "national_id_encrypted"],
        ]
        users = CustomUser.objects.all()
        self.stdout.write(f"  CustomUser: {users.count()}")
        for user in users.iterator():
            try:
                self._reencrypt_attr(user, "totp_secret")
                user.save(update_fields=list(dict.fromkeys(user_fields)))
                total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ CustomUser {user.id}: {e}")

        # ── 2. Twilio credentials في NotificationSettings ──
        from notifications.models import NotificationSettings

        for ns in NotificationSettings.objects.all():
            try:
                changed = False
                for attr in ("_twilio_account_sid", "_twilio_auth_token"):
                    if self._reencrypt_attr(ns, attr):
                        changed = True
                if changed:
                    ns.save()
                    total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ NotificationSettings {ns.id}: {e}")

        # ── 3. كلُّ نموذجٍ فيه EncryptedTextField — بالاستقراء من سجلّ التطبيقات لا بقائمةٍ مكتوبة ──
        # القراءةُ تفكّ بأيّ مفتاحٍ من المفاتيح، و`update()` يشفّر بالحالي عبر `get_prep_value`؛ فلا يمرّ
        # التدويرُ بـ`save()` ولا إشاراته ولا قيوده (سجلّاتٌ مُحصَّنةٌ كالمخالفات)، ولا يلمس `updated_at`.
        # (W-20261021-003: كان يقتصر على HealthRecord وClinicVisit فتبقى behavior وoperations وغيرُها بالقديم.)
        for model in self.rotated_models():
            names = encrypted_field_names(model)
            for obj in model._base_manager.all().iterator():
                try:
                    values = {n: v for n in names if (v := getattr(obj, n))}
                    if values:
                        model._base_manager.filter(pk=obj.pk).update(**values)
                        total += 1
                except (InvalidToken, ValueError, OSError) as e:
                    errors += 1
                    self.stderr.write(f"  خطأ {model.__name__} {obj.pk}: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ تم تدوير المفاتيح: {total} سجل محدّث، {errors} خطأ")
        )
        if errors:
            self.stdout.write(self.style.WARNING("⚠️ راجع الأخطاء أعلاه — قد تحتاج إعادة المحاولة"))
