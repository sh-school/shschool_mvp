"""
student_affairs/tests.py — اختبارات أمنية للملفات المحمية (F-001).

كان هذا الملفّ خارج البوابة مرّتين: `python_files` في `pytest.ini` تجمع ما
كان تحت مجلّد `tests/` فقط، و CI يُشغّل `pytest tests/` — فلم يجمعه أحد قطّ.
ولمّا شُغّل صراحةً سقط اختباران بـ`TypeError`: `create_user` صار يأخذ
`national_id` و`full_name`، والنداءان يمرّران `username` من نموذجٍ سابق.

واثنان آخران كانا `pass` محضاً — يُحسبان اجتيازاً ولا يفحصان شيئاً.

وأخطر من ذلك أن اختباري اجتياز المسار كانا يمرّان **لسببٍ خاطئ**:
`protected_media` مزيَّنة بـ`@role_required(STUDENT_AFFAIRS_MANAGE)`، فمستخدمٌ
بلا دورٍ يُحجب عند المُزيِّن ولا يبلغ فحص `..` أصلاً. والدعوى كانت فضفاضة —
`in (302, 403, 404)` — فتبتلع الحجبَ المبكّر وتعدّه نجاحاً.

فصارت هنا: دورٌ مصرَّحٌ له، ثم `404` بعينها.
"""

import unittest

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Membership, Role, School

User = get_user_model()

#: تجهيزٌ ثقيل: `StudentAttendance` تتطلّب `Session` ومعها `ClassGroup` والمادة والمعلّم.
NEEDS_ATTENDANCE_FIXTURE = "يحتاج سلسلة تجهيزات: Session + ClassGroup + StudentAttendance بملفّ"


class ProtectedMediaTests(TestCase):
    """اختبارات الوصول للملفات المحمية (F-001)."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="مدرسة الاختبار", code="SAT01")
        cls.role = Role.objects.create(school=cls.school, name="principal")

    def _authorized_user(self, national_id):
        """مستخدمٌ يجتاز `@role_required` — وإلّا لم يبلغ الفحص المقصود."""
        user = User.objects.create_user(
            national_id=national_id,
            full_name="مستخدم الاختبار",
            password="TestPass-123!",
        )
        Membership.objects.create(user=user, school=self.school, role=self.role, is_active=True)
        return user

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
        """محاولة path traversal بـ '..' → 404 — والمستخدم مصرَّحٌ له فعلاً."""
        client = Client()
        client.force_login(self._authorized_user("28900000001"))
        url = reverse(
            "student_affairs:protected_media",
            args=["tardiness_excuses/../../../etc/passwd"],
        )

        response = client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_a_plain_path_gets_past_the_role_check(self):
        """المقدّمة نفسها: المستخدم يبلغ جسم الدالّة لا يُحجب عند المُزيِّن.

        فلو حُجب لكان اختبار الاجتياز أعلاه يمرّ بلا أن يمسّ فحص `..`.
        و`404` هنا تأتي من `get_object_or_404` لانعدام الملفّ، لا من الحجب.
        """
        client = Client()
        client.force_login(self._authorized_user("28900000002"))
        url = reverse(
            "student_affairs:protected_media",
            args=["tardiness_excuses/test.pdf"],
        )

        response = client.get(url)

        self.assertEqual(response.status_code, 404)

    @unittest.skip(NEEDS_ATTENDANCE_FIXTURE)
    def test_wrong_school_returns_404(self):
        """مستخدم مدرسة أخرى → 404 — عزلُ المستأجرين على تقديم الملفّات."""

    @unittest.skip(NEEDS_ATTENDANCE_FIXTURE)
    def test_authorized_user_gets_file(self):
        """مستخدم مصرّح → ترويسة X-Accel-Redirect."""
