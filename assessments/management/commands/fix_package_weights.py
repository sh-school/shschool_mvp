"""
assessments/management/commands/fix_package_weights.py

أمر إدارة لتصحيح أوزان AssessmentPackage وpass_grade في AnnualSubjectResult.

الاستخدام:
    python manage.py fix_package_weights --dry-run   # عرض ما سيتغير بدون تطبيق
    python manage.py fix_package_weights             # تطبيق التغييرات فعلياً
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from assessments.models import AnnualSubjectResult, AssessmentPackage

# الأوزان الصحيحة حسب مواصفات وزارة التعليم القطرية
CORRECT_WEIGHTS = {
    "S1": {
        "P1": Decimal("12.50"),   # أعمال مستمرة ف1 → 2  درجة من 40
        "P2": Decimal("0.00"),    # غير مستخدم في الفصل الأول
        "P3": Decimal("37.50"),   # منتصف الفصل الأول → 6  درجات من 40
        "P4": Decimal("50.00"),   # نهاية الفصل الأول → 8  درجات من 40
    },
    "S2": {
        "P1": Decimal("8.33"),    # أعمال مستمرة ف2 → 3  درجات من 60
        "P2": Decimal("0.00"),    # غير مستخدم
        "P3": Decimal("25.00"),   # منتصف الفصل الثاني → 9  درجات من 60
        "P4": Decimal("66.67"),   # نهاية العام → 24 درجة  من 60
    },
}

CORRECT_SEMESTER_MAX = {
    "S1": Decimal("40"),
    "S2": Decimal("60"),
}

PACKAGE_TYPE_LABELS = {
    "P1": "أعمال مستمرة",
    "P2": "اختبارات قصيرة",
    "P3": "منتصف الفصل",
    "P4": "اختبار نهائي",
}

SEMESTER_LABELS = {
    "S1": "الفصل الأول  (من 40)",
    "S2": "الفصل الثاني (من 60)",
}


class Command(BaseCommand):
    help = "تصحيح أوزان باقات التقييم وdرجة النجاح السنوية حسب مواصفات وزارة التعليم القطرية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض التغييرات المطلوبة دون تطبيقها فعلياً",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("[ DRY RUN ] لن يتم حفظ أي تغييرات."))
        else:
            self.stdout.write(self.style.SUCCESS("[ LIVE ] سيتم حفظ التغييرات في قاعدة البيانات."))

        self.stdout.write("")
        self._fix_package_weights(dry_run)
        self.stdout.write("")
        self._fix_pass_grades(dry_run)
        self.stdout.write("")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "أعد تشغيل الأمر بدون --dry-run لتطبيق التغييرات."
                )
            )

    # ─────────────────────────────────────────────
    # 1. أوزان AssessmentPackage
    # ─────────────────────────────────────────────

    def _fix_package_weights(self, dry_run: bool) -> None:
        self.stdout.write(self.style.HTTP_INFO("─── AssessmentPackage — أوزان الباقات ───"))

        total_wrong = 0
        to_update: list[AssessmentPackage] = []

        for semester, type_weights in CORRECT_WEIGHTS.items():
            sem_label = SEMESTER_LABELS[semester]
            correct_max = CORRECT_SEMESTER_MAX[semester]

            for pkg_type, correct_weight in type_weights.items():
                pkg_label = PACKAGE_TYPE_LABELS[pkg_type]

                wrong_packages = AssessmentPackage.objects.filter(
                    semester=semester,
                    package_type=pkg_type,
                ).exclude(
                    weight=correct_weight,
                    semester_max_grade=correct_max,
                ).select_related("setup__subject", "setup__class_group")

                count = wrong_packages.count()
                if count == 0:
                    self.stdout.write(
                        f"  ✓ {sem_label} / {pkg_type} {pkg_label}: كل الصفوف صحيحة"
                    )
                    continue

                total_wrong += count
                self.stdout.write(
                    self.style.WARNING(
                        f"  ✗ {sem_label} / {pkg_type} {pkg_label}: "
                        f"{count} صف يحتاج تحديث → weight={correct_weight}%, "
                        f"semester_max={correct_max}"
                    )
                )

                # طباعة تفاصيل الصفوف الخاطئة
                for pkg in wrong_packages[:10]:
                    self.stdout.write(
                        f"      id={pkg.pk} | "
                        f"weight={pkg.weight}% → {correct_weight}% | "
                        f"semester_max={pkg.semester_max_grade} → {correct_max} | "
                        f"{pkg.setup.subject.name_ar} / {pkg.setup.class_group}"
                    )
                if count > 10:
                    self.stdout.write(f"      ... و{count - 10} صف آخر")

                if not dry_run:
                    to_update.append((semester, pkg_type, correct_weight, correct_max))

        if dry_run:
            if total_wrong:
                self.stdout.write(
                    self.style.WARNING(f"\n  المجموع: {total_wrong} باقة تحتاج تصحيح.")
                )
            else:
                self.stdout.write(self.style.SUCCESS("\n  كل الأوزان صحيحة بالفعل."))
            return

        # تطبيق التحديثات
        if not to_update:
            self.stdout.write(self.style.SUCCESS("\n  كل الأوزان صحيحة بالفعل — لا شيء للتحديث."))
            return

        updated_total = 0
        with transaction.atomic():
            for semester, pkg_type, correct_weight, correct_max in to_update:
                n = AssessmentPackage.objects.filter(
                    semester=semester,
                    package_type=pkg_type,
                ).exclude(
                    weight=correct_weight,
                    semester_max_grade=correct_max,
                ).update(
                    weight=correct_weight,
                    semester_max_grade=correct_max,
                )
                updated_total += n

        self.stdout.write(
            self.style.SUCCESS(f"\n  تم تحديث {updated_total} باقة بنجاح.")
        )

    # ─────────────────────────────────────────────
    # 2. pass_grade في AnnualSubjectResult
    # ─────────────────────────────────────────────

    def _fix_pass_grades(self, dry_run: bool) -> None:
        self.stdout.write(self.style.HTTP_INFO("─── AnnualSubjectResult — درجة النجاح ───"))

        wrong_qs = AnnualSubjectResult.objects.filter(pass_grade=Decimal("50"))
        count = wrong_qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("  ✓ كل نتائج pass_grade = 60 بالفعل — لا شيء للتحديث."))
            return

        self.stdout.write(
            self.style.WARNING(f"  ✗ {count} نتيجة سنوية تحمل pass_grade=50 → ستُصحَّح إلى 60")
        )

        # عرض عينة
        for r in wrong_qs.select_related("student", "setup__subject")[:10]:
            self.stdout.write(
                f"      id={r.pk} | "
                f"{r.student.full_name if hasattr(r.student, 'full_name') else r.student_id} | "
                f"{r.setup.subject.name_ar} | pass_grade={r.pass_grade} | status={r.status}"
            )
        if count > 10:
            self.stdout.write(f"      ... و{count - 10} نتيجة أخرى")

        if dry_run:
            return

        with transaction.atomic():
            updated = wrong_qs.update(pass_grade=Decimal("60"))

        self.stdout.write(
            self.style.SUCCESS(f"  تم تحديث {updated} نتيجة سنوية: pass_grade 50 → 60.")
        )
