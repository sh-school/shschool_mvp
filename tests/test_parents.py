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


class TestChildKpis:
    """أرقامُ بطاقة الابن: اللونُ يحمل الحكم، والرقمُ الذي لا يُقاس لا يُعرض."""

    class _Link:
        def __init__(self, grades=True, attendance=True):
            self.can_view_grades = grades
            self.can_view_attendance = attendance

    def _kpis(self, **child):
        from parents.services import _child_kpis

        child.setdefault("link", self._Link())
        return {k["label"]: k for k in _child_kpis(child)}

    def test_behavior_score_is_gone_because_nothing_computes_it(self):
        assert "درجة السلوك" not in self._kpis(attendance_pct=95)

    def test_attendance_thresholds_colour_the_number(self):
        assert self._kpis(attendance_pct=90)["الحضور"]["tone"] == "green"
        assert self._kpis(attendance_pct=75)["الحضور"]["tone"] == "amber"
        assert self._kpis(attendance_pct=74)["الحضور"]["tone"] == "red"
        assert self._kpis(attendance_pct=None)["الحضور"]["value"] == "—"

    def test_five_absences_are_red_and_lateness_rides_along(self):
        absent = self._kpis(absent_30=5, late_30=2)["الغياب"]
        assert absent["tone"] == "red" and absent["sub"] == "و2 تأخّر"

    def test_a_failed_subject_is_red(self):
        subjects = self._kpis(subjects_count=9, failed=2, passed=7)["المواد"]
        assert subjects["tone"] == "red" and subjects["sub"] == "راسب في 2"

    def test_permissions_hide_what_the_parent_may_not_see(self):
        kpis = self._kpis(link=self._Link(grades=False, attendance=True), attendance_pct=90)
        assert set(kpis) == {"الحضور", "الغياب"}


@pytest.mark.django_db
def test_the_dashboard_draws_each_child_with_the_shared_components(
    client_as, parent_with_consent, student_user, school
):
    ParentStudentLink.objects.get_or_create(
        parent=parent_with_consent, student=student_user, school=school
    )
    body = client_as(parent_with_consent).get("/parents/").content.decode()

    assert "ui-section" in body and "ui-kpis" in body
    assert "kpi-mini" not in body and "alert-strip" not in body
    assert 'style="display:none' not in body
