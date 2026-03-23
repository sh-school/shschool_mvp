"""
notifications/routing.py
WebSocket URL patterns لـ SchoolOS v5.1
"""

from django.urls import path

from operations import consumers as ops_consumers

from . import consumers

websocket_urlpatterns = [
    # إشعارات فورية لكل مستخدم
    path("ws/notifications/", consumers.NotificationConsumer.as_asgi()),
    # بث تحديثات الحضور لحصة بعينها
    path("ws/attendance/<uuid:session_id>/", ops_consumers.AttendanceConsumer.as_asgi()),
]
