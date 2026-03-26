"""
management command: python manage.py seed_violations_2025
يحقن 46 مخالفة رسمية وفق لائحة وزارة التربية القطرية 2025-2026
"""

from django.core.management.base import BaseCommand

from behavior.models import ViolationCategory


class Command(BaseCommand):
    help = "حقن 46 مخالفة رسمية — لائحة السلوك الطلابي قطر 2025-2026"

    def add_arguments(self, parser):
        parser.add_argument(
            "--deactivate-old",
            action="store_true",
            help="تعطيل المخالفات القديمة (ABCD) وتفعيل الجديدة فقط",
        )

    def handle(self, *args, **options):
        created = ViolationCategory.seed_2025()
        total_2025 = ViolationCategory.objects.filter(code__regex=r"^\d+-\d+$").count()

        if options["deactivate_old"]:
            old_count = ViolationCategory.objects.filter(
                code__regex=r"^[A-D]\d+$"
            ).update(is_active=False)
            self.stdout.write(
                self.style.WARNING(f"⚠ تم تعطيل {old_count} مخالفة قديمة (ABCD)")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ تم إضافة {created} مخالفة جديدة | "
                f"الإجمالي 2025: {total_2025} مخالفة"
            )
        )

        # ملخص حسب الدرجات
        for degree in range(1, 5):
            count = ViolationCategory.objects.filter(
                degree=degree, is_active=True
            ).count()
            self.stdout.write(f"   الدرجة {degree}: {count} مخالفة")
