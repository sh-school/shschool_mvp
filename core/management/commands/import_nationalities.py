"""
management command: python manage.py import_nationalities [--file PATH | --stdin]

يستورد قيم الجنسية من ملف سجل القيد الرسمي (سجل_القيد_*.xlsx) أو من CSV
بعمودين: national_id, nationality.

السبب: ملف طلاب الوزارة (new_students_full.csv) لا يحتوي عمود الجنسية،
لكن سجل القيد الصادر من نظام المدرسة يحتوي العمود في الصف الرابع.

للإنتاج (Railway):
    cat data/student_nationalities.csv | railway run python manage.py \\
        import_nationalities --stdin
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models.user import CustomUser

DEFAULT_CSV = "data/student_nationalities.csv"


class Command(BaseCommand):
    help = "استيراد حقل الجنسية من CSV (national_id, nationality) إلى CustomUser"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=DEFAULT_CSV,
            help=f"مسار CSV (افتراضي: {DEFAULT_CSV})",
        )
        parser.add_argument(
            "--stdin",
            action="store_true",
            help="قراءة CSV من stdin بدل ملف على القرص",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="استعراض التغييرات فقط بدون حفظ",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        updated = 0
        skipped_nomatch = 0
        skipped_unchanged = 0

        if options["stdin"]:
            reader = csv.DictReader(sys.stdin)
            rows = list(reader)
        else:
            path = Path(options["file"])
            if not path.exists():
                raise CommandError(f"الملف غير موجود: {path}")
            with path.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        self.stdout.write(f"عدد الصفوف في CSV: {len(rows)}")

        with transaction.atomic():
            for row in rows:
                nid = (row.get("national_id") or "").strip()
                nat = (row.get("nationality") or "").strip()
                if not nid:
                    continue
                user = CustomUser.objects.filter(national_id=nid).only("id", "nationality").first()
                if not user:
                    skipped_nomatch += 1
                    continue
                if user.nationality == nat:
                    skipped_unchanged += 1
                    continue
                if not dry:
                    CustomUser.objects.filter(pk=user.pk).update(nationality=nat)
                updated += 1

            if dry:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(f"✅ تم تحديث: {updated}"))
        self.stdout.write(f"   لم يتغيّر: {skipped_unchanged}")
        self.stdout.write(f"   غير موجود في DB: {skipped_nomatch}")
        if dry:
            self.stdout.write(self.style.WARNING("(dry-run — لم يُحفظ شيء)"))
