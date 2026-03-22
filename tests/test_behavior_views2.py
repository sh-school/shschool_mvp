"""
tests/test_behavior_views2.py
Extended behavior views tests — covers behavior/behavior_views.py + behavior/views.py
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from core.models import (
    BehaviorInfraction, BehaviorPointRecovery, ParentStudentLink,
)
from .conftest import (
    BehaviorInfractionFactory, UserFactory, RoleFactory,
    MembershipFactory, StudentEnrollmentFactory, ClassGroupFactory,
)


# ══════════════════════════════════════════════════════════════
#  helpers
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def vice_admin_user(db, school):
    role = RoleFactory(school=school, name="vice_admin")
    user = UserFactory(full_name="نائب الشؤون الإدارية")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def coordinator_user(db, school):
    role = RoleFactory(school=school, name="coordinator")
    user = UserFactory(full_name="المنسق")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def superuser(db, school):
    user = UserFactory(full_name="مسؤول النظام", is_superuser=True)
    role = RoleFactory(school=school, name="admin")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def level3_infraction(db, school, student_user, teacher_user):
    return BehaviorInfractionFactory(
        school=school, student=student_user, reported_by=teacher_user,
        level=3, points_deducted=25, is_resolved=False,
    )


@pytest.fixture
def level4_infraction(db, school, student_user, teacher_user):
    return BehaviorInfractionFactory(
        school=school, student=student_user, reported_by=teacher_user,
        level=4, points_deducted=40, is_resolved=False,
    )


# ══════════════════════════════════════════════════════════════
#  Dashboard
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorDashboardExtended:

    def test_dashboard_forbidden_for_student(self, client_as, student_user):
        client = client_as(student_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.status_code == 403

    def test_dashboard_forbidden_for_parent(self, client_as, parent_user):
        client = client_as(parent_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.status_code == 403

    def test_dashboard_context_keys(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.status_code == 200
        for key in ("stats", "total_deducted", "total_restored",
                     "net_deducted", "recent_infractions", "critical_unresolved",
                     "can_report", "is_committee"):
            assert key in resp.context, f"Missing context key: {key}"

    def test_dashboard_can_report_true_for_teacher(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.context["can_report"] is True

    def test_dashboard_is_committee_true_for_principal(self, client_as, principal_user, school):
        client = client_as(principal_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.context["is_committee"] is True

    def test_dashboard_is_committee_false_for_teacher(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.context["is_committee"] is False

    def test_dashboard_with_infractions(self, client_as, teacher_user, school, behavior_infraction):
        client = client_as(teacher_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.context["total_deducted"] > 0

    def test_dashboard_with_recovery(self, client_as, teacher_user, school,
                                      behavior_infraction, principal_user):
        BehaviorPointRecovery.objects.create(
            infraction=behavior_infraction, reason="سلوك إيجابي",
            points_restored=3, approved_by=principal_user,
        )
        client = client_as(teacher_user)
        resp = client.get("/behavior/dashboard/")
        assert resp.context["total_restored"] == 3

    def test_dashboard_redirect_no_school(self, client, db):
        """User without school membership gets redirected."""
        user = UserFactory(full_name="بلا مدرسة")
        # No membership => get_role() returns something that isn't parent/student
        # but get_school() returns None
        user.is_superuser = True
        user.save()
        client.force_login(user)
        resp = client.get("/behavior/dashboard/")
        # superuser passes role check but has no school => redirect
        assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════
#  Report Infraction
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReportInfractionExtended:

    def test_student_cannot_report(self, client_as, student_user):
        client = client_as(student_user)
        resp = client.get("/behavior/report/")
        assert resp.status_code == 302  # redirect to dashboard

    def test_get_report_form_context(self, client_as, teacher_user, school, enrolled_student):
        client = client_as(teacher_user)
        resp = client.get("/behavior/report/")
        assert resp.status_code == 200
        assert "students" in resp.context
        assert "POINTS_BY_LEVEL" in resp.context
        assert "levels" in resp.context

    def test_post_missing_fields(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": "",
            "level": 1,
            "description": "",
            "points_deducted": 5,
        })
        # Should stay on form (200) with error messages
        assert resp.status_code == 200

    def test_post_missing_description(self, client_as, teacher_user, school, student_user, enrolled_student):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 1,
            "description": "",
            "points_deducted": 5,
        })
        assert resp.status_code == 200
        assert BehaviorInfraction.objects.count() == 0

    def test_post_invalid_level(self, client_as, teacher_user, school, student_user, enrolled_student):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 9,
            "description": "test violation",
            "points_deducted": 5,
        })
        # Invalid level => error, stays on form
        assert resp.status_code == 200

    def test_post_invalid_points(self, client_as, teacher_user, school, student_user, enrolled_student):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 1,
            "description": "test violation",
            "points_deducted": 999,
        })
        assert resp.status_code == 200

    def test_post_level2_redirects_to_student_profile(
        self, client_as, teacher_user, school, student_user, enrolled_student
    ):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 2,
            "description": "سوء سلوك",
            "points_deducted": 15,
            "action_taken": "تحذير",
        })
        assert resp.status_code == 302
        assert f"/behavior/student/{student_user.id}/" in resp.url

    def test_post_level3_redirects_to_committee(
        self, client_as, teacher_user, school, student_user, enrolled_student
    ):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 3,
            "description": "مخالفة جسيمة",
            "points_deducted": 25,
        })
        assert resp.status_code == 302
        assert "/behavior/committee/" in resp.url

    def test_post_level4_redirects_to_committee(
        self, client_as, teacher_user, school, student_user, enrolled_student
    ):
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": 4,
            "description": "مخالفة شديدة الخطورة",
            "points_deducted": 40,
        })
        assert resp.status_code == 302
        assert "/behavior/committee/" in resp.url

    def test_coordinator_can_report(self, client_as, coordinator_user, school):
        client = client_as(coordinator_user)
        resp = client.get("/behavior/report/")
        assert resp.status_code == 200

    def test_vice_admin_can_report(self, client_as, vice_admin_user, school):
        client = client_as(vice_admin_user)
        resp = client.get("/behavior/report/")
        assert resp.status_code == 200

    def test_post_non_numeric_level(self, client_as, teacher_user, school, student_user, enrolled_student):
        """Non-numeric level/points should be handled gracefully."""
        client = client_as(teacher_user)
        resp = client.post("/behavior/report/", {
            "student_id": str(student_user.id),
            "level": "abc",
            "description": "test",
            "points_deducted": "xyz",
        })
        # Should handle ValueError gracefully
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
#  Student Behavior Profile
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStudentBehaviorProfileExtended:

    def test_profile_nonexistent_student(self, client_as, teacher_user):
        import uuid
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/student/{uuid.uuid4()}/")
        assert resp.status_code == 404

    def test_profile_by_level_counts(self, client_as, teacher_user, school, student_user):
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=1, points_deducted=5)
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=2, points_deducted=15)
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/student/{student_user.id}/")
        assert resp.status_code == 200
        by_level = resp.context["by_level"]
        assert by_level[1] == 1
        assert by_level[2] == 1

    def test_profile_status_color_yellow(self, client_as, teacher_user, school, student_user):
        """score = 100 - 25 = 75 => yellow (60<=score<80)"""
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=3, points_deducted=25)
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/student/{student_user.id}/")
        assert resp.context["status_color"] == "yellow"

    def test_profile_status_color_red(self, client_as, teacher_user, school, student_user):
        """score = 100 - 50 = 50 => red (<60)"""
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=3, points_deducted=25)
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=3, points_deducted=25)
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/student/{student_user.id}/")
        assert resp.context["status_color"] == "red"

    def test_profile_context_permissions(self, client_as, principal_user, school, student_user):
        client = client_as(principal_user)
        resp = client.get(f"/behavior/student/{student_user.id}/")
        assert resp.context["can_report"] is True
        assert resp.context["is_committee"] is True


# ══════════════════════════════════════════════════════════════
#  Point Recovery
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPointRecoveryExtended:

    def test_teacher_cannot_access_recovery(self, client_as, teacher_user, behavior_infraction):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/recovery/{behavior_infraction.id}/")
        assert resp.status_code == 302

    def test_recovery_already_exists(self, client_as, principal_user, school,
                                      student_user, teacher_user, behavior_infraction):
        BehaviorPointRecovery.objects.create(
            infraction=behavior_infraction, reason="سبب",
            points_restored=3, approved_by=principal_user,
        )
        client = client_as(principal_user)
        resp = client.get(f"/behavior/recovery/{behavior_infraction.id}/")
        assert resp.status_code == 302  # redirect — already processed

    def test_recovery_post_no_reason(self, client_as, principal_user, behavior_infraction):
        client = client_as(principal_user)
        resp = client.post(f"/behavior/recovery/{behavior_infraction.id}/", {
            "reason": "",
            "points_restored": 3,
        })
        assert resp.status_code == 200  # stays on form
        assert not BehaviorPointRecovery.objects.filter(infraction=behavior_infraction).exists()

    def test_recovery_post_zero_points(self, client_as, principal_user, behavior_infraction):
        client = client_as(principal_user)
        resp = client.post(f"/behavior/recovery/{behavior_infraction.id}/", {
            "reason": "سلوك إيجابي",
            "points_restored": 0,
        })
        assert resp.status_code == 200
        assert not BehaviorPointRecovery.objects.filter(infraction=behavior_infraction).exists()

    def test_recovery_post_exceeds_deducted(self, client_as, principal_user, behavior_infraction):
        client = client_as(principal_user)
        resp = client.post(f"/behavior/recovery/{behavior_infraction.id}/", {
            "reason": "سلوك إيجابي",
            "points_restored": 999,
        })
        assert resp.status_code == 200
        assert not BehaviorPointRecovery.objects.filter(infraction=behavior_infraction).exists()

    def test_recovery_marks_resolved(self, client_as, principal_user, behavior_infraction):
        client = client_as(principal_user)
        client.post(f"/behavior/recovery/{behavior_infraction.id}/", {
            "reason": "التزام تام",
            "points_restored": 3,
        })
        behavior_infraction.refresh_from_db()
        assert behavior_infraction.is_resolved is True

    def test_specialist_can_access_recovery(self, client_as, specialist_user, behavior_infraction):
        client = client_as(specialist_user)
        resp = client.get(f"/behavior/recovery/{behavior_infraction.id}/")
        assert resp.status_code == 200

    def test_superuser_can_access_recovery(self, client_as, superuser, behavior_infraction):
        client = client_as(superuser)
        resp = client.get(f"/behavior/recovery/{behavior_infraction.id}/")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
#  Committee Dashboard
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCommitteeDashboardExtended:

    def test_teacher_cannot_access_committee(self, client_as, teacher_user):
        client = client_as(teacher_user)
        resp = client.get("/behavior/committee/")
        assert resp.status_code == 403

    def test_student_cannot_access_committee(self, client_as, student_user):
        client = client_as(student_user)
        resp = client.get("/behavior/committee/")
        assert resp.status_code == 403

    def test_specialist_can_access_committee(self, client_as, specialist_user, school):
        client = client_as(specialist_user)
        resp = client.get("/behavior/committee/")
        assert resp.status_code == 200

    def test_vice_admin_can_access_committee(self, client_as, vice_admin_user, school):
        client = client_as(vice_admin_user)
        resp = client.get("/behavior/committee/")
        assert resp.status_code == 200

    def test_committee_context_keys(self, client_as, principal_user, school):
        client = client_as(principal_user)
        resp = client.get("/behavior/committee/")
        for key in ("open_cases", "resolved_cases", "stats"):
            assert key in resp.context

    def test_committee_stats_counts(self, client_as, principal_user, school,
                                     student_user, teacher_user):
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=3, is_resolved=False)
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=4, is_resolved=False)
        client = client_as(principal_user)
        resp = client.get("/behavior/committee/")
        stats = resp.context["stats"]
        assert stats["open_count"] == 2
        assert stats["level3"] == 1
        assert stats["level4"] == 1

    def test_committee_resolved_cases(self, client_as, principal_user, school,
                                       student_user, teacher_user):
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=3, is_resolved=True)
        client = client_as(principal_user)
        resp = client.get("/behavior/committee/")
        assert resp.context["stats"]["resolved_count"] == 1


# ══════════════════════════════════════════════════════════════
#  Committee Decision
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCommitteeDecisionExtended:

    def test_teacher_cannot_make_decision(self, client_as, teacher_user, level3_infraction):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/committee/{level3_infraction.id}/decision/")
        assert resp.status_code == 302

    def test_get_decision_form(self, client_as, principal_user, level3_infraction):
        client = client_as(principal_user)
        resp = client.get(f"/behavior/committee/{level3_infraction.id}/decision/")
        assert resp.status_code == 200
        assert "infraction" in resp.context

    def test_resolve_decision(self, client_as, principal_user, level3_infraction):
        client = client_as(principal_user)
        resp = client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "resolve",
            "action_taken": "حل المشكلة",
            "points_restored": 10,
            "recovery_reason": "التزام",
        })
        assert resp.status_code == 302
        level3_infraction.refresh_from_db()
        assert level3_infraction.is_resolved is True

    def test_resolve_creates_recovery(self, client_as, principal_user, level3_infraction):
        client = client_as(principal_user)
        client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "resolve",
            "action_taken": "حل",
            "points_restored": 5,
            "recovery_reason": "سلوك إيجابي",
        })
        assert BehaviorPointRecovery.objects.filter(infraction=level3_infraction).exists()

    def test_resolve_without_points(self, client_as, principal_user, level3_infraction):
        client = client_as(principal_user)
        client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "resolve",
            "action_taken": "إغلاق",
            "points_restored": 0,
        })
        level3_infraction.refresh_from_db()
        assert level3_infraction.is_resolved is True
        assert not BehaviorPointRecovery.objects.filter(infraction=level3_infraction).exists()

    def test_escalate_decision(self, client_as, principal_user, level3_infraction):
        client = client_as(principal_user)
        resp = client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "escalate",
            "action_taken": "تصعيد",
        })
        assert resp.status_code == 302
        level3_infraction.refresh_from_db()
        assert level3_infraction.level == 4

    def test_escalate_level4_stays_4(self, client_as, principal_user, level4_infraction):
        client = client_as(principal_user)
        client.post(f"/behavior/committee/{level4_infraction.id}/decision/", {
            "decision": "escalate",
        })
        level4_infraction.refresh_from_db()
        assert level4_infraction.level == 4

    def test_suspend_decision(self, client_as, principal_user, level3_infraction):
        client = client_as(principal_user)
        resp = client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "suspend",
            "action_taken": "إيقاف مؤقت لمدة يومين",
        })
        assert resp.status_code == 302
        level3_infraction.refresh_from_db()
        assert "إيقاف مؤقت" in level3_infraction.action_taken

    def test_unknown_decision(self, client_as, principal_user, level3_infraction):
        """Unknown decision type should still redirect."""
        client = client_as(principal_user)
        resp = client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "unknown_decision",
        })
        assert resp.status_code == 302

    def test_decision_404_for_level1(self, client_as, principal_user, behavior_infraction):
        """Level 1 infraction can't be accessed via committee decision."""
        client = client_as(principal_user)
        resp = client.get(f"/behavior/committee/{behavior_infraction.id}/decision/")
        assert resp.status_code == 404

    def test_decision_appends_action(self, client_as, principal_user, level3_infraction):
        level3_infraction.action_taken = "إجراء سابق"
        level3_infraction.save()
        client = client_as(principal_user)
        client.post(f"/behavior/committee/{level3_infraction.id}/decision/", {
            "decision": "resolve",
            "action_taken": "إجراء جديد",
            "points_restored": 0,
        })
        level3_infraction.refresh_from_db()
        assert "إجراء سابق" in level3_infraction.action_taken
        assert "إجراء جديد" in level3_infraction.action_taken


