"""
python manage.py seed_violations_2026 [--dry-run] [--academic-year 2026-2027]

يُحقن 41 مخالفةً رسميّةً مع سلالمها الكاملة من conduct_2026.CATALOG.
المصدر الوحيد: conduct_2026.py — لا ملفَّ خارجيَّ، لا hardcode.

الفرق عن seed_violations_2025:
  - يملأ ladder_json و ladder_key (الحقلان الجديدان في migration 0021).
  - يُصحِّح اسم 4-07 (المُدمَج في #658).
  - idempotent: update_or_create بالـcode — آمنٌ للتشغيل أكثرَ من مرّة.
"""

from django.core.management.base import BaseCommand

from behavior.conduct_2026 import CATALOG, LADDERS
from behavior.models import ViolationCategory


class Command(BaseCommand):
    help = "حقن 41 مخالفة 2026 مع سلالمها الكاملة في ViolationCategory"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="عرضٌ بلا كتابة")
        parser.add_argument(
            "--academic-year",
            default="2026-2027",
            help="العام الدراسيّ (للتوثيق في verbose_name فقط — المخالفاتُ لا تُرتبط بعامٍ حالياً)",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        year = options["academic_year"]
        created_n = updated_n = skipped_n = 0

        for infraction in CATALOG:
            ladder = LADDERS[infraction.ladder]
            ladder_data = ladder.to_json()

            defaults = {
                "name_ar": infraction.name,
                "degree": infraction.degree,
                "ladder_key": infraction.ladder,
                "ladder_json": ladder_data,
                "is_active": True,
            }

            if dry:
                existing = ViolationCategory.objects.filter(code=infraction.code).first()
                status = "جديدة" if not existing else "تحديث"
                self.stdout.write(
                    f"[dry] {infraction.code} — {infraction.name[:50]} [{status}] سلّم={infraction.ladder}"
                )
                skipped_n += 1
                continue

            obj, created = ViolationCategory.objects.update_or_create(
                code=infraction.code,
                defaults=defaults,
            )
            if created:
                created_n += 1
            else:
                updated_n += 1

        if dry:
            self.stdout.write(self.style.WARNING(f"\n[dry-run] {skipped_n} مخالفة — لم تُكتب."))
            return

        self.stdout.write(self.style.SUCCESS(f"✅ {year} — {created_n} جديدة · {updated_n} محدَّثة"))

        # ملخَّص حسب الدرجات
        for degree in range(1, 5):
            count = ViolationCategory.objects.filter(
                degree=degree, ladder_json__isnull=False
            ).count()
            self.stdout.write(f"   الدرجة {degree}: {count} مخالفة بسلّم محقون")

        # إحصاء السلالم المشتركة
        shared = {}
        for infraction in CATALOG:
            shared.setdefault(infraction.ladder, []).append(infraction.code)
        multi = {k: v for k, v in shared.items() if len(v) > 1}
        if multi:
            self.stdout.write("\nسلالمٌ مشتركةٌ بين مخالفات:")
            for key, codes in sorted(multi.items()):
                self.stdout.write(f"   {key}: {', '.join(codes)}")
