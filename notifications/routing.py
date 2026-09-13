"""
notifications/routing.py
WebSocket URL patterns لـ SchoolOS v5.1
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    # إشعارات فورية لكل مستخدم
    path("ws/notifications/", consumers.NotificationConsumer.as_asgi()),
]
