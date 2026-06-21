"""
assessments/management/commands/audit_package_weights.py

أمر تدقيق (قراءة فقط) — يكشف أي (SubjectClassSetup × فصل) لا يساوي مجموع
أوزان باقاته 100%. بديل آمن للأمر المحذوف fix_package_weights (الذي كان
يكتب أوزاناً قديمة خاطئة ويُفسد الدرجات).

الاستخدام:
    python manage.py audit_package_weights
    python manage.py audit_package_weights --tolerance 0.5

يُرجِع رمز خروج غير صفري عند وجود انحراف (مناسب لـ CI / pre-deploy gate).
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from assessments.models import AssessmentPackage


class Command(BaseCommand):
    help = "تدقيق مجموع أوزان باقات التقييم لكل (إعداد مادة × فصل) — يجب أن يساوي 100%"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tolerance",
            type=float,
            default=0.01,
            help="هامش السماح حول 100% (افتراضي 0.01)",
        )

    def handle(self, *args, **options):
        tol = Decimal(str(options["tolerance"]))

        rows = (
            AssessmentPackage.objects.values("setup_id", "semester")
            .annotate(total=Sum("weight"))
            .order_by("setup_id", "semester")
        )

        bad = []
        checked = 0
        for r in rows:
            total = r["total"] or Decimal("0")
            if total == 0:
                continue  # لا باقات فعّالة لهذا الفصل في هذا الإعداد
            checked += 1
            if abs(total - Decimal("100")) > tol:
                bad.append((r["setup_id"], r["semester"], total))

        if not bad:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ كل مجاميع الأوزان = 100% ({checked} إعداد×فصل مفحوص، هامش ±{tol})."
                )
            )
            return

        self.stdout.write(self.style.ERROR(f"✗ {len(bad)} (إعداد × فصل) مجموع أوزانها ≠ 100%:"))
        for setup_id, semester, total in bad:
            pkg = (
                AssessmentPackage.objects.filter(setup_id=setup_id, semester=semester)
                .select_related("setup__subject", "setup__class_group")
                .first()
            )
            label = (
                f"{pkg.setup.subject.name_ar} / {pkg.setup.class_group}" if pkg else str(setup_id)
            )
            self.stdout.write(self.style.WARNING(f"   • {label} | {semester} | المجموع = {total}%"))

        raise CommandError(f"{len(bad)} إعداد×فصل بأوزان غير صحيحة — راجع القائمة أعلاه.")
