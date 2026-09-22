"""
notifications/selectors.py
قراءاتُ صندوق الإشعارات — يُقيَّم الاستعلامُ هنا لا في العرض (حارسُ الطبقات P5).
"""

from django.db.models import Count

from .models import InAppNotification


def inbox_notifications(user, event_filter, unread_only):
    """آخر مئة إشعارٍ للمستخدم، مصفّاةً بالنوع والمقروء — الأحدثُ أوّلاً."""
    qs = InAppNotification.objects.filter(user=user)
    if event_filter:
        qs = qs.filter(event_type=event_filter)
    if unread_only:
        qs = qs.filter(is_read=False)
    return list(qs.order_by("-created_at")[:100])


def inbox_type_counts(user):
    """عددُ إشعارات المستخدم لكلّ نوعٍ — {event_type: count}."""
    return dict(
        InAppNotification.objects.filter(user=user)
        .order_by()
        .values("event_type")
        .annotate(c=Count("id"))
        .values_list("event_type", "c")
    )


def inbox_unread_count(user):
    return InAppNotification.objects.unread_count(user)
