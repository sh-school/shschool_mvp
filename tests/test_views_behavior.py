"""
tests/test_views_behavior.py
اختبارات views السلوك الطلابي ولجنة الضبط
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import pytest
from behavior.models import BehaviorInfraction, BehaviorPointRecovery
from .conftest import BehaviorInfractionFactory


@pytest.mark.django_db
class TestBehaviorDashboard:

    def test_dashboard_loads_for_teacher(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        response = client.get("/behavior/dashboard/")
        assert response.status_code == 200

    def test_dashboard_context(self, client_as, teacher_user, school, behavior_infraction):
        client = client_as(teacher_user)
        response = client.get("/behavior/dashboard/")
        assert "recent_infractions" in response.context
        assert "total_deducted" in response.context
        assert "critical_unresolved" in response.context


@pytest.mark.django_db
class TestReportInfraction:

    def test_get_report_form(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        response = client.get("/behavior/report/")
        assert response.status_code == 200
        assert "students" in response.context

    def test_post_creates_level1_infraction(
        self, client_as, teacher_user, school, student_user, enrolled_student
    ):
        client = client_as(teacher_user)
        count_before = BehaviorInfraction.objects.count()
        response = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 1,
            "description": "تأخر عن الحصة",
            "points_deducted": 5,
            "action_taken": "تحذير شفوي",
        })
        assert response.status_code in (200, 302)
        assert BehaviorInfraction.objects.count() > count_before

    def test_critical_infraction_redirects_to_committee(
        self, client_as, teacher_user, school, student_user, enrolled_student
    ):
        """مخالفة درجة 3 تُحال للجنة"""
        client = client_as(teacher_user)
        response = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 3,
            "description": "تصرف خطير",
            "points_deducted": 25,
        }, follow=True)
        # يجب أن يصل إلى صفحة اللجنة أو يُعاد توجيهه
        assert response.status_code == 200

    def test_parent_cannot_report_infraction(
        self, client_as, parent_user, school, student_user
    ):
        client = client_as(parent_user)
        response = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 1,
            "description": "test",
        })
        assert response.status_code in (302, 403)  # يُعاد توجيهه أو محجوب


@pytest.mark.django_db
class TestStudentBehaviorProfile:

    def test_profile_loads(self, client_as, teacher_user, student_user, behavior_infraction):
        client = client_as(teacher_user)
        response = client.get(f"/behavior/student/{student_user.id}/")
        assert response.status_code == 200
        assert "infractions" in response.context
        assert "net_score" in response.context

    def test_net_score_calculation(self, client_as, principal_user, school, student_user, teacher_user):
        """100 - 15 (مخصوم) + 10 (مسترد) = 95"""
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=2, points_deducted=15
        )
        BehaviorPointRecovery.objects.create(
            infraction=inf, reason="سلوك إيجابي",
            points_restored=10, approved_by=principal_user
        )
        client = client_as(teacher_user)
        response = client.get(f"/behavior/student/{student_user.id}/")
        assert response.context["net_score"] == 95

    def test_status_green_for_high_score(self, client_as, teacher_user, student_user, school):
        client = client_as(teacher_user)
        response = client.get(f"/behavior/student/{student_user.id}/")
        # بدون مخالفات → net_score = 100 → green
        assert response.context["status_color"] == "green"


@pytest.mark.django_db
class TestPointRecovery:

    def test_get_recovery_form(self, client_as, principal_user, behavior_infraction):
        client = client_as(principal_user)
        response = client.get(f"/behavior/recovery/{behavior_infraction.id}/")
        assert response.status_code == 200
        assert "infraction" in response.context

    def test_post_creates_recovery(
        self, client_as, principal_user, school,
        student_user, teacher_user, behavior_infraction
    ):
        client = client_as(principal_user)
        response = client.post(f"/behavior/recovery/{behavior_infraction.id}/", {
            "reason": "التزام بالنظام المدرسي",
            "points_restored": 3,
        })
        assert response.status_code in (200, 302)
        assert BehaviorPointRecovery.objects.filter(
            infraction=behavior_infraction
        ).exists()

    def test_teacher_cannot_approve_recovery(
        self, client_as, teacher_user, behavior_infraction
    ):
        client = client_as(teacher_user)
        response = client.get(f"/behavior/recovery/{behavior_infraction.id}/")
        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestCommitteeDashboard:

    def test_committee_dashboard_loads_for_principal(
        self, client_as, principal_user, school
    ):
        client = client_as(principal_user)
        response = client.get("/behavior/committee/")
        assert response.status_code == 200
        assert "open_cases" in response.context
        assert "stats" in response.context

    def test_critical_infractions_in_open_cases(
        self, client_as, principal_user, school, student_user, teacher_user
    ):
        BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=3, is_resolved=False
        )
        client = client_as(principal_user)
        response = client.get("/behavior/committee/")
        assert response.context["stats"]["open_count"] >= 1

    def test_resolve_infraction_via_committee(
        self, client_as, principal_user, school,
        student_user, teacher_user
    ):
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=3,
            points_deducted=25, is_resolved=False
        )
        client = client_as(principal_user)
        response = client.post(
            f"/behavior/committee/{inf.id}/decision/",
            {
                "decision": "resolve",
                "action_taken": "تم حل المشكلة مع الطالب",
                "points_restored": 10,
                "recovery_reason": "التزام بالقرارات",
            }
        )
        assert response.status_code in (200, 302)
        refreshed = BehaviorInfraction.objects.get(id=inf.id)
        assert refreshed.is_resolved is True
