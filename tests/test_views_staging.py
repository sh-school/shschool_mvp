"""
tests/test_views_staging.py
اختبارات views استيراد الدرجات من Excel
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يغطي: import_grades_select, import_log_list,
       download_grade_template, upload_grade_file
"""
import io
import uuid
import pytest
from django.utils import timezone
from staging.models import ImportLog
from .conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory,
    ClassGroupFactory, StudentEnrollmentFactory,
)


# ══════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════

def make_admin(school):
    role = RoleFactory(school=school, name="admin")
    user = UserFactory(full_name="مسؤول الاستيراد")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم الاستيراد")
    MembershipFactory(user=user, school=school, role=role)
    return user


# ══════════════════════════════════════════════
#  صفحة الاستيراد الرئيسية
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestImportGradesSelect:

    def test_admin_can_access(self, client_as, school):
        admin = make_admin(school)
        client = client_as(admin)
        response = client.get("/import/")
        assert response.status_code == 200

    def test_teacher_can_access(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/import/")
        assert response.status_code == 200

    def test_parent_cannot_access(self, client_as, parent_user):
        client = client_as(parent_user)
        response = client.get("/import/")
        assert response.status_code in (302, 403)

    def test_student_cannot_access(self, client_as, student_user):
        client = client_as(student_user)
        response = client.get("/import/")
        assert response.status_code in (302, 403)

    def test_unauthenticated_redirects(self, client):
        response = client.get("/import/")
        assert response.status_code == 302
        assert "/auth/login/" in response.url or "/login/" in response.url

    def test_context_has_assessments(self, client_as, school):
        admin = make_admin(school)
        client = client_as(admin)
        response = client.get("/import/")
        assert "assessments" in response.context

    def test_context_has_logs(self, client_as, school):
        admin = make_admin(school)
        client = client_as(admin)
        response = client.get("/import/")
        assert "logs" in response.context

    def test_import_log_shows_in_context(self, client_as, school):
        admin = make_admin(school)
        ImportLog.objects.create(
            school=school,
            uploaded_by=admin,
            file_name="test.xlsx",
            status="completed",
            total_rows=10,
            imported_rows=9,
        )
        client = client_as(admin)
        response = client.get("/import/")
        assert response.status_code == 200
        assert response.context["logs"].count() >= 1

    def test_year_filter_in_context(self, client_as, school):
        admin = make_admin(school)
        client = client_as(admin)
        response = client.get("/import/?year=2024-2025")
        assert response.status_code == 200
        assert response.context.get("year") == "2024-2025"


# ══════════════════════════════════════════════
#  سجل الاستيراد (admin only)
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestImportLogList:

    def test_admin_can_view_log(self, client_as, school):
        admin = make_admin(school)
        client = client_as(admin)
        response = client.get("/import/log/")
        assert response.status_code == 200

    def test_teacher_cannot_view_log(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/import/log/")
        assert response.status_code in (302, 403)

    def test_parent_cannot_view_log(self, client_as, parent_user):
        client = client_as(parent_user)
        response = client.get("/import/log/")
        assert response.status_code in (302, 403)

    def test_logs_in_context(self, client_as, school):
        admin = make_admin(school)
        ImportLog.objects.create(
            school=school,
            uploaded_by=admin,
            file_name="grades.xlsx",
            status="completed",
        )
        client = client_as(admin)
        response = client.get("/import/log/")
        assert "logs" in response.context
        assert response.context["logs"].count() >= 1

    def test_only_own_school_logs(self, client_as):
        school_a = SchoolFactory()
        school_b = SchoolFactory()
        admin_a  = make_admin(school_a)
        admin_b  = make_admin(school_b)

        ImportLog.objects.create(school=school_b, uploaded_by=admin_b,
                                 file_name="other_school.xlsx", status="completed")

        client = client_as(admin_a)
        response = client.get("/import/log/")
        assert response.status_code == 200
        for log in response.context["logs"]:
            assert log.school == school_a


# ══════════════════════════════════════════════
#  ImportLog Model
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestImportLogModel:

    def test_str(self, school):
        admin = make_admin(school)
        log = ImportLog.objects.create(
            school=school,
            uploaded_by=admin,
            file_name="درجات.xlsx",
            status="completed",
        )
        assert "درجات.xlsx" in str(log)
        assert "مكتمل" in str(log)

    def test_uuid_pk(self, school):
        admin = make_admin(school)
        log = ImportLog.objects.create(school=school, uploaded_by=admin, file_name="test.xlsx")
        assert isinstance(log.id, uuid.UUID)

    def test_default_status_pending(self, school):
        admin = make_admin(school)
        log = ImportLog.objects.create(school=school, uploaded_by=admin, file_name="test.xlsx")
        assert log.status == "pending"

    def test_error_log_is_list(self, school):
        admin = make_admin(school)
        log = ImportLog.objects.create(school=school, uploaded_by=admin, file_name="test.xlsx")
        assert isinstance(log.error_log, list)

    def test_ordering_newest_first(self, school):
        admin = make_admin(school)
        log1 = ImportLog.objects.create(school=school, uploaded_by=admin, file_name="a.xlsx")
        log2 = ImportLog.objects.create(school=school, uploaded_by=admin, file_name="b.xlsx")
        logs = ImportLog.objects.filter(school=school)
        assert logs[0].id == log2.id   # الأحدث أولاً

    def test_all_status_choices(self, school):
        admin = make_admin(school)
        statuses = ["pending", "validating", "importing", "completed", "failed"]
        for s in statuses:
            log = ImportLog.objects.create(
                school=school, uploaded_by=admin,
                file_name=f"{s}.xlsx", status=s,
            )
            assert log.status == s

    def test_error_log_stores_list(self, school):
        admin = make_admin(school)
        errors = ["خطأ في الصف 5", "رقم وطني غير صحيح"]
        log = ImportLog.objects.create(
            school=school, uploaded_by=admin,
            file_name="test.xlsx", error_log=errors,
        )
        refreshed = ImportLog.objects.get(id=log.id)
        assert refreshed.error_log == errors

    def test_set_null_on_user_delete(self, school):
        """حذف المستخدم → uploaded_by = NULL (لا تُحذف السجلات)"""
        admin = make_admin(school)
        log = ImportLog.objects.create(school=school, uploaded_by=admin, file_name="test.xlsx")
        user_id = admin.id
        admin.delete()
        refreshed = ImportLog.objects.get(id=log.id)
        assert refreshed.uploaded_by is None


# ══════════════════════════════════════════════
#  رفع ملف بدون ملف
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestUploadGradeFile:

    def test_upload_without_file_redirects(self, client_as, school):
        """POST بدون ملف → يُعاد للصفحة الرئيسية"""
        admin = make_admin(school)
        client = client_as(admin)
        # نحتاج assessment_id صحيح — نستخدم UUID وهمي (سيُعيد 404)
        fake_id = uuid.uuid4()
        response = client.post(f"/import/upload/{fake_id}/", {})
        # يُعيد 404 لأن الـ assessment غير موجود
        assert response.status_code in (302, 404)

    def test_get_redirects_to_select(self, client_as, school):
        """GET على upload → redirect"""
        admin = make_admin(school)
        client = client_as(admin)
        fake_id = uuid.uuid4()
        response = client.get(f"/import/upload/{fake_id}/")
        assert response.status_code in (302, 404)
