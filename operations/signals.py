"""
operations/signals.py — ما يُحدثه في العمليّات تغيّرٌ يقع خارجها.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from core.models import CalendarEvent


@receiver(post_save, sender="core.CalendarEvent")
def clear_sessions_of_a_break(
    sender: type[CalendarEvent], instance: CalendarEvent, raw: bool = False, **kwargs: object
) -> None:
    """إجازةٌ تُحفظ في التقويم تمحو ما وُلّد لأيّامها ولم يمسّه أحد.

    الإجازةُ الطارئةُ تُعلَن بعد أن وُلّد أسبوعُها، فتبقى حصصُها في كشف الحصص تنتظر
    الرصد. وشرطُ الجمهور لا يُكرَّر هنا: إجازةُ الموظفين وحدَهم أيّامُها أيّامُ دراسة،
    فيمرّ بها الحكمُ بلا أثر. والإجازةُ التي تُحذف أو تُقصَّر تُعيد أيّامَها للتوليد
    من تلقاء نفسه — فلا مستقبِلَ للحذف.
    """
    if raw or instance.event_type != "break":
        return
    from operations.services import ScheduleService

    ScheduleService.clear_holiday_sessions(
        instance.academic_year.school, instance.start_date, instance.end_date
    )
