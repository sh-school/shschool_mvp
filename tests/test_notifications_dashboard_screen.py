"""[NOTIFICATIONS] لوحةُ الإشعارات — الشاشةُ تُفتح فعلاً لا أن تُستدعى خدمتُها.

كانت `get_dashboard_stats` معرَّفةً داخل `BreachNotificationService` بينما
تُنادى من `NotificationService`، فكانت `/notifications/` تسقط بـ AttributeError
عند كلّ فتح. ولم يكشفها اختبار، لأنّ اختبارات الإشعارات كلَّها تُنادي الخدمة
مباشرةً ولا تفتح الشاشة. فما لا يُفتَح لا يُقاس عطبُه:

    service_test → passes        (والشاشةُ ساقطة)

فالمقياسُ هنا استجابةُ الصفحة نفسِها، ثمّ موضعُ الدالّة في صنفها الصحيح.
"""

import pytest
from django.urls import reverse

from notifications.services import BreachNotificationService, NotificationService


@pytest.mark.django_db
def test_the_notifications_dashboard_renders_for_leadership(client, principal_user):
    """الفتحُ الفعليّ — لا استدعاءُ الخدمة وحدَها."""
    client.force_login(principal_user)

    response = client.get(reverse("notifications_dashboard"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_the_dashboard_stats_live_on_the_service_the_view_calls(school):
    """الموضعُ جزءٌ من العقد: النداءُ من `NotificationService` فليكن فيها."""
    assert hasattr(NotificationService, "get_dashboard_stats")
    assert not hasattr(BreachNotificationService, "get_dashboard_stats")

    stats = NotificationService.get_dashboard_stats(school, year="2026-2027")

    assert stats["total"] == 0
    assert stats["pending_absence"] == 0
    assert stats["failing_students"] == 0
