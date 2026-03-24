"""
tests/test_parents.py
اختبارات بوابة أولياء الأمور

يغطي:
  - لوحة ولي الأمر
  - عرض درجات الطالب
  - عرض حضور الطالب
  - إدارة الروابط (المدير)
  - صفحة الموافقة (PDPPL)
  - التحقق من العزل — ولي الأمر يرى أبناءه فقط
"""

import pytest
from django.utils import timezone

from core.models import ParentStudentLink
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    UserFactory,
)


@pytest.fixture
def parent_with_consent(parent_user):
    """ولي أمر أعطى موافقة — يمكنه الوصول"""
    parent_user.consent_given_at = timezone.now()
    parent_user.save(update_fields=["consent_given_at"])
    return parent_user


class TestParentViews:
    def test_parent_dashboard(self, client_as, parent_with_consent):
        c = client_as(parent_with_consent)
        resp = c.get("/parents/")
        assert resp.status_code == 200

    def test_parent_redirected_to_consent(self, client_as, parent_user):
        """ولي أمر بدون موافقة → يُعاد لصفحة الموافقة"""
        # نزيل الموافقة لاختبار التحويل
        parent_user.consent_given_at = None
        parent_user.save(update_fields=["consent_given_at"])

        c = client_as(parent_user)
        resp = c.get("/parents/", follow=False)
        assert resp.status_code == 302
        assert "/parents/consent/" in resp.url

    def test_consent_page(self, client_as, parent_user):
        c = client_as(parent_user)
        resp = c.get("/parents/consent/")
        assert resp.status_code == 200

    def test_consent_submit(self, client_as, parent_user, school, student_user):
        c = client_as(parent_user)
        resp = c.post("/parents/consent/", {"agree": "1"}, follow=True)
        assert resp.status_code == 200
        parent_user.refresh_from_db()
        assert parent_user.consent_given_at is not None

    def test_student_grades_own_child(self, client_as, parent_with_consent, student_user):
        c = client_as(parent_with_consent)
        resp = c.get(f"/parents/student/{student_user.id}/grades/")
        assert resp.status_code == 200

    def test_student_grades_other_child_forbidden(self, client_as, parent_with_consent, school):
        """ولي الأمر لا يرى درجات طالب ليس ابنه"""
        other_student = UserFactory(full_name="طالب آخر")
        role = RoleFactory(school=school, name="student")
        MembershipFactory(user=other_student, school=school, role=role)

        c = client_as(parent_with_consent)
        resp = c.get(f"/parents/student/{other_student.id}/grades/")
        assert resp.status_code in [403, 404]

    def test_student_attendance(self, client_as, parent_with_consent, student_user):
        c = client_as(parent_with_consent)
        resp = c.get(f"/parents/student/{student_user.id}/attendance/")
        assert resp.status_code == 200

    def test_teacher_cannot_access_parent_portal(self, client_as, teacher_user):
        """المعلم لا يصل لبوابة أولياء الأمور"""
        c = client_as(teacher_user)
        resp = c.get("/parents/")
        assert resp.status_code in [302, 403]


class TestParentLinkAdmin:
    def test_manage_links_as_principal(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/parents/admin/links/")
        assert resp.status_code == 200

    def test_manage_links_forbidden_for_parent(self, client_as, parent_with_consent):
        c = client_as(parent_with_consent)
        resp = c.get("/parents/admin/links/")
        assert resp.status_code == 403

    def test_add_parent_link(self, client_as, principal_user, school):
        new_parent = UserFactory(full_name="ولي أمر جديد")
        new_student = UserFactory(full_name="طالب جديد")
        parent_role = RoleFactory(school=school, name="parent")
        student_role = RoleFactory(school=school, name="student")
        MembershipFactory(user=new_parent, school=school, role=parent_role)
        MembershipFactory(user=new_student, school=school, role=student_role)

        c = client_as(principal_user)
        resp = c.post(
            "/parents/admin/links/add/",
            {
                "parent_id": str(new_parent.id),
                "student_id": str(new_student.id),
                "relationship": "father",
            },
        )
        assert resp.status_code in [200, 302]
        assert ParentStudentLink.objects.filter(parent=new_parent, student=new_student).exists()
