"""
Management command: cleanup_old_messages
يحذف رسائل DeveloperMessage التي تجاوزت retention period (افتراضياً 90 يوم).

الاستخدام:
    python manage.py cleanup_old_messages              # dry-run (يعرض العدد فقط)
    python manage.py cleanup_old_messages --apply      # حذف فعلي
    python manage.py cleanup_old_messages --days 60    # override المدة

هذا يُشغَّل يدوياً أو عبر cron/scheduled task.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from developer_feedback.models import DeveloperMessage


class Command(BaseCommand):
    help = "يحذف الرسائل القديمة (>= X يوم) وفق retention policy PDPPL"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="تنفيذ الحذف فعلياً (بدونها = dry-run)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="عدد الأيام (default=90)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        apply = options["apply"]

        cutoff = timezone.now() - timedelta(days=days)
        qs = DeveloperMessage.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        self.stdout.write(
            self.style.WARNING(
                f"[cleanup_old_messages] رسائل أقدم من {days} يوم: {count}"
            )
        )

        if count == 0:
            self.stdout.write(self.style.SUCCESS("لا يوجد ما يُحذف."))
            return

        if not apply:
            self.stdout.write(
                self.style.NOTICE(
                    "Dry-run — لم يُحذف شيء. استخدم --apply للحذف الفعلي."
                )
            )
            return

        with transaction.atomic():
            deleted, breakdown = qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"تم حذف {deleted} عنصر (مع cascade). التفاصيل: {breakdown}"
            )
        )
