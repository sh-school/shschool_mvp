"""إنفاذُ سياسة الاحتفاظ بالبيانات يدويّاً — عرضٌ افتراضاً، وكتابةٌ بـ`--apply`.

    python manage.py enforce_retention              # عرضُ ما سيُحذف — لا كتابة
    python manage.py enforce_retention --dry-run    # الشيءُ نفسُه صراحةً
    python manage.py enforce_retention --apply      # الحذفُ فعلاً + سطرٌ في التدقيق

السياسةُ والمدّةُ في `governance/retention.py` و`docs/privacy/data_retention.md`؛
والمهمّةُ المجدولةُ `core.enforce_data_retention` تُجريها أسبوعيّاً. هذا الأمرُ
للتشغيل بين الجدولين أو للتحقّق قبل تغيير المدّة.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from governance.retention import BATCH_SIZE, RULES, enforce_retention


class Command(BaseCommand):
    help = "يُنفِّذ سياسةَ الاحتفاظ بالبيانات (PDPPL م.7 و10) — عرضٌ بلا --apply"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run", action="store_true", help="عرضُ الأعداد بلا حذف (وهو الافتراض)"
        )
        parser.add_argument("--apply", action="store_true", help="الحذفُ فعلاً")
        parser.add_argument(
            "--batch-size",
            type=int,
            default=BATCH_SIZE,
            help=f"كم صفّاً في جملة الحذف الواحدة (الافتراض {BATCH_SIZE})",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["dry_run"] and options["apply"]:
            raise CommandError("حدّد --dry-run أو --apply — لا كليهما.")
        if options["batch_size"] <= 0:
            raise CommandError("--batch-size يجب أن يكون موجباً.")

        apply = bool(options["apply"])
        report = enforce_retention(dry_run=not apply, batch_size=options["batch_size"])

        if not report.enabled:
            self.stdout.write(
                self.style.WARNING("معطَّل: PDPPL_DATA_RETENTION_DAYS=0 — لا يُحذف شيء.")
            )
            return

        mode = "حُذف" if apply else "مرشَّحٌ للحذف"
        self.stdout.write(
            f"المدّة {report.retention_days} يوماً — الحدّ {report.cutoff:%Y-%m-%d %H:%M} — {mode}:"
        )
        for rule in RULES:
            count = report.counts.get(rule.key, 0)
            self.stdout.write(f"  {count:>7}  {rule.label}  ({rule.table})")
        self.stdout.write(f"  {report.total:>7}  المجموع")

        if apply:
            self.stdout.write(self.style.SUCCESS("كُتب ملخّصُ التنفيذ في سجلّ التدقيق."))
        else:
            self.stdout.write("عرضٌ فقط — أضِف --apply للحذف.")
