"""
management command: populate_phone_encryption
═════════════════════════════════════════════
يملأ phone_encrypted و phone_hmac لجميع المستخدمين الذين لديهم phone
ولم تُملأ حقول تشفيرهم بعد (PDPPL Article 8).

الاستخدام:
  python manage.py populate_phone_encryption
  python manage.py populate_phone_encryption --batch-size 200
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "تعبئة phone_encrypted و phone_hmac لجميع المستخدمين الحاليين"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="حجم الدُفعة (افتراضي: 100)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="معاينة بدون حفظ",
        )

    def handle(self, *args, **options):
        from core.models import CustomUser
        from core.models._crypto import encrypt_field, hmac_field

        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        qs = CustomUser.objects.filter(phone__isnull=False).exclude(phone="")
        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("لا يوجد مستخدمون لديهم رقم هاتف."))
            return

        self.stdout.write(f"إجمالي المستخدمين: {total}")
        if dry_run:
            self.stdout.write(self.style.WARNING("وضع المعاينة — لن يُحفظ شيء"))

        updated = 0
        skipped = 0

        for i in range(0, total, batch_size):
            batch = list(qs[i : i + batch_size])
            to_update = []

            for user in batch:
                new_hmac = hmac_field(user.phone)
                new_enc = encrypt_field(user.phone)

                needs_update = (
                    (new_hmac and new_hmac != user.phone_hmac)
                    or (new_enc and new_enc != user.phone_encrypted)
                )

                if needs_update:
                    user.phone_hmac = new_hmac or user.phone_hmac
                    user.phone_encrypted = new_enc or user.phone_encrypted
                    to_update.append(user)
                else:
                    skipped += 1

            if to_update and not dry_run:
                with transaction.atomic():
                    CustomUser.objects.bulk_update(
                        to_update, ["phone_encrypted", "phone_hmac"]
                    )

            updated += len(to_update)
            self.stdout.write(
                f"  دُفعة {i // batch_size + 1}: تحديث {len(to_update)} | تخطي {skipped}"
            )

        style = self.style.SUCCESS if not dry_run else self.style.WARNING
        self.stdout.write(style(
            f"\n✅ اكتمل — محدَّث: {updated} | متخطَّى: {skipped}"
        ))
