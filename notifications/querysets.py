"""
notifications/querysets.py — Custom QuerySets للإشعارات
=========================================================
"""

from __future__ import annotations

from django.db.models import Count, QuerySet
from django.utils import timezone


class InAppNotificationQuerySet(QuerySet):
    """QuerySet لـ InAppNotification."""

    def for_user(self, user) -> InAppNotificationQuerySet:
        return self.filter(user=user)

    def for_school(self, school) -> InAppNotificationQuerySet:
        return self.filter(school=school)

    def unread(self) -> InAppNotificationQuerySet:
        return self.filter(is_read=False)

    def read(self) -> InAppNotificationQuerySet:
        return self.filter(is_read=True)

    def priority(self, level: str) -> InAppNotificationQuerySet:
        """level: low | medium | high | urgent"""
        return self.filter(priority=level)

    def urgent(self) -> InAppNotificationQuerySet:
        return self.filter(priority__in=["high", "urgent"])

    def event_type(self, event: str) -> InAppNotificationQuerySet:
        return self.filter(event_type=event)

    def recent(self, days: int = 7) -> InAppNotificationQuerySet:
        since = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created_at__gte=since)

    def unread_count_for_user(self, user) -> int:
        return self.for_user(user).unread().count()

    def mark_all_read(self, user) -> int:
        """يُعلّم جميع إشعارات المستخدم كمقروءة — يُرجع عدد المُحدَّثة."""
        return self.for_user(user).unread().update(is_read=True, read_at=timezone.now())


class NotificationLogQuerySet(QuerySet):
    """QuerySet لـ NotificationLog."""

    def sent(self) -> NotificationLogQuerySet:
        return self.filter(status="sent")

    def failed(self) -> NotificationLogQuerySet:
        return self.filter(status="failed")

    def pending(self) -> NotificationLogQuerySet:
        return self.filter(status="pending")

    def channel(self, ch: str) -> NotificationLogQuerySet:
        """ch: email | sms | whatsapp | push"""
        return self.filter(channel=ch)

    def for_student(self, student) -> NotificationLogQuerySet:
        return self.filter(student=student)

    def this_month(self) -> NotificationLogQuerySet:
        today = timezone.now().date()
        return self.filter(sent_at__year=today.year, sent_at__month=today.month)

    def failure_summary(self):
        return (
            self.failed()
            .values("channel", "error_message")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
