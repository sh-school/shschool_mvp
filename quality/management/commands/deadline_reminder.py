from django.core.management.base import BaseCommand

from core.models import School
from notifications.hub import NotificationHub
from quality.models import OperationalProcedure


class Command(BaseCommand):
    help = "Send deadline reminder notifications for procedures due within 3 days"

    def handle(self, *args, **options):
        schools = School.objects.all()
        total_sent = 0
        for school in schools:
            procedures = (
                OperationalProcedure.objects.filter(school=school)
                .due_soon(days=3)
                .select_related("executor_user")
            )

            for proc in procedures:
                if proc.executor_user:
                    NotificationHub.dispatch(
                        event_type="plan_deadline",
                        school=school,
                        recipients=[proc.executor_user],
                        title=f"تنبيه: الإجراء {proc.number} يقترب موعده",
                        body=f"الموعد النهائي: {proc.deadline}",
                    )
                    total_sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {total_sent} deadline reminders"))
