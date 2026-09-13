"""
tests/test_channels.py
اختبارات WebSocket consumers (Django Channels)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر:
  - NotificationConsumer: رفض غير المصادق، unread_count عند الاتصال، ping/pong
  - NotificationConsumer: notification.new + emergency.broadcast
"""

import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from notifications.consumers import NotificationConsumer
from notifications.models import InAppNotification

from .conftest import (
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    UserFactory,
)

# ──────────────────────────────────────────────
#  إعداد: InMemoryChannelLayer (لا Redis)
# ──────────────────────────────────────────────

TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}


@pytest.fixture(autouse=True)
def _channel_layer_settings(settings):
    """تطبيق InMemoryChannelLayer على كل اختبارات الملف."""
    settings.CHANNEL_LAYERS = TEST_CHANNEL_LAYERS


# ──────────────────────────────────────────────
#  helpers
# ──────────────────────────────────────────────


async def make_communicator(consumer_class, path, user=None, url_route_kwargs=None):
    """يُنشئ WebsocketCommunicator مع scope محاكي — متوافق مع channels 4.x."""
    app = consumer_class.as_asgi()
    communicator = WebsocketCommunicator(app, path)
    # نضيف البيانات مباشرة على scope بعد الإنشاء (API الجديد)
    communicator.scope["user"] = user
    communicator.scope["url_route"] = {"kwargs": url_route_kwargs or {}}
    return communicator


@database_sync_to_async
def _create_user_with_school():
    school = SchoolFactory()
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم اختباري")
    MembershipFactory(user=user, school=school, role=role)
    return user, school


@database_sync_to_async
def _create_user_for_school(school, role_name="teacher"):
    role = RoleFactory(school=school, name=role_name)
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=role)
    return user


@database_sync_to_async
def _create_unread_notification(user, school, count=2):
    for i in range(count):
        InAppNotification.objects.create(
            user=user,
            school=school,
            title=f"إشعار {i}",
            body="نص",
            event_type="general",
            priority="medium",
        )


# ══════════════════════════════════════════════════════════
#  1. NotificationConsumer
# ══════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestNotificationConsumer:
    async def test_unauthenticated_rejected(self):
        """اتصال بدون مستخدم يجب أن يُرفض."""

        class AnonymousUser:
            is_authenticated = False
            pk = None

        communicator = await make_communicator(
            NotificationConsumer,
            "/ws/notifications/",
            user=AnonymousUser(),
        )
        connected, code = await communicator.connect()
        assert not connected

    async def test_authenticated_connected(self):
        """مستخدم مصادق عليه يجب أن يتصل بنجاح."""
        user, school = await _create_user_with_school()
        communicator = await make_communicator(
            NotificationConsumer,
            "/ws/notifications/",
            user=user,
        )
        connected, _ = await communicator.connect()
        assert connected
        # يستقبل عدد الإشعارات غير المقروءة فور الاتصال
        response = await communicator.receive_json_from()
        assert response["type"] == "unread_count"
        assert response["count"] == 0
        await communicator.disconnect()

    async def test_unread_count_on_connect(self):
        """يُرسل العدد الصحيح عند الاتصال إذا كان هناك إشعارات."""
        user, school = await _create_user_with_school()
        await _create_unread_notification(user, school, count=3)

        communicator = await make_communicator(
            NotificationConsumer,
            "/ws/notifications/",
            user=user,
        )
        connected, _ = await communicator.connect()
        assert connected

        response = await communicator.receive_json_from()
        assert response["type"] == "unread_count"
        assert response["count"] == 3
        await communicator.disconnect()

    async def test_ping_pong(self):
        """إرسال ping يجب أن يُعيد pong."""
        user, school = await _create_user_with_school()
        communicator = await make_communicator(
            NotificationConsumer,
            "/ws/notifications/",
            user=user,
        )
        await communicator.connect()
        await communicator.receive_json_from()  # unread_count

        await communicator.send_json_to({"action": "ping"})
        response = await communicator.receive_json_from()
        assert response["type"] == "pong"
        await communicator.disconnect()

    async def test_notification_new_event(self):
        """notification.new يُرسل الإشعار للمتصفح."""
        user, school = await _create_user_with_school()
        communicator = await make_communicator(
            NotificationConsumer,
            "/ws/notifications/",
            user=user,
        )
        await communicator.connect()
        await communicator.receive_json_from()  # unread_count

        # محاكاة رسالة من channel layer
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        group = f"user_{user.pk}"
        # نحتاج channel_name — نحصل عليه بعد الاتصال
        # نُرسل مباشرة عبر group_send
        await layer.group_send(
            group,
            {
                "type": "notification.new",
                "title": "إشعار اختباري",
                "body": "نص الإشعار",
                "priority": "medium",
                "count": 1,
                "id": str(uuid.uuid4()),
                "url": "/notifications/",
            },
        )
        response = await communicator.receive_json_from(timeout=3)
        assert response["type"] == "new_notification"
        assert response["title"] == "إشعار اختباري"
        assert response["priority"] == "medium"
        await communicator.disconnect()

    async def test_emergency_broadcast_event(self):
        """emergency.broadcast يُرسل رسالة طارئة للمتصفح."""
        user, school = await _create_user_with_school()
        communicator = await make_communicator(
            NotificationConsumer,
            "/ws/notifications/",
            user=user,
        )
        await communicator.connect()
        await communicator.receive_json_from()  # unread_count

        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        await layer.group_send(
            f"user_{user.pk}",
            {
                "type": "emergency.broadcast",
                "message": "تنبيه طارئ: إخلاء المبنى",
            },
        )
        response = await communicator.receive_json_from(timeout=3)
        assert response["type"] == "emergency"
        assert "إخلاء" in response["message"]
        await communicator.disconnect()
