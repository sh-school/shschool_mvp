"""عدٌّ فقط لحجم رسائل المطوّر مقابل سياسة الاحتفاظ 90 يومًا (W-20261001-002).

قراءةٌ محضة: استعلامٌ تجميعيٌّ واحد (`aggregate`) بـCount/Min، لا صفوفَ تُجلب ولا محتوى ولا مرسِلون،
ولا حذفَ ولا تعديل. مؤقّتٌ لقرار المالك على الرقم؛ لا يُجدوَل ولا يُدار.
"""

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Count, Min, Q
from django.utils import timezone

from developer_feedback.models import DeveloperMessage


class Command(BaseCommand):
    help = "يعدّ رسائل المطوّر: الإجمالي والأقدم من 90 يومًا وأقدم تاريخ (قراءةٌ فقط، بلا محتوى)."

    def handle(self, *args: Any, **options: Any) -> None:
        now = timezone.now()
        cutoff = now - timedelta(days=DeveloperMessage.RETENTION_DAYS)
        result = DeveloperMessage.objects.aggregate(
            total=Count("pk"),
            older=Count("pk", filter=Q(created_at__lt=cutoff)),
            oldest=Min("created_at"),
        )
        oldest = result["oldest"]
        oldest_text = timezone.localtime(oldest).strftime("%Y-%m-%d") if oldest else "لا رسائل"
        self.stdout.write(f"وقت القياس: {timezone.localtime(now):%Y-%m-%d %H:%M} (توقيت الدوحة)")
        self.stdout.write(f"الإجمالي: {result['total']}")
        self.stdout.write(f"الأقدم من {DeveloperMessage.RETENTION_DAYS} يومًا: {result['older']}")
        self.stdout.write(f"أقدم تاريخ: {oldest_text}")
