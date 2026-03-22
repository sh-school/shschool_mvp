"""
management command: normalize_executors
الملف: quality/management/commands/normalize_executors.py

يُصحّح الأخطاء الإملائية في executor_norm ويوحّد المسميات الوظيفية
مستنَد من: data/3_Unique_Executors_Inventory.csv
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from quality.models import ExecutorMapping, OperationalProcedure

# ─────────────────────────────────────────────────────────────
# خريطة التطبيع — مُستخرجة مباشرة من ملف Unique_Executors_Inventory.csv
# المفتاح   = القيمة الموجودة في قاعدة البيانات (executor_norm الحالي)
# القيمة    = الاسم الصحيح الموحّد
# ─────────────────────────────────────────────────────────────
NORMALIZATION_MAP = {
    # اختلافات الهاء المربوطة / التاء المربوطة
    "منسق التربيه الاسلاميه": "منسق التربية الإسلامية",
    "منسق التربيه البدنيه": "منسق التربية البدنية",
    "منسق الفنون البصريه": "منسق الفنون البصرية",
    "منسق الدراسات الاجتماعيه": "منسق الدراسات الاجتماعية",
    "منسق اللغه العربيه": "منسق اللغة العربية",
    "منسق اللغه الانجليزيه": "منسق اللغة الإنجليزية",
    "منسق المشاريع الالكترونيه": "منسق المشاريع الإلكترونية",
    "سكرتير المدرسه": "سكرتير المدرسة",
    "مدير المدرسه": "مدير المدرسة",
    "ممرض المدرسه": "ممرض المدرسة",
    "مسؤول الاذاعه": "مسؤول الإذاعة",
    "مسؤول الصيانه": "مسؤول الصيانة",
    "مقرر لجنه الصحه والسلامه": "مقرر لجنة الصحة والسلامة",
    "مقرر لجنه المراجعه الذاتيه": "مقرر لجنة المراجعة الذاتية",
    "أخصائي الأنشطة الدرسية": "أخصائي الأنشطة المدرسية",
    "النائب الاداري": "النائب الإداري",
    # اختلافات في المسمى الكامل
    "نائب المدير للشؤون الاكاديمية": "النائب الأكاديمي",
    "مرشد أكاديمي": "المرشد الأكاديمي",
    "مسؤول مصادر التعلم": "مركز مصادر التعلم",
}


class Command(BaseCommand):
    help = (
        "يُوحّد قيم executor_norm في جداول OperationalProcedure و ExecutorMapping "
        "بتصحيح الأخطاء الإملائية وتوحيد المسميات الوظيفية."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="اعرض التغييرات دون تطبيقها فعلياً",
        )
        parser.add_argument(
            "--school",
            type=str,
            default=None,
            help="كود المدرسة (اختياري — بدونه يُطبَّق على كل المدارس)",
        )
        parser.add_argument(
            "--year",
            type=str,
            default=None,
            help="السنة الدراسية مثل 2025-2026 (اختياري)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        school_code = options["school"]
        year = options["year"]

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  وضع المعاينة (dry-run) — لن يُحفظ أي تغيير\n"))

        total_proc = 0
        total_map = 0

        with transaction.atomic():
            for old_val, new_val in NORMALIZATION_MAP.items():
                # ── تصفية OperationalProcedure ──
                proc_qs = OperationalProcedure.objects.filter(executor_norm=old_val)
                if school_code:
                    proc_qs = proc_qs.filter(school__code=school_code)
                if year:
                    proc_qs = proc_qs.filter(academic_year=year)

                proc_count = proc_qs.count()

                # ── تصفية ExecutorMapping ──
                map_qs = ExecutorMapping.objects.filter(executor_norm=old_val)
                if school_code:
                    map_qs = map_qs.filter(school__code=school_code)
                if year:
                    map_qs = map_qs.filter(academic_year=year)

                map_count = map_qs.count()

                if proc_count == 0 and map_count == 0:
                    continue

                self.stdout.write(
                    f"  {'[DRY]' if dry_run else '✅'} "
                    f'"{old_val}"  →  "{new_val}"'
                    f"  |  إجراءات: {proc_count}  |  ربط: {map_count}"
                )

                if not dry_run:
                    if proc_count:
                        proc_qs.update(executor_norm=new_val)
                    if map_count:
                        map_qs.update(executor_norm=new_val)

                total_proc += proc_count
                total_map += map_count

            if dry_run:
                # أُلغِ العملية حتى لا يُحفظ شيء
                transaction.set_rollback(True)

        # ── ملخص ──
        action = "سيتأثر" if dry_run else "تم تحديث"
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY-RUN] ' if dry_run else ''}الملخص النهائي:\n"
                f"  • {action} {total_proc} إجراء في OperationalProcedure\n"
                f"  • {action} {total_map} سجل في ExecutorMapping"
            )
        )

        if not dry_run and total_proc:
            self.stdout.write(
                self.style.SUCCESS(
                    "\n✅ اكتمل التطبيع. يُنصح بتشغيل apply_all_mappings "
                    "لتحديث executor_user بعد التطبيع."
                )
            )
