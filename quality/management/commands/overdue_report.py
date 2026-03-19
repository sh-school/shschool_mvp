"""
management command: overdue_report
الملف: quality/management/commands/overdue_report.py

الإصلاح #1: يُولّد تقرير بالإجراءات المتأخرة مع تفاصيل كل منفذ.
يُستخدم لحملة تسريع التنفيذ قبل نهاية العام الدراسي.

الاستخدام:
    # عرض كل المتأخرات في الكونسول
    python manage.py overdue_report

    # تصدير إلى CSV
    python manage.py overdue_report --export

    # تصفية بمدرسة محددة
    python manage.py overdue_report --school SHH

    # تصفية بالعام الدراسي
    python manage.py overdue_report --year 2025-2026
"""
import csv
import sys
from datetime import date
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from quality.models import OperationalProcedure, OperationalDomain


class Command(BaseCommand):
    help = "يُولّد تقرير بالإجراءات غير المكتملة مع ترتيب حسب المنفذ والمجال"

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            type=str,
            default=None,
            help="كود المدرسة (اختياري)",
        )
        parser.add_argument(
            "--year",
            type=str,
            default="2025-2026",
            help="السنة الدراسية (افتراضي: 2025-2026)",
        )
        parser.add_argument(
            "--export",
            action="store_true",
            help="تصدير النتائج إلى ملف CSV",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="In Progress",
            help="الحالة المستهدفة (افتراضي: In Progress)",
        )

    def handle(self, *args, **options):
        school_code = options["school"]
        year        = options["year"]
        export      = options["export"]
        status      = options["status"]

        # ── جلب الإجراءات ──
        qs = OperationalProcedure.objects.filter(
            academic_year=year,
            status=status,
        ).select_related(
            "indicator__target__domain",
            "executor_user",
            "school",
        ).order_by("executor_norm", "indicator__target__domain__name", "number")

        if school_code:
            qs = qs.filter(school__code=school_code)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ لا توجد إجراءات متأخرة"))
            return

        # ── تجميع حسب المنفذ ──
        by_executor = defaultdict(list)
        for proc in qs:
            by_executor[proc.executor_norm].append(proc)

        self.stdout.write(
            self.style.WARNING(
                f"\n{'='*60}\n"
                f"تقرير الإجراءات [{status}] — {year}\n"
                f"{'='*60}\n"
                f"الإجمالي: {total} إجراء | عدد المنفذين: {len(by_executor)}\n"
            )
        )

        # ── طباعة كونسول ──
        if not export:
            for executor_norm, procs in sorted(by_executor.items()):
                user = procs[0].executor_user
                user_str = f" ({user.full_name})" if user else " [غير مربوط]"
                self.stdout.write(
                    f"\n  📌 {executor_norm}{user_str} — {len(procs)} إجراء\n"
                )
                # تجميع حسب المجال
                by_domain = defaultdict(list)
                for p in procs:
                    domain_name = p.indicator.target.domain.name if p.indicator.target.domain else "—"
                    by_domain[domain_name].append(p)

                for domain_name, domain_procs in sorted(by_domain.items()):
                    self.stdout.write(f"     [{domain_name}] ({len(domain_procs)} إجراء)")
                    for p in domain_procs[:3]:  # أول 3 فقط
                        self.stdout.write(f"       - [{p.number}] {p.text[:60]}... | {p.date_range}")
                    if len(domain_procs) > 3:
                        self.stdout.write(f"       ... و {len(domain_procs)-3} إجراء إضافي")

        # ── تصدير CSV ──
        if export:
            filename = f"overdue_report_{year.replace('-','_')}_{date.today()}.csv"
            with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "المدرسة", "السنة", "المجال", "الهدف", "رقم الإجراء",
                    "نص الإجراء", "المنفذ (نص)", "المنفذ (اسم)", "الفترة", "الحالة",
                ])
                for proc in qs:
                    domain = proc.indicator.target.domain
                    target = proc.indicator.target
                    user   = proc.executor_user
                    writer.writerow([
                        proc.school.name if proc.school else "",
                        proc.academic_year,
                        domain.name if domain else "",
                        f"[{target.number}] {target.text[:40]}" if target else "",
                        proc.number,
                        proc.text[:100],
                        proc.executor_norm,
                        user.full_name if user else "—",
                        proc.date_range,
                        proc.status,
                    ])

            self.stdout.write(
                self.style.SUCCESS(f"\n✅ تم تصدير {total} إجراء إلى: {filename}")
            )

        # ── ملخص نهائي ──
        self.stdout.write(
            f"\n{'='*60}\n"
            f"الملخص:\n"
        )
        domain_summary = (
            OperationalProcedure.objects.filter(
                academic_year=year, status=status,
                **({'school__code': school_code} if school_code else {}),
            )
            .values("indicator__target__domain__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        for row in domain_summary:
            name  = row["indicator__target__domain__name"] or "—"
            count = row["count"]
            bar   = "█" * min(count // 10, 30)
            self.stdout.write(f"  {name:35} {bar} {count}")
