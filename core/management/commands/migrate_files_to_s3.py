"""core/management/commands/migrate_files_to_s3.py — ترحيلُ الملفّات من StoredFile إلى S3/R2.

البند 11: كان `core.db_storage.DatabaseStorage` (`StoredFile.content`، BinaryField)
هو المخزن الوحيد — قرارٌ صحيحٌ يوم 2026-06-22 (راجع core/db_storage.py) لأنّ
حاوية الويب على Railway بلا قرصٍ دائم. صار S3/R2 إلزامياً الآن، فتحتاج
الملفّاتُ الموجودة فعلاً نقلاً — لا خسارتها بمجرّد تبديل STORAGES["default"].

توسيعٌ ثمّ تقليص (نفس نمط الهجرات في هذا المشروع): هذا الأمر **ينسخ فقط** —
لا يحذف صفوف `StoredFile` القديمة. الحذفُ خطوةٌ لاحقةٌ منفصلةٌ ومقصودة، بعد
أن يستقرّ S3 في الإنتاج أسبوعاً على الأقلّ بلا عطلٍ يستدعي التراجع.

    python manage.py migrate_files_to_s3            # تقريرٌ فقط
    python manage.py migrate_files_to_s3 --apply     # ينسخ فعلياً
"""

from __future__ import annotations

from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management.base import BaseCommand

from core.models import StoredFile


class Command(BaseCommand):
    help = "ينسخ ملفّات StoredFile (DatabaseStorage) إلى S3/R2 — بلا حذف، بلا --apply"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--apply", action="store_true", help="انسخ فعلياً — الافتراضُ تقريرٌ فقط")
        parser.add_argument(
            "--batch-size", type=int, default=50, help="عددُ الصفوف المقروءة من القاعدة دفعةً واحدة"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        apply = options["apply"]
        batch_size = options["batch_size"]
        destination = storages["default"]

        if type(destination).__name__ == "DatabaseStorage":
            self.stderr.write(
                self.style.ERROR(
                    "STORAGES['default'] لا يزال DatabaseStorage — فعِّل USE_S3 أوّلاً "
                    "(أو انتظر دمج البند 11 في الإنتاج)."
                )
            )
            return

        total = StoredFile.objects.count()
        migrated = skipped = failed = 0

        self.stdout.write(f"{total} ملفّاً في StoredFile — الوجهة: {type(destination).__name__}\n")

        for sf in StoredFile.objects.order_by("name").iterator(chunk_size=batch_size):
            try:
                already_there = destination.exists(sf.name)
            except Exception as exc:  # noqa: BLE001 — نتابع الباقي مهما كان سبب الفشل
                failed += 1
                self.stderr.write(f"  فحصٌ فشل: {sf.name} — {exc}")
                continue

            if already_there:
                skipped += 1
                continue

            if not apply:
                migrated += 1
                continue

            try:
                destination.save(sf.name, ContentFile(bytes(sf.content), name=sf.name))
                migrated += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.stderr.write(f"  نسخٌ فشل: {sf.name} — {exc}")

        verb = "نُسخ" if apply else "سيُنسَخ"
        self.stdout.write(
            f"\n{verb} {migrated}، تُجووِز (موجودٌ سلفاً) {skipped}، فشل {failed} — من أصل {total}."
        )
        if not apply:
            self.stdout.write("تقريرٌ فقط — أضِف --apply للنسخ الفعليّ.")
        elif failed:
            self.stderr.write(self.style.WARNING(f"{failed} ملفّاً لم يُنسَخ — راجع الأخطاء أعلاه."))
