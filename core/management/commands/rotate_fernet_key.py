"""
rotate_fernet_key — إعادة تشفير البيانات بالمفتاح الجديد

الاستخدام:
  1. أنشئ مفتاح جديد: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. انقل المفتاح القديم من FERNET_KEY إلى FERNET_OLD_KEYS في .env
  3. ضع المفتاح الجديد في FERNET_KEY
  4. شغّل: python manage.py rotate_fernet_key
"""

import logging

from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand

from core.models._crypto import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "إعادة تشفير جميع الحقول المشفّرة بالمفتاح الجديد (FERNET_KEY)"

    def handle(self, *args, **options):
        total = 0
        errors = 0

        # ── 1. national_id_encrypted في CustomUser ──
        from core.models import CustomUser

        users = CustomUser.objects.exclude(national_id_encrypted="").exclude(
            national_id_encrypted__isnull=True
        )
        self.stdout.write(f"  المستخدمون مع national_id مشفّر: {users.count()}")
        for user in users.iterator():
            try:
                plain = decrypt_field(user.national_id_encrypted)
                if plain and plain != user.national_id_encrypted:
                    user.national_id_encrypted = encrypt_field(plain)
                    user.save(update_fields=["national_id_encrypted"])
                    total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ في المستخدم {user.id}: {e}")

        # ── 2. totp_secret في CustomUser ──
        totp_users = CustomUser.objects.exclude(totp_secret="").exclude(totp_secret__isnull=True)
        self.stdout.write(f"  مستخدمون مع TOTP secret: {totp_users.count()}")
        for user in totp_users.iterator():
            try:
                plain = decrypt_field(user.totp_secret)
                if plain and plain != user.totp_secret:
                    user.totp_secret = encrypt_field(plain)
                    user.save(update_fields=["totp_secret"])
                    total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ TOTP في المستخدم {user.id}: {e}")

        # ── 3. Twilio credentials في NotificationSettings ──
        from notifications.models import NotificationSettings

        for ns in NotificationSettings.objects.all():
            try:
                for field in ("_twilio_account_sid", "_twilio_auth_token"):
                    val = getattr(ns, field, "")
                    if val:
                        plain = decrypt_field(val)
                        if plain and plain != val:
                            setattr(ns, field, encrypt_field(plain))
                ns.save()
                total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ في NotificationSettings {ns.id}: {e}")

        # ── 4. Health records (clinic) ──
        from clinic.models import HealthRecord

        for hr in HealthRecord.objects.all():
            changed = False
            try:
                for field in ("_allergies", "_chronic_diseases", "_medications"):
                    val = getattr(hr, field, "")
                    if val:
                        plain = decrypt_field(val)
                        if plain and plain != val:
                            setattr(hr, field, encrypt_field(plain))
                            changed = True
                if changed:
                    hr.save()
                    total += 1
            except (InvalidToken, ValueError, OSError) as e:
                errors += 1
                self.stderr.write(f"  خطأ في HealthRecord {hr.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ تم تدوير المفاتيح: {total} سجل محدّث، {errors} خطأ")
        )
        if errors:
            self.stdout.write(self.style.WARNING("⚠️ راجع الأخطاء أعلاه — قد تحتاج إعادة المحاولة"))
