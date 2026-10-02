"""
management command: backfill_birth_date_encrypted
═════════════════════════════════════════════════
يملأ Profile.birth_date_encrypted من birth_date للصفوف التي سبقت الهجرة
(PDPPL م.16 — ميلادُ القاصر). عبر ORM فيمرّ بحقل التشفير، وآمنٌ للإعادة:
لا يمسّ صفّاً مملوءاً.

الاستخدام:
  python manage.py backfill_birth_date_encrypted
  python manage.py backfill_birth_date_encrypted --dry-run
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "تعبئة Profile.birth_date_encrypted للصفوف القديمة (آمنٌ للإعادة)"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--dry-run", action="store_true", help="عدٌّ بلا كتابة")

    def handle(self, *args, **options):
        from core.models import Profile

        qs = Profile.objects.filter(birth_date__isnull=False, birth_date_encrypted="")
        total = qs.count()
        self.stdout.write(f"صفوفٌ تحتاج تعبئة: {total}")
        if options["dry_run"] or not total:
            return

        done = 0
        # الدفعاتُ بالمفتاح لا بالإزاحة: الصفوفُ المملوءة تخرج من الفلتر أثناء المرور.
        while True:
            batch = list(qs.order_by("pk")[: options["batch_size"]])
            if not batch:
                break
            for profile in batch:
                profile.save(update_fields=["birth_date"])  # save() يملأ المشفَّر
            done += len(batch)
        self.stdout.write(self.style.SUCCESS(f"عُبّئ {done} صفّاً"))
