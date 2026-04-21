"""
Tests for DeveloperMessageEditView — تعديل رسالة سبق إرسالها.

تغطي:
1. المُرسِل يعدّل رسالته بنجاح — تُحفظ لقطة في MessageEditHistory
2. مستخدم آخر لا يمكنه تعديل رسائل غيره (404)
3. تسجيل EDIT_MESSAGE في AuditLog
4. إشعار SMTP للمطوّر يُرسَل بعد التعديل
5. التعديل يعمل بغضّ النظر عن حالة الرسالة (NEW/IN_PROGRESS/RESOLVED)
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from developer_feedback.models import (
    AuditAction,
    AuditLog,
    DeveloperMessage,
    LegalOnboardingConsent,
    MessageEditHistory,
    MessagePriority,
    MessageStatus,
    MessageType,
)

User = get_user_model()


class MessageEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_a = User.objects.create_superuser(
            national_id="29900000001",
            full_name="المستخدم أ",
            password="password-A-123",
        )
        cls.user_b = User.objects.create_superuser(
            national_id="29900000002",
            full_name="المستخدم ب",
            password="password-B-123",
        )
        for u in (cls.user_a, cls.user_b):
            LegalOnboardingConsent.objects.create(
                user=u,
                consent_version="1.0",
                quiz_passed=True,
                quiz_score=3,
                admin_authorization_doc="AUTH-TEST",
            )

    def _make_message(self, owner):
        return DeveloperMessage.objects.create(
            user=owner,
            user_id_hash="test_hash",
            subject="عنوان أصلي للرسالة",
            body="نص أصلي طويل بما يكفي للتحقق.",
            message_type=MessageType.BUG,
            priority=MessagePriority.NORMAL,
        )

    def test_owner_can_edit_own_message(self):
        msg = self._make_message(self.user_a)
        c = Client()
        c.force_login(self.user_a)

        resp = c.post(
            reverse("developer_feedback:message_edit", kwargs={"pk": msg.pk}),
            data={
                "message_type": MessageType.OTHER,
                "priority": MessagePriority.HIGH,
                "subject": "عنوان مُعدَّل بعد الإرسال",
                "body": "نص مُعدَّل طويل بما يكفي للتحقق.",
            },
        )
        self.assertEqual(resp.status_code, 302)

        msg.refresh_from_db()
        self.assertEqual(msg.subject, "عنوان مُعدَّل بعد الإرسال")
        self.assertEqual(msg.message_type, MessageType.OTHER)
        self.assertEqual(msg.priority, MessagePriority.HIGH)

        # لقطة محفوظة بالقيم القديمة
        self.assertEqual(msg.edit_history.count(), 1)
        snap = msg.edit_history.first()
        self.assertEqual(snap.old_subject, "عنوان أصلي للرسالة")
        self.assertEqual(snap.old_priority, MessagePriority.NORMAL)
        self.assertEqual(snap.edited_by, self.user_a)

    def test_other_user_cannot_edit(self):
        msg = self._make_message(self.user_a)
        c = Client()
        c.force_login(self.user_b)
        resp = c.post(
            reverse("developer_feedback:message_edit", kwargs={"pk": msg.pk}),
            data={
                "message_type": MessageType.BUG,
                "priority": MessagePriority.NORMAL,
                "subject": "محاولة اختراق من مستخدم آخر",
                "body": "نص طويل بما يكفي.",
            },
        )
        # UpdateView + queryset filter → 404 عبر get_object
        self.assertIn(resp.status_code, (404, 403))
        msg.refresh_from_db()
        self.assertEqual(msg.subject, "عنوان أصلي للرسالة")
        self.assertEqual(msg.edit_history.count(), 0)

    def test_edit_logs_audit_action(self):
        msg = self._make_message(self.user_a)
        c = Client()
        c.force_login(self.user_a)
        c.post(
            reverse("developer_feedback:message_edit", kwargs={"pk": msg.pk}),
            data={
                "message_type": MessageType.BUG,
                "priority": MessagePriority.NORMAL,
                "subject": "عنوان بعد التعديل",
                "body": "نص بعد التعديل طويل بما يكفي.",
            },
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.EDIT_MESSAGE,
                target_message=msg,
                actor=self.user_a,
            ).exists()
        )

    def test_edit_sends_smtp_notification(self):
        msg = self._make_message(self.user_a)
        c = Client()
        c.force_login(self.user_a)
        mail.outbox = []
        c.post(
            reverse("developer_feedback:message_edit", kwargs={"pk": msg.pk}),
            data={
                "message_type": MessageType.BUG,
                "priority": MessagePriority.NORMAL,
                "subject": "عنوان بعد التعديل",
                "body": "نص بعد التعديل طويل بما يكفي.",
            },
        )
        # تم إرسال إيميل واحد للمطوّر مع بادئة [تعديل]
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("[تعديل", mail.outbox[0].subject)

    def test_edit_works_regardless_of_status(self):
        """طلب المدير: التعديل مسموح في كل الحالات (NEW/RESOLVED/CLOSED)."""
        for status in (MessageStatus.RESOLVED, MessageStatus.CLOSED):
            msg = self._make_message(self.user_a)
            msg.status = status
            msg.save(update_fields=["status"])
            c = Client()
            c.force_login(self.user_a)
            resp = c.post(
                reverse("developer_feedback:message_edit", kwargs={"pk": msg.pk}),
                data={
                    "message_type": MessageType.BUG,
                    "priority": MessagePriority.NORMAL,
                    "subject": f"عنوان معدَّل رغم حالة {status}",
                    "body": "نص معدَّل طويل بما يكفي.",
                },
            )
            self.assertEqual(resp.status_code, 302, f"status={status} منع التعديل")
            msg.refresh_from_db()
            self.assertEqual(msg.subject, f"عنوان معدَّل رغم حالة {status}")
