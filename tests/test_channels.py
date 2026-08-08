"""
tests/test_channels.py
اختبارات WebSocket consumers (Django Channels)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر:
  - NotificationConsumer: رفض غير المصادق، unread_count عند الاتصال، ping/pong
  - NotificationConsumer: notification.new + emergency.broadcast
  - AttendanceConsumer: اتصال، رفض UUID خاطئ، attendance.update
"""

import uuid
from datetime import date, time

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from notifications.consumers import NotificationConsumer
from notifications.models import InAppNotification
from operations.consumers import AttendanceConsumer

from .conftest import (
    ClassGroupFactory,
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
def _create_attendance_session(school, teacher):
    from operations.models import Session

    class_group = ClassGroupFactory(school=school)
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        date=date.today(),
        start_time=time(8, 0),
        end_time=time(8, 45),
    )


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


# ══════════════════════════════════════════════════════════
#  2. AttendanceConsumer
# ══════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestAttendanceConsumer:
    async def test_unauthenticated_rejected(self):
        """مستخدم غير مصادق لا يتصل."""

        class AnonymousUser:
            is_authenticated = False
            pk = None

        session_id = str(uuid.uuid4())
        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=AnonymousUser(),
            url_route_kwargs={"session_id": session_id},
        )
        connected, _ = await communicator.connect()
        assert not connected

    async def test_teacher_of_session_connected(self):
        """The assigned teacher may subscribe to the attendance session."""
        user, school = await _create_user_with_school()
        session = await _create_attendance_session(school, user)
        session_id = str(session.id)

        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=user,
            url_route_kwargs={"session_id": session_id},
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async def test_nonexistent_session_rejected(self):
        """A valid UUID must still refer to a real accessible session."""
        user, school = await _create_user_with_school()
        session_id = str(uuid.uuid4())

        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=user,
            url_route_kwargs={"session_id": session_id},
        )
        connected, _ = await communicator.connect()
        assert not connected

    async def test_cross_school_session_rejected(self):
        """An authenticated user cannot subscribe to another school's session."""
        user, own_school = await _create_user_with_school()
        teacher, other_school = await _create_user_with_school()
        session = await _create_attendance_session(other_school, teacher)
        session_id = str(session.id)

        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=user,
            url_route_kwargs={"session_id": session_id},
        )
        connected, _ = await communicator.connect()
        assert not connected

    async def test_unrelated_same_school_teacher_rejected(self):
        """A same-school teacher cannot subscribe to another teacher's session."""
        teacher, school = await _create_user_with_school()
        session = await _create_attendance_session(school, teacher)
        viewer = await _create_user_for_school(school, "teacher")
        session_id = str(session.id)

        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=viewer,
            url_route_kwargs={"session_id": session_id},
        )
        connected, _ = await communicator.connect()
        assert not connected

    async def test_same_school_leadership_connected(self):
        """School leadership may observe an attendance session."""
        teacher, school = await _create_user_with_school()
        session = await _create_attendance_session(school, teacher)
        leader = await _create_user_for_school(school, "principal")
        session_id = str(session.id)

        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=leader,
            url_route_kwargs={"session_id": session_id},
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async def test_invalid_uuid_rejected(self):
        """UUID خاطئ → رفض الاتصال."""
        user, school = await _create_user_with_school()
        communicator = await make_communicator(
            AttendanceConsumer,
            "/ws/attendance/NOT_A_UUID/",
            user=user,
            url_route_kwargs={"session_id": "NOT_A_UUID"},
        )
        connected, _ = await communicator.connect()
        assert not connected

    async def test_attendance_update_broadcast(self):
        """attendance.update يُبث لجميع المشتركين في الحصة."""
        user, school = await _create_user_with_school()
        session = await _create_attendance_session(school, user)
        session_id = str(session.id)

        communicator = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=user,
            url_route_kwargs={"session_id": session_id},
        )
        await communicator.connect()

        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        student_id = str(uuid.uuid4())
        await layer.group_send(
            f"attendance_{session_id}",
            {
                "type": "attendance.update",
                "student_id": student_id,
                "status": "present",
                "present_count": 15,
                "total_students": 30,
            },
        )
        response = await communicator.receive_json_from(timeout=3)
        assert response["type"] == "attendance_update"
        assert response["student_id"] == student_id
        assert response["status"] == "present"
        assert response["present_count"] == 15
        await communicator.disconnect()

    async def test_multiple_consumers_same_session(self):
        """متصلان باتصالين مختلفين على نفس الحصة يستقبلان نفس التحديث."""
        user, school = await _create_user_with_school()
        session = await _create_attendance_session(school, user)
        session_id = str(session.id)

        comm1 = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=user,
            url_route_kwargs={"session_id": session_id},
        )
        comm2 = await make_communicator(
            AttendanceConsumer,
            f"/ws/attendance/{session_id}/",
            user=user,
            url_route_kwargs={"session_id": session_id},
        )
        await comm1.connect()
        await comm2.connect()

        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        await layer.group_send(
            f"attendance_{session_id}",
            {
                "type": "attendance.update",
                "student_id": str(uuid.uuid4()),
                "status": "absent",
                "present_count": 10,
                "total_students": 30,
            },
        )
        r1 = await comm1.receive_json_from(timeout=3)
        r2 = await comm2.receive_json_from(timeout=3)
        assert r1["status"] == "absent"
        assert r2["status"] == "absent"
        await comm1.disconnect()
        await comm2.disconnect()
