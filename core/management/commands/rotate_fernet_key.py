"""
rotate_fernet_key — إعادة تشفير كل الحقول المشفّرة بالمفتاح الجديد (FERNET_KEY).

[PII-01] مُصحَّح: كان الأمر السابق (أ) يقرأ حقول HealthRecord بأسماء خاطئة
(`_allergies`) فلا يعيد تشفير أي سجل صحي، (ب) يُهمل `phone_encrypted`، (ج) يُهمل
`ClinicVisit` كلياً (أخطر بيانات م.16). النسخة الحالية تشمل كل الحقول المشفّرة.

الاستخدام:
  1. أنشئ مفتاحاً جديداً: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. انقل المفتاح القديم من FERNET_KEY إلى FERNET_OLD_KEYS في .env
  3. ضع المفتاح الجديد في FERNET_KEY
  4. شغّل: python manage.py rotate_fernet_key
  5. تحقّق بـ verify_encryption ثم أزل المفتاح القديم من FERNET_OLD_KEYS
"""

import logging

from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand

from core.models._crypto import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "إعادة تشفير جميع الحقول المشفّرة بالمفتاح الجديد (FERNET_KEY)"

    def _reencrypt_attr(self, obj, attr):
        """يفكّ حقلاً يخزّن نصاً مشفّراً بالمفتاح القديم ويعيد تشفيره بالحالي."""
        val = getattr(obj, attr, "") or ""
        if not val:
            return False
        plain = decrypt_field(val)
        if plain and plain != val:  # كان مشفّراً بمفتاح قديم
            setattr(obj, attr, encrypt_field(plain))
            return True
        return False

    def handle(self, *args, **options):
        total = 0
        errors = 0

        # ── 1. CustomUser: national_id + phone (أعمدة *_encrypted) + totp_secret ──
        # save() يعيد تشفير national_id_encrypted/phone_encrypted من العمودين الخامين
        # بالمفتاح الحالي؛ totp_secret يُعاد تشفيره يدوياً لأنه غير محسوب في save().
        from core.models import CustomUser

        users = CustomUser.objects.all()
        self.stdout.write(f"  CustomUser: {users.count()}")
        for user in users.iterator():
            try:
                self._reencrypt_attr(user, "totp_secret")
                user.save(
                    update_fields=[
                        "national_id_encrypted",
                        "national_id_hmac",
                        "phone_encrypted",
                        "phone_hmac",
                        "totp_secret",
                    ]
                )
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

        # ── 3. HealthRecord (clinic) — أسماء الحقول الصحيحة (بلا شرطة سفلية) ──
        from clinic.models import HealthRecord

        for hr in HealthRecord.objects.all():
            try:
                changed = False
                for attr in ("allergies", "chronic_diseases", "medications"):
                    if self._reencrypt_attr(hr, attr):
                        changed = True
                if changed:
                    hr.save()
                    total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ HealthRecord {hr.id}: {e}")

        # ── 4. ClinicVisit — EncryptedTextField: القراءة تفكّ والحفظ يعيد التشفير ──
        from clinic.models import ClinicVisit

        for cv in ClinicVisit.objects.all().iterator():
            try:
                cv.save(update_fields=["reason", "symptoms", "treatment"])
                total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ ClinicVisit {cv.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ تم تدوير المفاتيح: {total} سجل محدّث، {errors} خطأ")
        )
        if errors:
            self.stdout.write(self.style.WARNING("⚠️ راجع الأخطاء أعلاه — قد تحتاج إعادة المحاولة"))
