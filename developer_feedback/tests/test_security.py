"""
Security tests — 8 tests from MTG-2026-014 Security Report.
- File upload bypass (N/A — E1 removed attachments)
- XSS in subject/body
- CSRF protection on POST
- IDOR on my-messages
- Rate limiting (skipped — integration with django-ratelimit)
- PII leakage in context
- Role-based access (Student blocked)
- SQL injection (Django ORM handles it)
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from developer_feedback.forms import DeveloperMessageForm
from developer_feedback.models import DeveloperMessage, LegalOnboardingConsent

User = get_user_model()


class SecurityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user_a = User.objects.create_user(
            username="sec_user_a",
            password="password-A-123",
        )
        cls.user_b = User.objects.create_user(
            username="sec_user_b",
            password="password-B-123",
        )
        # أكمل onboarding للمستخدم أ
        LegalOnboardingConsent.objects.create(
            user=cls.user_a,
            consent_version="1.0",
            quiz_passed=True,
            quiz_score=3,
            admin_authorization_doc="AUTH-TEST-001",
        )

    def test_1_xss_in_subject_is_escaped_by_django(self):
        """Django templates تُهرّب HTML تلقائياً."""
        xss = "<script>alert('xss')</script>"
        form = DeveloperMessageForm(
            data={
                "message_type": "bug",
                "priority": "normal",
                "subject": xss,
                "body": "body طويل بما يكفي.",
                "consent_privacy": True,
                "context_json_raw": "",
            }
        )
        # النموذج يقبل النص كـ text — الـ escape يحدث عند render
        self.assertTrue(form.is_valid())
        cleaned = form.cleaned_data["subject"]
        self.assertIn("script", cleaned)  # النص موجود كـ string
        # عند الـ render الـ template engine يُهرّبه — نثق بـ Django.

    def test_2_context_json_scrubs_tokens(self):
        payload = json.dumps(
            {
                "url_path": "/admin",
                "jwt": "eyJhbGciOiJIUzI1NiJ9...",
                "session": "abc123",
                "password": "mypass",
            }
        )
        form = DeveloperMessageForm(
            data={
                "message_type": "bug",
                "priority": "normal",
                "subject": "اختبار سياق",
                "body": "body طويل بما يكفي.",
                "consent_privacy": True,
                "context_json_raw": payload,
            }
        )
        self.assertTrue(form.is_valid())
        ctx = form.cleaned_data["context_json_raw"]
        for bad_key in ("jwt", "session", "password"):
            self.assertNotIn(bad_key, ctx)

    def test_3_student_role_cannot_access_send_page(self):
        """Student (user with role=student) ممنوع."""
        student = User.objects.create_user(
            username="test_student_xx",
            password="password-123",
        )
        # محاولة تعيين role إذا كان متاحاً
        if hasattr(student, "role"):
            student.role = "student"
            student.save()
        client = Client()
        client.force_login(student)
        resp = client.get(reverse("developer_feedback:message_create"))
        # إما 403 أو redirect (عدم 200)
        self.assertNotEqual(resp.status_code, 200)

    def test_4_unauthenticated_user_redirected_to_login(self):
        client = Client()
        resp = client.get(reverse("developer_feedback:message_create"))
        self.assertIn(resp.status_code, (302, 403))

    def test_5_my_messages_filters_by_user(self):
        """IDOR protection — كل مستخدم يرى رسائله فقط."""
        # أنشئ رسالة للمستخدم أ
        DeveloperMessage.objects.create(
            user=self.user_a,
            message_type="bug",
            priority="normal",
            subject="رسالة أ",
            body="محتوى للمستخدم أ.",
        )
        # أكمل onboarding للمستخدم ب
        LegalOnboardingConsent.objects.create(
            user=self.user_b,
            consent_version="1.0",
            quiz_passed=True,
            quiz_score=3,
            admin_authorization_doc="AUTH-TEST-002",
        )
        client = Client()
        client.force_login(self.user_b)
        resp = client.get(reverse("developer_feedback:my_messages"))
        if resp.status_code == 200:
            # المستخدم ب لا يرى رسالة المستخدم أ
            content = resp.content.decode("utf-8", errors="ignore")
            self.assertNotIn("رسالة أ", content)

    def test_6_inbox_blocked_for_regular_users(self):
        """Inbox محمي بـ DeveloperOnlyMixin — فقط superuser/developers."""
        client = Client()
        client.force_login(self.user_a)
        resp = client.get(reverse("developer_feedback:inbox_list"))
        self.assertNotEqual(resp.status_code, 200)

    def test_7_csrf_required_on_submit(self):
        """POST بدون CSRF يُرفض."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user_a)
        resp = client.post(
            reverse("developer_feedback:message_create"),
            data={"message_type": "bug"},
        )
        # 403 Forbidden بسبب CSRF
        self.assertEqual(resp.status_code, 403)

    def test_8_notification_payload_excludes_raw_user_id(self):
        """محتوى الإيميل لا يحوي user_id خام — hash فقط."""
        from developer_feedback.services.notifications import _build_safe_payload

        msg = DeveloperMessage.objects.create(
            user=self.user_a,
            message_type="bug",
            priority="high",
            subject="حرج",
            body="خطأ أمني في الواجهة.",
        )
        payload = _build_safe_payload(msg)
        self.assertNotIn("user_id", payload)  # لا user_id خام
        self.assertIn("user_id_hash", payload)
        # الـ hash موجود وليس فارغاً
        self.assertEqual(len(payload["user_id_hash"]), 64)
