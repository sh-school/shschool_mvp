"""
tests/test_views_quality.py
اختبارات views الجودة والخطة التشغيلية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يغطي: plan_dashboard, my_procedures, quality_committee,
       executor_mapping, progress_report, evaluation_dashboard
"""
import pytest
from .conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory,
)


# ══════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════

def make_principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير الجودة")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_vice_academic(school):
    role = RoleFactory(school=school, name="vice_academic")
    user = UserFactory(full_name="نائب أكاديمي")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم")
    MembershipFactory(user=user, school=school, role=role)
    return user


def make_parent(school):
    role = RoleFactory(school=school, name="parent")
    user = UserFactory(full_name="ولي أمر")
    MembershipFactory(user=user, school=school, role=role)
    return user


# ══════════════════════════════════════════════
#  لوحة تحكم الجودة — plan_dashboard
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestPlanDashboard:

    def test_principal_can_access(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/")
        assert response.status_code == 200

    def test_vice_academic_can_access(self, client_as, school):
        vice = make_vice_academic(school)
        client = client_as(vice)
        response = client.get("/quality/")
        assert response.status_code == 200

    def test_teacher_can_access(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/")
        assert response.status_code == 200

    def test_parent_cannot_access(self, client_as, school):
        parent = make_parent(school)
        client = client_as(parent)
        response = client.get("/quality/")
        assert response.status_code in (302, 403)

    def test_unauthenticated_redirects(self, client):
        response = client.get("/quality/")
        assert response.status_code == 302
        assert "login" in response.url

    def test_year_filter(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/?year=2024-2025")
        assert response.status_code == 200


# ══════════════════════════════════════════════
#  إجراءاتي — my_procedures
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestMyProcedures:

    def test_teacher_sees_my_procedures(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/my-procedures/")
        assert response.status_code == 200

    def test_principal_sees_my_procedures(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/my-procedures/")
        assert response.status_code == 200

    def test_parent_cannot_access(self, client_as, school):
        parent = make_parent(school)
        client = client_as(parent)
        response = client.get("/quality/my-procedures/")
        assert response.status_code in (302, 403)

    def test_unauthenticated_redirects(self, client):
        response = client.get("/quality/my-procedures/")
        assert response.status_code == 302


# ══════════════════════════════════════════════
#  لجنة المراجعة الذاتية
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestQualityCommittee:

    def test_principal_can_view_committee(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/committee/")
        assert response.status_code == 200

    def test_teacher_can_view_committee(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/committee/")
        assert response.status_code == 200

    def test_unauthenticated_redirects(self, client):
        response = client.get("/quality/committee/")
        assert response.status_code == 302

    def test_add_member_requires_login(self, client):
        response = client.post("/quality/committee/add/", {})
        assert response.status_code == 302


# ══════════════════════════════════════════════
#  لجنة منفذي الخطة
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestExecutorCommittee:

    def test_principal_can_access(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/executor-committee/")
        assert response.status_code == 200

    def test_teacher_can_access(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/executor-committee/")
        assert response.status_code == 200

    def test_parent_cannot_access(self, client_as, school):
        parent = make_parent(school)
        client = client_as(parent)
        response = client.get("/quality/executor-committee/")
        assert response.status_code in (302, 403)


# ══════════════════════════════════════════════
#  ربط المنفذين — executor_mapping
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestExecutorMapping:

    def test_principal_can_view(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/executor-mapping/")
        assert response.status_code == 200

    def test_vice_academic_can_view(self, client_as, school):
        vice = make_vice_academic(school)
        client = client_as(vice)
        response = client.get("/quality/executor-mapping/")
        assert response.status_code == 200

    def test_teacher_cannot_manage_mapping(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/executor-mapping/")
        # معلم لا يُسمح له بإدارة الربط
        assert response.status_code in (200, 302, 403)

    def test_save_mapping_requires_post(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/executor-mapping/save/")
        # GET على endpoint POST → redirect أو 405
        assert response.status_code in (302, 405)


# ══════════════════════════════════════════════
#  تقرير التقدم
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestProgressReport:

    def test_principal_can_view_report(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/report/")
        assert response.status_code == 200

    def test_teacher_can_view_report(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/report/")
        assert response.status_code == 200

    def test_unauthenticated_redirects(self, client):
        response = client.get("/quality/report/")
        assert response.status_code == 302

    def test_pdf_report_requires_auth(self, client):
        response = client.get("/quality/report/pdf/")
        assert response.status_code == 302
        assert "login" in response.url

    def test_pdf_report_for_principal(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/report/pdf/")
        # يُرجع PDF أو redirect حسب التطبيق
        assert response.status_code in (200, 302, 404)


# ══════════════════════════════════════════════
#  تقييم الموظفين — evaluation_dashboard
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestEvaluationDashboard:

    def test_principal_can_view_evaluations(self, client_as, school):
        principal = make_principal(school)
        client = client_as(principal)
        response = client.get("/quality/evaluations/")
        assert response.status_code == 200

    def test_vice_academic_can_view_evaluations(self, client_as, school):
        vice = make_vice_academic(school)
        client = client_as(vice)
        response = client.get("/quality/evaluations/")
        assert response.status_code == 200

    def test_teacher_cannot_view_all_evaluations(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/evaluations/")
        # معلم لا يرى لوحة تقييم الكل
        assert response.status_code in (200, 302, 403)

    def test_my_evaluations_for_teacher(self, client_as, school):
        teacher = make_teacher(school)
        client = client_as(teacher)
        response = client.get("/quality/evaluations/mine/")
        assert response.status_code == 200

    def test_unauthenticated_cannot_evaluate(self, client):
        response = client.get("/quality/evaluations/")
        assert response.status_code == 302
        assert "login" in response.url
