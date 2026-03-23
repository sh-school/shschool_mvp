"""
notifications/management/commands/send_notifications.py

python manage.py send_notifications --type absence
python manage.py send_notifications --type fail --year 2025-2026
python manage.py send_notifications --type all
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import School
from notifications.services import NotificationService


class Command(BaseCommand):
    help = "إرسال الإشعارات التلقائية (غياب / رسوب)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type", default="all", choices=["absence", "fail", "all"], help="نوع الإشعار"
        )
        parser.add_argument("--year", default=settings.CURRENT_ACADEMIC_YEAR)
        parser.add_argument("--school", default=None, help="كود المدرسة (اتركه فارغاً للكل)")

    def handle(self, *args, **options):
        notif_type = options["type"]
        year = options["year"]
        school_code = options["school"]

        schools = School.objects.filter(is_active=True)
        if school_code:
            schools = schools.filter(code=school_code)

        for school in schools:
            self.stdout.write(f"\n{'='*50}")
            self.stdout.write(f"المدرسة: {school.name}")

            if notif_type in ("absence", "all"):
                sent, failed = NotificationService.send_pending_absence_alerts(school)
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ تنبيهات الغياب: {sent} أُرسل")
                    + (self.style.WARNING(f"  ✗ {failed} فشل") if failed else "")
                )

            if notif_type in ("fail", "all"):
                sent, failed = NotificationService.send_fail_alerts_for_year(school, year)
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ تنبيهات الرسوب: {sent} أُرسل")
                    + (self.style.WARNING(f"  ✗ {failed} فشل") if failed else "")
                )

        self.stdout.write(self.style.SUCCESS("\nاكتمل إرسال الإشعارات ✓"))
