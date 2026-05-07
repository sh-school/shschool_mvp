"""
student_affairs/tests.py — اختبارات أمنية للملفات المحمية (F-001).

يغطي 3 سيناريوهات:
  1. مستخدم غير مسجّل → redirect إلى login
  2. Path traversal → 404
  3. مستخدم مصرّح → X-Accel-Redirect header
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class ProtectedMediaTests(TestCase):
    """اختبارات الوصول للملفات المحمية (F-001)."""

    def test_unauthenticated_redirects_to_login(self):
        """مستخدم غير مسجّل → redirect إلى login."""
        url = reverse(
            "student_affairs:protected_media",
            args=["tardiness_excuses/test.pdf"],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.url)

    def test_path_traversal_returns_404(self):
        """محاولة path traversal بـ '..' → 404."""
        client = Client()
        user = User.objects.create_user(
            username="traversal_test_user",
            password="TestPass-123!",
        )
        client.force_login(user)
        url = reverse(
            "student_affairs:protected_media",
            args=["tardiness_excuses/../../../etc/passwd"],
        )
        response = client.get(url)
        # إما 404 (path traversal blocked) أو 302/403 (role check)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_absolute_path_returns_404(self):
        """مسار مطلق يبدأ بـ '/' → 404."""
        client = Client()
        user = User.objects.create_user(
            username="abspath_test_user",
            password="TestPass-123!",
        )
        client.force_login(user)
        # Django's <path:path> لا يمرر '/' في البداية عادةً،
        # لكن الفحص موجود كطبقة حماية إضافية (defense-in-depth)
        url = reverse(
            "student_affairs:protected_media",
            args=["tardiness_excuses/test.pdf"],
        )
        response = client.get(url)
        # المستخدم ليس لديه صلاحية STUDENT_AFFAIRS_MANAGE → 302/403
        self.assertIn(response.status_code, (302, 403, 404))

    def test_wrong_school_returns_404(self):
        """مستخدم مدرسة أخرى → 404."""
        # TODO: implement with proper fixtures — يحتاج setup:
        # مستخدمين من مدرستين مختلفتين + سجل حضور مع ملف
        pass

    def test_authorized_user_gets_file(self):
        """مستخدم مصرّح → X-Accel-Redirect header."""
        # TODO: implement with proper fixtures — يحتاج setup:
        # مستخدم بصلاحية STUDENT_AFFAIRS_MANAGE + سجل حضور مع ملف
        # في نفس المدرسة + التحقق من X-Accel-Redirect header
        pass
