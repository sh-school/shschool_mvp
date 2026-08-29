"""
student_affairs/tests.py — اختبارات أمنية للملفات المحمية (F-001).

كان هذا الملفّ خارج البوابة مرّتين: `python_files` في `pytest.ini` تجمع ما
كان تحت مجلّد `tests/` فقط، و CI يُشغّل `pytest tests/` — فلم يجمعه أحد قطّ.
ولمّا شُغّل صراحةً سقط اختباران بـ`TypeError`: `create_user` صار يأخذ
`national_id` و`full_name`، والنداءان يمرّران `username` من نموذجٍ سابق.

واثنان آخران كانا `pass` محضاً — يُحسبان اجتيازاً ولا يفحصان شيئاً. وقد
أُنجزا: عزلُ المستأجرين على تقديم الملفّات، ومسارُ التصريح بترويسته.

وأخطر من ذلك أن اختباري اجتياز المسار كانا يمرّان **لسببٍ خاطئ**:
`protected_media` مزيَّنة بـ`@role_required(STUDENT_AFFAIRS_MANAGE)`، فمستخدمٌ
بلا دورٍ يُحجب عند المُزيِّن ولا يبلغ فحص `..` أصلاً. والدعوى كانت فضفاضة —
`in (302, 403, 404)` — فتبتلع الحجبَ المبكّر وتعدّه نجاحاً.

فصارت هنا: دورٌ مصرَّحٌ له، ثم `404` بعينها.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Membership, Role, School

User = get_user_model()


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

    def _attendance_with_excuse(self, school, national_id):
        """سجلُّ حضورٍ يحمل ملفَّ عذر — والسلسلة كاملةً من الصفّ إلى الحصّة."""
        from datetime import date, time

        from django.core.files.uploadedfile import SimpleUploadedFile

        from core.models import ClassGroup
        from operations.models import Session, StudentAttendance, Subject

        role = Role.objects.create(school=school, name="teacher")
        teacher = User.objects.create_user(
            national_id=national_id, full_name="معلّم", password="TestPass-123!"
        )
        Membership.objects.create(user=teacher, school=school, role=role, is_active=True)

        student = User.objects.create_user(
            national_id=str(int(national_id) + 1), full_name="طالب", password="TestPass-123!"
        )
        cg = ClassGroup.objects.create(school=school, grade="G7", section="1")
        subject = Subject.objects.create(school=school, name_ar="العلوم", code=national_id[-4:])
        session = Session.objects.create(
            school=school,
            class_group=cg,
            teacher=teacher,
            subject=subject,
            date=date.today(),
            start_time=time(8, 0),
            end_time=time(8, 45),
        )
        return StudentAttendance.objects.create(
            session=session,
            student=student,
            school=school,
            status="absent",
            excuse_type="medical",
            excuse_file=SimpleUploadedFile("excuse.pdf", b"%PDF-1.4 test", "application/pdf"),
        )

    def test_wrong_school_returns_404(self):
        """مستخدم مدرسة أخرى → 404 — عزلُ المستأجرين على تقديم الملفّات.

        أمان الصفوف يحرس الجداول، ولم يكن يُثبَت قطّ على مسار تقديم الملفّات:
        والملفّ هنا عذرٌ طبيّ. والعزل يقع في `get_object_or_404(school=…)`
        فيُعيد 404 لا 403 — لا يُقرّ بوجود الملفّ لمن لا يملكه.
        """
        other = School.objects.create(name="مدرسة أخرى", code="SAT02")
        attendance = self._attendance_with_excuse(other, "28900000010")

        client = Client()
        client.force_login(self._authorized_user("28900000003"))
        url = reverse("student_affairs:protected_media", args=[attendance.excuse_file.name])

        response = client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_authorized_user_gets_file(self):
        """مستخدم مصرّح من المدرسة نفسها → ترويسة X-Accel-Redirect.

        وهو الوجه الآخر للاختبار أعلاه: لو ردّ 404 للجميع لَمرّ ذاك وهذا
        يفشل — فالاثنان معاً يُثبتان أن العزل يفصل ولا يمنع الكلّ.
        """
        attendance = self._attendance_with_excuse(self.school, "28900000020")

        client = Client()
        client.force_login(self._authorized_user("28900000004"))
        url = reverse("student_affairs:protected_media", args=[attendance.excuse_file.name])

        response = client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], f"/media/{attendance.excuse_file.name}")
        self.assertIn("attachment", response["Content-Disposition"])