# ══════════════════════════════════════════════════════════════
#  Behavior Report (periodic report)
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorReport:

    def test_student_cannot_access_report(self, client_as, student_user):
        import uuid
        client = client_as(student_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        assert resp.status_code == 403

    def test_parent_cannot_access_report(self, client_as, parent_user, student_user):
        client = client_as(parent_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        assert resp.status_code == 403

    def test_teacher_can_access_report(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        assert resp.status_code == 200

    def test_report_default_period(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        assert resp.context["period"] == "full"

    def test_report_s1_period(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/?period=S1")
        assert resp.status_code == 200

    def test_report_s2_period(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/?period=S2")
        assert resp.status_code == 200

    def test_report_context_keys(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        for key in ("student", "infractions", "by_level", "total_deducted",
                     "total_restored", "net_score", "rating", "rating_color",
                     "period", "year", "parent_links", "period_choices"):
            assert key in resp.context, f"Missing context key: {key}"

    def test_report_net_score_no_infractions(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        assert resp.context["net_score"] == 100

    def test_report_404_nonexistent_student(self, client_as, teacher_user, school):
        import uuid
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{uuid.uuid4()}/")
        assert resp.status_code == 404

    def test_report_superuser_access(self, client_as, superuser, school, student_user):
        client = client_as(superuser)
        resp = client.get(f"/behavior/report/student/{student_user.id}/")
        assert resp.status_code == 200

    def test_report_year_param(self, client_as, teacher_user, school, student_user):
        client = client_as(teacher_user)
        resp = client.get(f"/behavior/report/student/{student_user.id}/?year=2024-2025")
        assert resp.context["year"] == "2024-2025"

    def test_report_post_send_no_parents(self, client_as, teacher_user, school, student_user):
        """POST send with no parent links => warning message."""
        client = client_as(teacher_user)
        resp = client.post(f"/behavior/report/student/{student_user.id}/", {
            "action": "send",
        })
        assert resp.status_code == 302  # redirects back

    @patch("notifications.services.NotificationService.send_email")
    def test_report_post_send_with_parent(
        self, mock_send, client_as, teacher_user, school, student_user, parent_user
    ):
        """POST send with parent email => sends email."""
        client = client_as(teacher_user)
        resp = client.post(f"/behavior/report/student/{student_user.id}/", {
            "action": "send",
        })
        assert resp.status_code == 302

    @patch("notifications.services.NotificationService.send_email", side_effect=Exception("SMTP error"))
    def test_report_post_send_email_fails(
        self, mock_send, client_as, teacher_user, school, student_user, parent_user
    ):
        """Email failure should not crash."""
        client = client_as(teacher_user)
        resp = client.post(f"/behavior/report/student/{student_user.id}/", {
            "action": "send",
        })
        assert resp.status_code == 302


# ══════════════════════════════════════════════════════════════
#  Behavior Statistics
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorStatistics:

    def test_teacher_cannot_access_statistics(self, client_as, teacher_user):
        client = client_as(teacher_user)
        resp = client.get("/behavior/statistics/")
        assert resp.status_code == 403

    def test_student_cannot_access_statistics(self, client_as, student_user):
        client = client_as(student_user)
        resp = client.get("/behavior/statistics/")
        assert resp.status_code == 403

    def test_principal_can_access_statistics(self, client_as, principal_user, school):
        client = client_as(principal_user)
        resp = client.get("/behavior/statistics/")
        assert resp.status_code == 200

    def test_specialist_can_access_statistics(self, client_as, specialist_user, school):
        client = client_as(specialist_user)
        resp = client.get("/behavior/statistics/")
        assert resp.status_code == 200

    def test_statistics_context_keys(self, client_as, principal_user, school):
        client = client_as(principal_user)
        resp = client.get("/behavior/statistics/")
        for key in ("by_level", "total", "top_students", "monthly",
                     "top_classes", "resolved_pct", "year"):
            assert key in resp.context, f"Missing context key: {key}"

    def test_statistics_year_param(self, client_as, principal_user, school):
        client = client_as(principal_user)
        resp = client.get("/behavior/statistics/?year=2024-2025")
        assert resp.context["year"] == "2024-2025"

    def test_statistics_empty(self, client_as, principal_user, school):
        client = client_as(principal_user)
        resp = client.get("/behavior/statistics/")
        assert resp.context["total"] == 0
        assert resp.context["resolved_pct"] == 0

    def test_statistics_with_data(self, client_as, principal_user, school,
                                   student_user, teacher_user):
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=1, points_deducted=5)
        BehaviorInfractionFactory(school=school, student=student_user,
                                   reported_by=teacher_user, level=2, points_deducted=15)
        client = client_as(principal_user)
        resp = client.get("/behavior/statistics/")
        assert resp.context["total"] >= 2
        assert resp.context["by_level"][1] >= 1
        assert resp.context["by_level"][2] >= 1


# ══════════════════════════════════════════════════════════════
#  PDF Views
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPDFViews:

    def test_warning_pdf_404_wrong_school(self, client_as, principal_user, school):
        """Infraction from another school => 404."""
        import uuid
        client = client_as(principal_user)
        resp = client.get(f"/behavior/infraction/{uuid.uuid4()}/pdf/warning/")
        assert resp.status_code == 404

    def test_parent_pdf_404_wrong_school(self, client_as, principal_user, school):
        import uuid
        client = client_as(principal_user)
        resp = client.get(f"/behavior/infraction/{uuid.uuid4()}/pdf/parent/")
        assert resp.status_code == 404

    def test_student_pdf_404_wrong_school(self, client_as, principal_user, school):
        import uuid
        client = client_as(principal_user)
        resp = client.get(f"/behavior/infraction/{uuid.uuid4()}/pdf/student/")
        assert resp.status_code == 404

    @patch("behavior.views._render_behavior_pdf")
    def test_warning_pdf_renders(self, mock_pdf, client_as, principal_user,
                                  school, behavior_infraction):
        from django.http import HttpResponse
        mock_pdf.return_value = HttpResponse(b"%PDF-1.4", content_type="application/pdf")
        client = client_as(principal_user)
        resp = client.get(f"/behavior/infraction/{behavior_infraction.id}/pdf/warning/")
        assert resp.status_code == 200
        mock_pdf.assert_called_once()

    @patch("behavior.views._render_behavior_pdf")
    def test_parent_pdf_renders(self, mock_pdf, client_as, principal_user,
                                 school, behavior_infraction):
        from django.http import HttpResponse
        mock_pdf.return_value = HttpResponse(b"%PDF-1.4", content_type="application/pdf")
        client = client_as(principal_user)
        resp = client.get(f"/behavior/infraction/{behavior_infraction.id}/pdf/parent/")
        assert resp.status_code == 200

    @patch("behavior.views._render_behavior_pdf")
    def test_student_pdf_renders(self, mock_pdf, client_as, principal_user,
                                  school, behavior_infraction):
        from django.http import HttpResponse
        mock_pdf.return_value = HttpResponse(b"%PDF-1.4", content_type="application/pdf")
        client = client_as(principal_user)
        resp = client.get(f"/behavior/infraction/{behavior_infraction.id}/pdf/student/")
        assert resp.status_code == 200

    def test_policy_pdf_missing_file(self, client_as, teacher_user, school):
        """Policy PDF returns 404 when file doesn't exist."""
        client = client_as(teacher_user)
        resp = client.get("/behavior/policy/pdf/")
        assert resp.status_code == 404

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    def test_policy_pdf_exists(self, mock_open, mock_exists,
                                client_as, teacher_user, school):
        """Policy PDF returns 200 when file exists."""
        import io
        mock_open.return_value = io.BytesIO(b"%PDF-1.4 test")
        client = client_as(teacher_user)
        resp = client.get("/behavior/policy/pdf/")
        assert resp.status_code == 200

    def test_pdf_requires_login(self, client, db, behavior_infraction):
        """Unauthenticated user should be redirected to login."""
        resp = client.get(f"/behavior/infraction/{behavior_infraction.id}/pdf/warning/")
        assert resp.status_code == 302
        assert "/login" in resp.url or "/accounts/login" in resp.url


# ══════════════════════════════════════════════════════════════
#  Auth - Login Required
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorLoginRequired:

    def test_dashboard_requires_login(self, client, db):
        resp = client.get("/behavior/dashboard/")
        assert resp.status_code == 302

    def test_report_requires_login(self, client, db):
        resp = client.get("/behavior/report/")
        assert resp.status_code == 302

    def test_committee_requires_login(self, client, db):
        resp = client.get("/behavior/committee/")
        assert resp.status_code == 302

    def test_statistics_requires_login(self, client, db):
        resp = client.get("/behavior/statistics/")
        assert resp.status_code == 302
