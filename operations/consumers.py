"""
operations/consumers.py
━━━━━━━━━━━━━━━━━━━━━━━
AttendanceConsumer — بث تحديثات الحضور الفوري

الاتصال: /ws/attendance/<session_id>/
group: attendance_{session_id}

يُستخدم من:
  • واجهة شبكة الحضور (attendance_grid.html)
  • كل مستخدم يشاهد نفس الحصة يرى التحديثات فوراً بدون تحديث الصفحة
"""

import json
import logging
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import DatabaseError

from core.rls import rls_context

logger = logging.getLogger(__name__)


class AttendanceConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer لبث تحديثات الحضور"""

    # ── الاتصال ─────────────────────────────────────────────────
    async def connect(self):
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            await self.close()
            return

        # التحقق من session_id في URL
        session_id = self.scope["url_route"]["kwargs"].get("session_id")
        if not session_id:
            await self.close()
            return

        # التحقق من صحة UUID
        try:
            uuid.UUID(str(session_id))
        except (ValueError, AttributeError):
            await self.close()
            return

        if not await self._can_access_session(user, session_id):
            logger.warning(
                "WS Attendance denied: user=%s session=%s",
                user.pk,
                session_id,
            )
            await self.close()
            return

        self.session_id = str(session_id)
        self.group_name = f"attendance_{self.session_id}"
        self.user = user

        # انضمام لـ group الحصة
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.debug(f"WS Attendance: {user.pk} اتصل بـ {self.group_name}")

    # ── قطع الاتصال ─────────────────────────────────────────────
    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # ── رسائل واردة (للقراءة فقط — العميل لا يُرسل حضور) ───────
    @database_sync_to_async
    def _can_access_session(self, user, session_id):
        """Mirror the HTTP attendance-view authorization policy."""
        from .models import Session

        try:
            school = user.get_school()
            if school is None:
                return False

            context = "*" if user.is_superuser else str(school.pk)

            with rls_context(context):
                teacher_id = (
                    Session.objects.filter(
                        id=session_id,
                        school_id=school.pk,
                    )
                    .values_list("teacher_id", flat=True)
                    .first()
                )

            if teacher_id is None:
                return False

            return teacher_id == user.pk or user.is_admin() or user.is_leadership()
        except DatabaseError:
            logger.exception(
                "WS Attendance authorization DB failure: user=%s session=%s",
                getattr(user, "pk", None),
                session_id,
            )
            return False

    async def receive(self, text_data=None, bytes_data=None):
        pass  # العميل يقرأ فقط — الإرسال عبر HTTP views

    # ── معالج تحديث الحضور (يُستدعى من operations/views.py) ────
    async def attendance_update(self, event):
        """
        يُرسل لكل مستمعي الحصة عند تغيير حضور طالب
        event = {
            "type": "attendance.update",
            "student_id": str(uuid),
            "status": "present" | "absent" | "late" | "excused",
            "present_count": int,
            "total_students": int,
        }
        """
        await self.send(
            json.dumps(
                {
                    "type": "attendance_update",
                    "student_id": event.get("student_id"),
                    "status": event.get("status"),
                    "present_count": event.get("present_count", 0),
                    "total_students": event.get("total_students", 0),
                }
            )
        )
