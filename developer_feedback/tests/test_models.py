"""Unit tests for developer_feedback models."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from developer_feedback.models import (
    AuditAction,
    AuditLog,
    DeveloperMessage,
    MessagePriority,
    MessageStatus,
    MessageType,
)

User = get_user_model()


class DeveloperMessageModelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="testuser_df_1",
            password="test-password-123",
        )

    def test_save_generates_ticket_number(self):
        msg = DeveloperMessage.objects.create(
            user=self.user,
            message_type=MessageType.BUG,
            priority=MessagePriority.NORMAL,
            subject="اختبار",
            body="وصف طويل كفاية لاختبار النموذج.",
        )
        self.assertTrue(msg.ticket_number.startswith("SOS-"))

    def test_save_computes_user_id_hash(self):
        msg = DeveloperMessage.objects.create(
            user=self.user,
            message_type=MessageType.BUG,
            priority=MessagePriority.NORMAL,
            subject="اختبار",
            body="وصف طويل كفاية لاختبار النموذج.",
        )
        self.assertEqual(len(msg.user_id_hash), 64)

    def test_save_sets_deletion_scheduled_at(self):
        msg = DeveloperMessage.objects.create(
            user=self.user,
            message_type=MessageType.FEATURE,
            priority=MessagePriority.LOW,
            subject="طلب ميزة جديدة",
            body="أتمنى إضافة خاصية ....",
        )
        msg.refresh_from_db()
        self.assertIsNotNone(msg.deletion_scheduled_at)
        # تقريباً 90 يوم من created_at
        delta = msg.deletion_scheduled_at - msg.created_at
        self.assertAlmostEqual(delta.days, 90, delta=1)

    def test_default_status_is_new(self):
        msg = DeveloperMessage.objects.create(
            user=self.user,
            message_type=MessageType.BUG,
            priority=MessagePriority.HIGH,
            subject="خطأ عاجل",
            body="الزر لا يعمل على صفحة الرئيسية.",
        )
        self.assertEqual(msg.status, MessageStatus.NEW)


class AuditLogModelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="testuser_df_2",
            password="test-password-123",
        )

    def test_audit_log_creation(self):
        log = AuditLog.objects.create(
            actor=self.user,
            action=AuditAction.VIEW_INBOX,
        )
        self.assertEqual(log.action, AuditAction.VIEW_INBOX)
        self.assertIsNotNone(log.created_at)
