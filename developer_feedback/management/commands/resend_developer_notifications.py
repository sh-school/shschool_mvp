"""يعيد إرسال إشعارات المطوّر الفاشلة لغياب المستلِم (W-20261121-005).

- يستهدف فقط الإشعارات `FAILED` التي سُجّلت بمستلِم فارغ (أي فشلت لغياب `DEVELOPER_FEEDBACK_RECIPIENT`).
- idempotent: الرسالة التي لها إشعار `SENT` واحد على الأقل تُتخطّى، فتكرار الأمر لا يرسل مرتين.
- يطبع أرقام التذاكر وأعدادها فقط، بلا محتوى ولا بريد.
- `--dry-run` يعرض ما سيُرسَل دون إرسال.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from developer_feedback.models import (
    DeveloperMessage,
    DeveloperMessageNotification,
    NotificationStatus,
)
from developer_feedback.services.notifications import (
    developer_recipient,
    send_developer_notification,
)


class Command(BaseCommand):
    help = "يعيد إرسال إشعارات المطوّر الفاشلة لغياب المستلِم بعد ضبط DEVELOPER_FEEDBACK_RECIPIENT."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="يعرض التذاكر التي ستُعاد إرسالها دون إرسال.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not developer_recipient():
            raise CommandError("DEVELOPER_FEEDBACK_RECIPIENT غير مضبوط: اضبطه على المنصّة أولاً.")

        failed_ids = (
            DeveloperMessageNotification.objects.filter(
                status=NotificationStatus.FAILED,
                recipient="",
            )
            .values_list("message_id", flat=True)
            .distinct()
        )
        pending = (
            DeveloperMessage.objects.filter(pk__in=failed_ids)
            .exclude(notifications__status=NotificationStatus.SENT)
            .order_by("pk")
            .distinct()
        )

        tickets = [message.ticket_number for message in pending]
        if options["dry_run"]:
            self.stdout.write(f"سيُعاد إرسال {len(tickets)} إشعارًا: {', '.join(tickets)}")
            return

        sent = 0
        for message in pending:
            if send_developer_notification(message).status == NotificationStatus.SENT:
                sent += 1
        self.stdout.write(f"أُعيد إرسال {sent} من {len(tickets)} إشعارًا.")
