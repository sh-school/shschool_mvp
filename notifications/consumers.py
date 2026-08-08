"""
notifications/consumers.py
━━━━━━━━━━━━━━━━━━━━━━━━━
WebSocket consumers لـ SchoolOS v5.1

NotificationConsumer — إشعارات فورية لكل مستخدم
  • group خاص: user_{user_id}
  • group للمدرسة: school_{school_id}  ← للبث الطارئ

الاتصال: /ws/notifications/
يُرسل عند الاتصال: {"type": "unread_count", "count": N}
يُستقبل من hub.py:
  • notification.new  → {"type": "new_notification", ...}
  • emergency.broadcast → {"type": "emergency", "message": "..."}
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import DatabaseError

from core.rls import rls_context

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer للإشعارات الفورية"""

    # ── الاتصال ─────────────────────────────────────────────────
    async def connect(self):
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            logger.warning("WS: رُفض اتصال غير مصادق عليه")
            await self.close()
            return

        self.user = user
        self.user_group = f"user_{user.pk}"

        # group للمدرسة (للبث الطارئ من المدير)
        self.school_id = await self._get_school_id()
        self.school_group = f"school_{self.school_id}" if self.school_id else None

        # انضمام للـ groups
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        if self.school_group:
            await self.channel_layer.group_add(self.school_group, self.channel_name)

        await self.accept()
        logger.debug(f"WS: اتصل {user.pk} → {self.user_group}")

        # إرسال عدد الإشعارات غير المقروءة فور الاتصال
        count = await self._unread_count()
        await self.send(json.dumps({"type": "unread_count", "count": count}))

    # ── قطع الاتصال ─────────────────────────────────────────────
    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, "school_group") and self.school_group:
            await self.channel_layer.group_discard(self.school_group, self.channel_name)
        logger.debug(f"WS: انقطع {getattr(self, 'user_group', '?')} code={close_code}")

    # ── رسائل واردة من المتصفح (اختياري) ───────────────────────
    async def receive(self, text_data=None, bytes_data=None):
        """
        يستقبل رسائل من المتصفح:
          {"action": "mark_read", "id": "uuid"}  ← لاحقاً
          {"action": "ping"}                      ← للتحقق من الاتصال
        """
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return

        action = data.get("action")
        if action == "ping":
            await self.send(json.dumps({"type": "pong"}))
        elif action == "refresh_count":
            count = await self._unread_count()
            await self.send(json.dumps({"type": "unread_count", "count": count}))

    # ── معالجات الـ group messages (من hub.py) ───────────────────

    async def notification_new(self, event):
        """
        يُرسل عند وصول إشعار جديد من NotificationHub
        event = {"type": "notification.new", "title": ..., "body": ...,
                 "priority": ..., "count": N, "id": uuid}
        """
        await self.send(
            json.dumps(
                {
                    "type": "new_notification",
                    "title": event.get("title", ""),
                    "body": event.get("body", ""),
                    "priority": event.get("priority", "medium"),
                    "count": event.get("count", 0),
                    "id": event.get("id", ""),
                    "url": event.get("url", ""),
                }
            )
        )

    async def emergency_broadcast(self, event):
        """
        بث طارئ من المدير لجميع مستخدمي المدرسة
        event = {"type": "emergency.broadcast", "message": "..."}
        """
        await self.send(
            json.dumps(
                {
                    "type": "emergency",
                    "message": event.get("message", ""),
                }
            )
        )

    # ── دوال مساعدة ─────────────────────────────────────────────

    @database_sync_to_async
    def _get_school_id(self):
        try:
            school = self.user.get_school()
            return str(school.pk) if school else None
        except DatabaseError:
            logger.exception(
                "WS notification school lookup failed: user=%s",
                getattr(self.user, "pk", None),
            )
            return None

    @database_sync_to_async
    def _unread_count(self):
        from .models import InAppNotification

        context = "*" if self.user.is_superuser else self.school_id
        if not context:
            return 0

        try:
            with rls_context(context):
                return InAppNotification.objects.filter(
                    user=self.user,
                    is_read=False,
                ).count()
        except DatabaseError:
            logger.exception(
                "WS notification unread-count DB failure: user=%s",
                getattr(self.user, "pk", None),
            )
            return 0
