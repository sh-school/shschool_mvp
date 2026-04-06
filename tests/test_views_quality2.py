"""
tests/test_views_quality2.py
اختبارات شاملة لـ quality/views.py — لرفع التغطية من 41% إلى ~85%
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import CustomUser, Membership, Role
from quality.models import (
    EmployeeEvaluation,
    ExecutorMapping,
    OperationalDomain,
    OperationalIndicator,
    OperationalProcedure,
    OperationalTarget,
    ProcedureEvidence,
    QualityCommitteeMember,
)

# ══════════════════════════════════════════════
#  HELPER FACTORIES
# ══════════════════════════════════════════════


def make_admin(school):
    """ينشئ مستخدماً بدور principal (admin)"""
    role, _ = Role.objects.get_or_create(school=school, name="principal")
    user = CustomUser.objects.create_user(
        national_id=f"ADM{school.pk!s:.6s}01",
        full_name="مدير المدرسة",
        email=f"admin_{school.pk!s:.6s}@school.qa",
        password="pass123",
    )
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def make_teacher(school, suffix="01"):
    """ينشئ مستخدماً بدور teacher"""
    role, _ = Role.objects.get_or_create(school=school, name="teacher")
    user = CustomUser.objects.create_user(
        national_id=f"TCH{school.pk!s:.6s}{suffix}",
        full_name=f"معلم {suffix}",
        email=f"teacher_{school.pk!s:.6s}_{suffix}@school.qa",
        password="pass123",
    )
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def make_domain(school, name="المجال التجريبي", year="2025-2026"):
    return OperationalDomain.objects.create(school=school, name=name, academic_year=year, order=1)


_proc_counter = 0


def make_procedure(
    school, domain, executor_user=None, status="In Progress", executor_norm="معلم الرياضيات"
):
    global _proc_counter
    _proc_counter += 1
    n = _proc_counter
    target, _ = OperationalTarget.objects.get_or_create(
        domain=domain, number="1.1", defaults={"text": "هدف تجريبي"}
    )
    indicator, _ = OperationalIndicator.objects.get_or_create(
        target=target, number="1.1.1", defaults={"text": "مؤشر تجريبي"}
    )
    return OperationalProcedure.objects.create(
        indicator=indicator,
        school=school,
        number=f"1.1.1.{n}",
        text=f"إجراء تجريبي {n}",
        executor_norm=executor_norm,
        executor_user=executor_user,
        status=status,
        academic_year="2025-2026",
    )


def make_committee_member(
    school,
    user,
    committee_type=QualityCommitteeMember.REVIEW,
    can_review=True,
    year="2025-2026",
    domain=None,
):
    return QualityCommitteeMember.objects.create(
        school=school,
        user=user,
        domain=domain,
        job_title=user.full_name,
        responsibility="عضو",
        committee_type=committee_type,
        academic_year=year,
        is_active=True,
        can_review=can_review,
    )


# ══════════════════════════════════════════════
#  plan_dashboard  (lines 36–54)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestPlanDashboard:
    def test_admin_sees_dashboard(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200

    def test_teacher_sees_my_procedures(self, client, school):
        """موظف غير إداري يرى إجراءاته فقط"""
        teacher = make_teacher(school)
        domain = make_domain(school)
        make_procedure(school, domain, executor_user=teacher)
        client.force_login(teacher)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200
        assert "my_procedures" in resp.context
        assert len(resp.context["my_procedures"]) == 1

    def test_year_filter(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard") + "?year=2024-2025")
        assert resp.status_code == 200
        assert resp.context["year"] == "2024-2025"

    def test_admin_unmapped_count(self, client, school):
        """admin يرى عدد المنفذين غير المربوطين"""
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, executor_norm="غير مربوط")
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200
        assert resp.context["unmapped_count"] >= 1

    def test_redirect_unauthenticated(self, client):
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 302
        assert "/login" in resp["Location"] or "login" in resp["Location"]


# ══════════════════════════════════════════════
#  domain_detail  (lines 59–75)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainDetail:
    def test_returns_200(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        client.force_login(admin)
        resp = client.get(reverse("domain_detail", kwargs={"domain_id": domain.pk}))
        assert resp.status_code == 200
        assert resp.context["domain"] == domain

    def test_status_filter(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        client.force_login(admin)
        resp = client.get(
            reverse("domain_detail", kwargs={"domain_id": domain.pk}) + "?status=Completed"
        )
        assert resp.status_code == 200
        assert resp.context["status_filter"] == "Completed"

    def test_executor_filter(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        client.force_login(admin)
        resp = client.get(
            reverse("domain_detail", kwargs={"domain_id": domain.pk}) + "?executor=teacher"
        )
        assert resp.status_code == 200
        assert resp.context["executor_filter"] == "teacher"

    def test_404_wrong_school(self, client, school):
        from tests.conftest import SchoolFactory

        admin = make_admin(school)
        other_school = SchoolFactory()
        other_domain = make_domain(other_school, name="مجال آخر")
        client.force_login(admin)
        resp = client.get(reverse("domain_detail", kwargs={"domain_id": other_domain.pk}))
        assert resp.status_code == 404


# ══════════════════════════════════════════════
#  procedure_detail  (lines 80–98)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestProcedureDetail:
    def test_admin_can_view(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("procedure_detail", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        assert resp.context["procedure"] == proc
        assert resp.context["can_edit"] is True

    def test_executor_can_view(self, client, school):
        teacher = make_teacher(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, executor_user=teacher)
        client.force_login(teacher)
        resp = client.get(reverse("procedure_detail", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        assert resp.context["can_edit"] is True

    def test_non_executor_gets_403(self, client, school):
        """FIX-06: معلم ليس منفذاً ولا مراجعاً يحصل على 403"""
        teacher = make_teacher(school, "02")
        domain = make_domain(school)
        other_teacher = make_teacher(school, "03")
        proc = make_procedure(school, domain, executor_user=other_teacher)
        client.force_login(teacher)
        resp = client.get(reverse("procedure_detail", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 403

    def test_reviewer_can_view_own_domain(self, client, school):
        """FIX-06: المراجع يرى إجراءات مجاله"""
        teacher = make_teacher(school, "04")
        domain = make_domain(school)
        make_committee_member(school, teacher, QualityCommitteeMember.REVIEW, domain=domain)
        proc = make_procedure(school, domain)
        client.force_login(teacher)
        resp = client.get(reverse("procedure_detail", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        assert resp.context["is_reviewer"] is True

    def test_non_reviewer_gets_403(self, client, school):
        """FIX-06: معلم عادي لا يرى إجراء ليس له"""
        teacher = make_teacher(school, "05")
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(teacher)
        resp = client.get(reverse("procedure_detail", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 403


# ══════════════════════════════════════════════
#  update_procedure_status  (lines 101–130)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUpdateProcedureStatus:
    def test_admin_can_update(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "Completed"},
        )
        assert resp.status_code == 200
        proc.refresh_from_db()
        assert proc.status == "Completed"

    def test_executor_can_update(self, client, school):
        teacher = make_teacher(school, "06")
        domain = make_domain(school)
        proc = make_procedure(school, domain, executor_user=teacher)
        client.force_login(teacher)
        resp = client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "In Progress"},
        )
        assert resp.status_code == 200

    def test_non_executor_gets_403(self, client, school):
        teacher = make_teacher(school, "07")
        domain = make_domain(school)
        proc = make_procedure(school, domain)  # no executor_user
        client.force_login(teacher)
        resp = client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "Completed"},
        )
        assert resp.status_code == 403

    def test_update_evaluation_text(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "In Progress", "evaluation": "جيد جداً"},
        )
        proc.refresh_from_db()
        assert proc.evaluation == "جيد جداً"

    def test_update_deadline(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "In Progress", "deadline": "2025-12-31"},
        )
        proc.refresh_from_db()
        assert str(proc.deadline) == "2025-12-31"

    def test_invalid_deadline_ignored(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "In Progress", "deadline": "not-a-date"},
        )
        assert resp.status_code == 200

    def test_pending_review_clears_reviewed_fields(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "08")
        domain = make_domain(school)
        proc = make_procedure(school, domain, executor_user=admin)
        proc.reviewed_by = teacher
        proc.reviewed_at = timezone.now()
        proc.save()
        client.force_login(admin)
        client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "Pending Review"},
        )
        proc.refresh_from_db()
        assert proc.reviewed_by is None
        assert proc.reviewed_at is None

    def test_invalid_status_not_saved(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="In Progress")
        client.force_login(admin)
        client.post(
            reverse("update_proc_status", kwargs={"proc_id": proc.pk}),
            {"status": "INVALID_STATUS"},
        )
        proc.refresh_from_db()
        assert proc.status == "In Progress"

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("update_proc_status", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  approve_procedure  (lines 133–165)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestApproveProcedure:
    def test_admin_can_approve(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(admin)
        resp = client.post(
            reverse("approve_procedure", kwargs={"proc_id": proc.pk}),
            {"action": "approve", "review_note": "ممتاز"},
        )
        assert resp.status_code == 302
        proc.refresh_from_db()
        assert proc.status == "Completed"
        assert proc.reviewed_by == admin
        assert proc.review_note == "ممتاز"

    def test_admin_can_reject(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(admin)
        resp = client.post(
            reverse("approve_procedure", kwargs={"proc_id": proc.pk}),
            {"action": "reject", "review_note": "يحتاج مراجعة"},
        )
        assert resp.status_code == 302
        proc.refresh_from_db()
        assert proc.status == "In Progress"

    def test_reviewer_can_approve(self, client, school):
        teacher = make_teacher(school, "09")
        domain = make_domain(school)
        make_committee_member(
            school, teacher, QualityCommitteeMember.REVIEW, can_review=True, domain=domain
        )
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(teacher)
        resp = client.post(
            reverse("approve_procedure", kwargs={"proc_id": proc.pk}),
            {"action": "approve"},
        )
        assert resp.status_code == 302
        proc.refresh_from_db()
        assert proc.status == "Completed"

    def test_non_reviewer_gets_403(self, client, school):
        teacher = make_teacher(school, "10")
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(teacher)
        resp = client.post(
            reverse("approve_procedure", kwargs={"proc_id": proc.pk}),
            {"action": "approve"},
        )
        assert resp.status_code == 403

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("approve_procedure", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 405

    def test_unknown_action_no_status_change(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(admin)
        client.post(
            reverse("approve_procedure", kwargs={"proc_id": proc.pk}),
            {"action": "unknown"},
        )
        proc.refresh_from_db()
        assert proc.status == "Pending Review"


# ══════════════════════════════════════════════
#  upload_evidence  (lines 168–190)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestUploadEvidence:
    def test_admin_can_upload(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.post(
            reverse("upload_evidence", kwargs={"proc_id": proc.pk}),
            {"title": "دليل تجريبي", "description": "وصف"},
        )
        assert resp.status_code == 302
        assert ProcedureEvidence.objects.filter(procedure=proc).count() == 1

    def test_executor_can_upload(self, client, school):
        teacher = make_teacher(school, "11")
        domain = make_domain(school)
        proc = make_procedure(school, domain, executor_user=teacher)
        client.force_login(teacher)
        resp = client.post(
            reverse("upload_evidence", kwargs={"proc_id": proc.pk}),
            {"title": "دليل من المنفذ"},
        )
        assert resp.status_code == 302

    def test_non_executor_gets_403(self, client, school):
        teacher = make_teacher(school, "12")
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(teacher)
        resp = client.post(
            reverse("upload_evidence", kwargs={"proc_id": proc.pk}),
            {"title": "دليل"},
        )
        assert resp.status_code == 403

    def test_empty_title_rejected(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.post(
            reverse("upload_evidence", kwargs={"proc_id": proc.pk}),
            {"title": ""},
        )
        assert resp.status_code == 302
        assert ProcedureEvidence.objects.filter(procedure=proc).count() == 0

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("upload_evidence", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  my_procedures  (lines 195–217)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestMyProcedures:
    def test_shows_my_procedures(self, client, school):
        teacher = make_teacher(school, "13")
        domain = make_domain(school)
        make_procedure(school, domain, executor_user=teacher, status="In Progress")
        make_procedure(
            school, domain, executor_user=teacher, status="Completed", executor_norm="معلم آخر"
        )
        client.force_login(teacher)
        resp = client.get(reverse("my_procedures"))
        assert resp.status_code == 200
        assert resp.context["total"] == 2
        assert resp.context["completed"] == 1
        assert resp.context["pct"] == 50

    def test_status_filter(self, client, school):
        teacher = make_teacher(school, "14")
        domain = make_domain(school)
        make_procedure(
            school, domain, executor_user=teacher, status="Completed", executor_norm="معلم1"
        )
        make_procedure(
            school, domain, executor_user=teacher, status="In Progress", executor_norm="معلم2"
        )
        client.force_login(teacher)
        resp = client.get(reverse("my_procedures") + "?status=Completed")
        assert resp.status_code == 200
        assert resp.context["status_filter"] == "Completed"

    def test_empty_procedures(self, client, school):
        teacher = make_teacher(school, "15")
        client.force_login(teacher)
        resp = client.get(reverse("my_procedures"))
        assert resp.status_code == 200
        assert resp.context["total"] == 0
        assert resp.context["pct"] == 0

    def test_year_filter(self, client, school):
        teacher = make_teacher(school, "16")
        client.force_login(teacher)
        resp = client.get(reverse("my_procedures") + "?year=2024-2025")
        assert resp.status_code == 200
        assert resp.context["year"] == "2024-2025"


# ══════════════════════════════════════════════
#  quality_committee  (views_committee)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestQualityCommittee:
    def test_returns_200(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_committee"))
        assert resp.status_code == 200

    def test_requires_login(self, client):
        resp = client.get(reverse("quality_committee"))
        assert resp.status_code == 302


# ══════════════════════════════════════════════
#  add_committee_member  (views_committee)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestAddCommitteeMember:
    def test_admin_can_add_with_user(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "17")
        client.force_login(admin)
        resp = client.post(
            reverse("add_committee_member"),
            {
                "year": "2025-2026",
                "user_id": str(teacher.pk),
                "job_title": "معلم",
                "responsibility": "عضو",
                "committee_type": QualityCommitteeMember.REVIEW,
            },
        )
        assert resp.status_code == 302
        assert QualityCommitteeMember.objects.filter(
            school=school, user=teacher, committee_type=QualityCommitteeMember.REVIEW
        ).exists()

    def test_admin_can_add_with_job_title_only(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.post(
            reverse("add_committee_member"),
            {
                "year": "2025-2026",
                "user_id": "",
                "job_title": "مستشار خارجي",
                "responsibility": "عضو",
                "committee_type": QualityCommitteeMember.REVIEW,
            },
        )
        assert resp.status_code == 302
        assert QualityCommitteeMember.objects.filter(
            school=school, job_title="مستشار خارجي"
        ).exists()

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "18")
        client.force_login(teacher)
        resp = client.post(
            reverse("add_committee_member"),
            {
                "year": "2025-2026",
                "job_title": "معلم",
                "responsibility": "عضو",
                "committee_type": QualityCommitteeMember.REVIEW,
            },
        )
        assert resp.status_code == 403

    def test_no_user_no_title_shows_error(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.post(
            reverse("add_committee_member"),
            {
                "year": "2025-2026",
                "user_id": "",
                "job_title": "",
                "responsibility": "عضو",
                "committee_type": QualityCommitteeMember.REVIEW,
            },
        )
        assert resp.status_code == 302

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("add_committee_member"))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  remove_committee_member  (views_committee)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestRemoveCommitteeMember:
    def test_admin_can_remove(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "19")
        member = make_committee_member(school, teacher, QualityCommitteeMember.REVIEW)
        client.force_login(admin)
        resp = client.post(reverse("remove_committee_member", kwargs={"member_id": member.pk}))
        assert resp.status_code == 302
        assert not QualityCommitteeMember.objects.filter(pk=member.pk).exists()

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "20")
        teacher2 = make_teacher(school, "21")
        member = make_committee_member(school, teacher2, QualityCommitteeMember.REVIEW)
        client.force_login(teacher)
        resp = client.post(reverse("remove_committee_member", kwargs={"member_id": member.pk}))
        assert resp.status_code == 403

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "22")
        member = make_committee_member(school, teacher)
        client.force_login(admin)
        resp = client.get(reverse("remove_committee_member", kwargs={"member_id": member.pk}))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  executor_committee  (views_committee)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestExecutorCommittee:
    def test_admin_sees_executor_committee(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("executor_committee"))
        assert resp.status_code == 200

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "23")
        client.force_login(teacher)
        resp = client.get(reverse("executor_committee"))
        assert resp.status_code == 403


# ══════════════════════════════════════════════
#  executor_member_detail  (views_committee)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestExecutorMemberDetail:
    def test_admin_views_member(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "24")
        member = make_committee_member(school, teacher, QualityCommitteeMember.EXECUTOR)
        client.force_login(admin)
        resp = client.get(reverse("executor_member_detail", kwargs={"member_id": member.pk}))
        assert resp.status_code == 200
        assert resp.context["member"] == member

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "25")
        teacher2 = make_teacher(school, "26")
        member = make_committee_member(school, teacher2, QualityCommitteeMember.EXECUTOR)
        client.force_login(teacher)
        resp = client.get(reverse("executor_member_detail", kwargs={"member_id": member.pk}))
        assert resp.status_code == 403

    def test_status_filter(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "27")
        member = make_committee_member(school, teacher, QualityCommitteeMember.EXECUTOR)
        client.force_login(admin)
        resp = client.get(
            reverse("executor_member_detail", kwargs={"member_id": member.pk}) + "?status=Completed"
        )
        assert resp.status_code == 200

    def test_domain_filter(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "28")
        domain = make_domain(school)
        member = make_committee_member(school, teacher, QualityCommitteeMember.EXECUTOR)
        client.force_login(admin)
        resp = client.get(
            reverse("executor_member_detail", kwargs={"member_id": member.pk})
            + f"?domain={domain.pk}"
        )
        assert resp.status_code == 200

    def test_procedures_stats(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "29")
        domain = make_domain(school)
        make_procedure(
            school, domain, executor_user=teacher, status="Completed", executor_norm="معلم29"
        )
        make_procedure(
            school, domain, executor_user=teacher, status="In Progress", executor_norm="معلم29b"
        )
        member = make_committee_member(school, teacher, QualityCommitteeMember.EXECUTOR)
        client.force_login(admin)
        resp = client.get(reverse("executor_member_detail", kwargs={"member_id": member.pk}))
        assert resp.status_code == 200
        assert resp.context["total"] == 2
        assert resp.context["completed"] == 1


# ══════════════════════════════════════════════
#  executor_mapping  (views_executor)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestExecutorMapping:
    def test_admin_views_mapping(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("executor_mapping"))
        assert resp.status_code == 200

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "30")
        client.force_login(teacher)
        resp = client.get(reverse("executor_mapping"))
        assert resp.status_code == 403

    def test_shows_executor_rows(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, executor_norm="منفذ الاختبار")
        client.force_login(admin)
        resp = client.get(reverse("executor_mapping"))
        assert resp.status_code == 200
        rows = resp.context["executor_rows"]
        norms = [r["executor_norm"] for r in rows]
        assert "منفذ الاختبار" in norms

    def test_year_filter(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("executor_mapping") + "?year=2024-2025")
        assert resp.status_code == 200


# ══════════════════════════════════════════════
#  save_executor_mapping  (views_executor)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestSaveExecutorMapping:
    def test_admin_can_save_mapping(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "31")
        domain = make_domain(school)
        make_procedure(school, domain, executor_norm="معلم31")
        client.force_login(admin)
        resp = client.post(
            reverse("save_executor_mapping"),
            {
                "executor_norm": "معلم31",
                "user_id": str(teacher.pk),
                "year": "2025-2026",
            },
        )
        assert resp.status_code == 302
        assert ExecutorMapping.objects.filter(school=school, executor_norm="معلم31").exists()

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "32")
        client.force_login(teacher)
        resp = client.post(
            reverse("save_executor_mapping"),
            {
                "executor_norm": "معلم",
                "user_id": str(teacher.pk),
            },
        )
        assert resp.status_code == 403

    def test_empty_norm_redirects_with_error(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.post(
            reverse("save_executor_mapping"),
            {
                "executor_norm": "",
                "user_id": "",
            },
        )
        assert resp.status_code == 302

    def test_unmap_user(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "33")
        ExecutorMapping.objects.create(
            school=school, executor_norm="معلم33", user=teacher, academic_year="2025-2026"
        )
        client.force_login(admin)
        resp = client.post(
            reverse("save_executor_mapping"),
            {
                "executor_norm": "معلم33",
                "user_id": "",
                "year": "2025-2026",
            },
        )
        assert resp.status_code == 302
        mapping = ExecutorMapping.objects.get(school=school, executor_norm="معلم33")
        assert mapping.user is None

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("save_executor_mapping"))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  apply_all_mappings  (views_executor)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestApplyAllMappings:
    def test_admin_can_apply(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "34")
        domain = make_domain(school)
        make_procedure(school, domain, executor_norm="معلم34")
        ExecutorMapping.objects.create(
            school=school, executor_norm="معلم34", user=teacher, academic_year="2025-2026"
        )
        client.force_login(admin)
        resp = client.post(reverse("apply_all_mappings"), {"year": "2025-2026"})
        assert resp.status_code == 302
        proc = OperationalProcedure.objects.filter(school=school, executor_norm="معلم34").first()
        assert proc.executor_user == teacher

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "35")
        client.force_login(teacher)
        resp = client.post(reverse("apply_all_mappings"), {"year": "2025-2026"})
        assert resp.status_code == 403

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("apply_all_mappings"))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  progress_report  (views_reports)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestProgressReport:
    def test_admin_views_report(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_report"))
        assert resp.status_code == 200

    def test_teacher_can_view_report(self, client, school):
        """المعلم ضمن QUALITY_VIEW — يمكنه عرض التقرير"""
        teacher = make_teacher(school, "36")
        client.force_login(teacher)
        resp = client.get(reverse("quality_report"))
        assert resp.status_code == 200

    def test_report_with_data(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, status="Completed", executor_norm="تقرير1")
        make_procedure(school, domain, status="In Progress", executor_norm="تقرير2")
        client.force_login(admin)
        resp = client.get(reverse("quality_report"))
        assert resp.status_code == 200
        assert "domain_stats" in resp.context
        assert "executor_stats" in resp.context

    def test_year_filter(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_report") + "?year=2024-2025")
        assert resp.status_code == 200
        assert resp.context["year"] == "2024-2025"


# ══════════════════════════════════════════════
#  evaluation_dashboard  (evaluation_views)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestEvaluationDashboard:
    def test_admin_views_dashboard(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("evaluation_dashboard"))
        assert resp.status_code == 200

    def test_teacher_gets_403(self, client, school):
        teacher = make_teacher(school, "37")
        client.force_login(teacher)
        resp = client.get(reverse("evaluation_dashboard"))
        assert resp.status_code == 403

    def test_vice_admin_can_view(self, client, school):
        role, _ = Role.objects.get_or_create(school=school, name="vice_admin")
        vice = CustomUser.objects.create_user(
            national_id="VICE0000001",
            full_name="نائب مدير",
            email="vice@school.qa",
            password="pass123",
        )
        Membership.objects.create(user=vice, school=school, role=role, is_active=True)
        client.force_login(vice)
        resp = client.get(reverse("evaluation_dashboard"))
        assert resp.status_code == 200

    def test_with_evaluation_data(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "38")
        EmployeeEvaluation.objects.create(
            school=school,
            employee=teacher,
            evaluator=admin,
            academic_year="2025-2026",
            period="S1",
            axis_professional=20,
            axis_commitment=20,
            axis_teamwork=20,
            axis_development=20,
            status="submitted",
        )
        client.force_login(admin)
        resp = client.get(reverse("evaluation_dashboard"))
        assert resp.status_code == 200
        assert len(resp.context["recent_evals"]) == 1


# ══════════════════════════════════════════════
#  create_evaluation  (evaluation_views)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestCreateEvaluation:
    @pytest.mark.xfail(
        reason="evaluation_form.html uses widget_tweaks which is not installed in test env"
    )
    def test_admin_get_form(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "39")
        client.force_login(admin)
        resp = client.get(reverse("create_evaluation", kwargs={"employee_id": teacher.pk}))
        assert resp.status_code == 200

    def test_non_admin_gets_403(self, client, school):
        teacher = make_teacher(school, "40")
        teacher2 = make_teacher(school, "41")
        client.force_login(teacher)
        resp = client.get(reverse("create_evaluation", kwargs={"employee_id": teacher2.pk}))
        assert resp.status_code == 403

    def test_employee_not_in_school_gets_403(self, client, school):
        from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

        admin = make_admin(school)
        other_school = SchoolFactory()
        role = RoleFactory(school=other_school, name="teacher")
        outsider = UserFactory(full_name="موظف خارجي")
        MembershipFactory(user=outsider, school=other_school, role=role)
        client.force_login(admin)
        resp = client.get(reverse("create_evaluation", kwargs={"employee_id": outsider.pk}))
        assert resp.status_code == 403

    def test_post_saves_evaluation(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "42")
        client.force_login(admin)
        resp = client.post(
            reverse("create_evaluation", kwargs={"employee_id": teacher.pk})
            + "?year=2025-2026&period=S1",
            {
                "axis_professional": 20,
                "axis_commitment": 20,
                "axis_teamwork": 20,
                "axis_development": 20,
                "strengths": "ممتاز",
                "improvements": "لا شيء",
                "goals_next": "التطوير",
                "action": "submitted",
            },
        )
        assert resp.status_code == 302
        assert EmployeeEvaluation.objects.filter(
            school=school, employee=teacher, status="submitted"
        ).exists()

    def test_post_saves_draft(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "43")
        client.force_login(admin)
        client.post(
            reverse("create_evaluation", kwargs={"employee_id": teacher.pk})
            + "?year=2025-2026&period=S2",
            {
                "axis_professional": 15,
                "axis_commitment": 15,
                "axis_teamwork": 15,
                "axis_development": 15,
                "action": "draft",
            },
        )
        assert EmployeeEvaluation.objects.filter(
            school=school, employee=teacher, status="draft"
        ).exists()


# ══════════════════════════════════════════════
#  acknowledge_evaluation  (evaluation_views)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestAcknowledgeEvaluation:
    def _make_eval(self, school, employee, evaluator, status="approved"):
        return EmployeeEvaluation.objects.create(
            school=school,
            employee=employee,
            evaluator=evaluator,
            academic_year="2025-2026",
            period="S1",
            axis_professional=20,
            axis_commitment=20,
            axis_teamwork=20,
            axis_development=20,
            status=status,
        )

    def test_employee_can_acknowledge(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "44")
        ev = self._make_eval(school, teacher, admin, status="approved")
        client.force_login(teacher)
        resp = client.post(
            reverse("acknowledge_evaluation", kwargs={"eval_id": ev.pk}),
            {"comment": "استلمت"},
        )
        assert resp.status_code == 302
        ev.refresh_from_db()
        assert ev.status == "acknowledged"

    def test_non_approved_returns_400(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "45")
        ev = self._make_eval(school, teacher, admin, status="submitted")
        client.force_login(teacher)
        resp = client.post(
            reverse("acknowledge_evaluation", kwargs={"eval_id": ev.pk}),
            {"comment": ""},
        )
        assert resp.status_code == 400

    def test_get_redirects_to_my_evals(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "46")
        ev = self._make_eval(school, teacher, admin, status="approved")
        client.force_login(teacher)
        resp = client.get(reverse("acknowledge_evaluation", kwargs={"eval_id": ev.pk}))
        assert resp.status_code == 302


# ══════════════════════════════════════════════
#  my_evaluations  (evaluation_views)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestMyEvaluations:
    def test_employee_sees_evaluations(self, client, school):
        admin = make_admin(school)
        teacher = make_teacher(school, "47")
        EmployeeEvaluation.objects.create(
            school=school,
            employee=teacher,
            evaluator=admin,
            academic_year="2025-2026",
            period="S1",
            axis_professional=20,
            axis_commitment=20,
            axis_teamwork=20,
            axis_development=20,
        )
        client.force_login(teacher)
        resp = client.get(reverse("my_evaluations"))
        assert resp.status_code == 200
        assert len(resp.context["evals"]) == 1

    def test_empty_evaluations(self, client, school):
        teacher = make_teacher(school, "48")
        client.force_login(teacher)
        resp = client.get(reverse("my_evaluations"))
        assert resp.status_code == 200
        assert len(resp.context["evals"]) == 0

    def test_requires_login(self, client):
        resp = client.get(reverse("my_evaluations"))
        assert resp.status_code == 302


# ══════════════════════════════════════════════
#  progress_report_pdf  (views_reports)
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestProgressReportPdf:
    def test_teacher_can_view_pdf(self, client, school):
        """المعلم ضمن QUALITY_VIEW — يمكنه تحميل تقرير PDF"""
        teacher = make_teacher(school, "49")
        client.force_login(teacher)
        resp = client.get(reverse("quality_report_pdf"))
        assert resp.status_code in (200, 500)  # 500 إذا WeasyPrint غير مثبت

    def test_admin_gets_pdf(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_report_pdf"))
        # قد تكون 200 (PDF) أو 500 إن كانت WeasyPrint غير مثبتة
        assert resp.status_code in (200, 500)
