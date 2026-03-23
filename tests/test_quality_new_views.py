"""
tests/test_quality_new_views.py
اختبارات الـ Views الجديدة لمنظومة الجودة (execution_list, review_list, modals, toggle_evidence)
"""

import pytest
from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import CustomUser, Membership, Role
from quality.models import (
    OperationalDomain,
    OperationalTarget,
    OperationalIndicator,
    OperationalProcedure,
    ProcedureEvidence,
    ProcedureStatusLog,
    QualityCommitteeMember,
)

# ══════════════════════════════════════════════
#  HELPER FACTORIES (same pattern as test_views_quality2.py)
# ══════════════════════════════════════════════

_counter = 0


def _next():
    global _counter
    _counter += 1
    return _counter


def make_admin(school):
    """ينشئ مستخدماً بدور principal (admin)"""
    n = _next()
    role, _ = Role.objects.get_or_create(school=school, name="principal")
    user = CustomUser.objects.create_user(
        national_id=f"ADMN{school.pk!s:.4s}{n:03d}",
        full_name="مدير المدرسة",
        email=f"admin_nv_{school.pk!s:.4s}_{n}@school.qa",
        password="pass123",
    )
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def make_teacher(school, suffix=None):
    """ينشئ مستخدماً بدور teacher"""
    n = _next()
    suffix = suffix or f"T{n}"
    role, _ = Role.objects.get_or_create(school=school, name="teacher")
    user = CustomUser.objects.create_user(
        national_id=f"TCHN{school.pk!s:.4s}{n:03d}",
        full_name=f"معلم {suffix}",
        email=f"teacher_nv_{school.pk!s:.4s}_{n}@school.qa",
        password="pass123",
    )
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def make_domain(school, name="المجال التجريبي", year="2025-2026"):
    n = _next()
    return OperationalDomain.objects.create(
        school=school, name=f"{name} {n}", academic_year=year, order=n
    )


def make_procedure(
    school,
    domain,
    executor_user=None,
    status="In Progress",
    executor_norm="معلم الرياضيات",
    deadline=None,
    evidence_request_status="not_requested",
    academic_year="2025-2026",
):
    n = _next()
    target, _ = OperationalTarget.objects.get_or_create(
        domain=domain, number=f"T{domain.pk!s:.4s}",
        defaults={"text": "هدف تجريبي"},
    )
    indicator, _ = OperationalIndicator.objects.get_or_create(
        target=target, number=f"I{domain.pk!s:.4s}",
        defaults={"text": "مؤشر تجريبي"},
    )
    return OperationalProcedure.objects.create(
        indicator=indicator,
        school=school,
        number=f"P{n:04d}",
        text=f"إجراء تجريبي {n}",
        executor_norm=executor_norm,
        executor_user=executor_user,
        status=status,
        deadline=deadline,
        evidence_request_status=evidence_request_status,
        academic_year=academic_year,
    )


def make_committee_member(
    school,
    user,
    committee_type=QualityCommitteeMember.REVIEW,
    can_review=True,
    year="2025-2026",
):
    return QualityCommitteeMember.objects.create(
        school=school,
        user=user,
        job_title=user.full_name,
        responsibility="عضو",
        committee_type=committee_type,
        academic_year=year,
        is_active=True,
        can_review=can_review,
    )


# ══════════════════════════════════════════════
#  1. TestExecutionList
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestExecutionList:
    """اختبارات قائمة التنفيذ execution_list."""

    def test_admin_sees_page(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("execution_list"))
        assert resp.status_code == 200
        assert "page_obj" in resp.context

    def test_teacher_sees_page(self, client, school):
        """المعلم يمكنه عرض قائمة التنفيذ"""
        teacher = make_teacher(school)
        client.force_login(teacher)
        resp = client.get(reverse("execution_list"))
        assert resp.status_code == 200

    def test_unauthenticated_redirects(self, client):
        resp = client.get(reverse("execution_list"))
        assert resp.status_code == 302
        assert "login" in resp["Location"].lower()

    def test_filter_by_status(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, status="Completed")
        make_procedure(school, domain, status="In Progress")
        client.force_login(admin)
        resp = client.get(reverse("execution_list") + "?status=Completed")
        assert resp.status_code == 200
        procs = list(resp.context["page_obj"])
        assert all(p.status == "Completed" for p in procs)

    def test_filter_by_domain(self, client, school):
        admin = make_admin(school)
        domain_a = make_domain(school, name="مجال أ")
        domain_b = make_domain(school, name="مجال ب")
        make_procedure(school, domain_a)
        make_procedure(school, domain_b)
        client.force_login(admin)
        resp = client.get(reverse("execution_list") + f"?field={domain_a.pk}")
        assert resp.status_code == 200
        procs = list(resp.context["page_obj"])
        # All returned procs should belong to domain_a
        for p in procs:
            assert p.indicator.target.domain_id == domain_a.pk

    def test_filter_by_executor(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, executor_norm="معلم العلوم")
        make_procedure(school, domain, executor_norm="معلم الرياضيات")
        client.force_login(admin)
        resp = client.get(reverse("execution_list") + "?executor=العلوم")
        assert resp.status_code == 200
        procs = list(resp.context["page_obj"])
        assert all("العلوم" in p.executor_norm for p in procs)

    def test_pagination_default_25(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        for _ in range(30):
            make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("execution_list"))
        assert resp.status_code == 200
        assert resp.context["page_obj"].paginator.per_page == 25

    def test_pagination_custom(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        for _ in range(60):
            make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("execution_list") + "?per_page=50")
        assert resp.status_code == 200
        assert resp.context["page_obj"].paginator.per_page == 50

    def test_pagination_all(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        for _ in range(5):
            make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("execution_list") + "?per_page=all")
        assert resp.status_code == 200
        assert resp.context["current_per_page"] == "all"
        # All items on one page
        assert len(resp.context["page_obj"]) >= 5

    def test_empty_state(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("execution_list"))
        assert resp.status_code == 200
        assert len(resp.context["page_obj"]) == 0


# ══════════════════════════════════════════════
#  2. TestReviewList
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestReviewList:
    """اختبارات قائمة المراجعة review_list."""

    def test_admin_sees_page(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("review_list"))
        assert resp.status_code == 200

    def test_reviewer_sees_page(self, client, school):
        """عضو لجنة المراجعة يمكنه عرض قائمة المراجعة"""
        teacher = make_teacher(school)
        make_committee_member(school, teacher, QualityCommitteeMember.REVIEW)
        client.force_login(teacher)
        resp = client.get(reverse("review_list"))
        assert resp.status_code == 200

    def test_teacher_forbidden(self, client, school):
        """معلم عادي لا يمكنه الوصول لقائمة المراجعة"""
        teacher = make_teacher(school)
        client.force_login(teacher)
        resp = client.get(reverse("review_list"))
        assert resp.status_code == 403

    def test_filter_by_evidence_request(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, evidence_request_status="requested")
        make_procedure(school, domain, evidence_request_status="not_requested")
        client.force_login(admin)
        resp = client.get(reverse("review_list") + "?evidence_req=1")
        assert resp.status_code == 200
        procs = list(resp.context["page_obj"])
        assert all(p.evidence_request_status == "requested" for p in procs)

    def test_context_has_is_reviewer(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("review_list"))
        assert resp.status_code == 200
        assert "is_reviewer" in resp.context
        assert resp.context["is_reviewer"] is True


# ══════════════════════════════════════════════
#  3. TestTaskUpdateModal
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestTaskUpdateModal:
    """اختبارات modal تحديث الإجراء task_update_modal."""

    def test_get_returns_modal_html(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("task_update_modal", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        # Modal partial should not extend base.html (check it renders successfully)
        assert "task" in resp.context

    def test_post_updates_fields(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.post(
            reverse("task_update_modal", kwargs={"proc_id": proc.pk}),
            {
                "follow_up": "تم الإنجاز",
                "comments": "ملاحظات التحديث",
                "evidence_type": "وصفي",
                "status": "In Progress",
            },
        )
        # POST should redirect
        assert resp.status_code in (200, 302)
        proc.refresh_from_db()
        assert proc.follow_up == "تم الإنجاز"
        assert proc.comments == "ملاحظات التحديث"
        assert proc.evidence_type == "وصفي"

    def test_post_creates_status_log(self, client, school):
        """تغيير الحالة ينشئ سجلاً في ProcedureStatusLog"""
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="In Progress")
        client.force_login(admin)
        client.post(
            reverse("task_update_modal", kwargs={"proc_id": proc.pk}),
            {"status": "Pending Review", "comments": "جاهز للمراجعة"},
        )
        proc.refresh_from_db()
        assert proc.status == "Pending Review"
        log = ProcedureStatusLog.objects.filter(procedure=proc).first()
        assert log is not None
        assert log.old_status == "In Progress"
        assert log.new_status == "Pending Review"
        assert log.changed_by == admin

    def test_post_with_file_upload(self, client, school):
        """رفع ملف عبر modal ينشئ ProcedureEvidence"""
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        fake_file = SimpleUploadedFile("evidence.pdf", b"PDF content", content_type="application/pdf")
        client.post(
            reverse("task_update_modal", kwargs={"proc_id": proc.pk}),
            {
                "status": "In Progress",
                "evidence_file": fake_file,
                "evidence_title": "دليل الإجراء",
            },
        )
        assert ProcedureEvidence.objects.filter(procedure=proc).exists()
        ev = ProcedureEvidence.objects.filter(procedure=proc).first()
        assert ev.title == "دليل الإجراء"
        assert ev.uploaded_by == admin

    def test_non_executor_cannot_edit(self, client, school):
        """معلم ليس منفذاً يحصل على modal للعرض فقط (GET يعمل, POST يرفض)"""
        executor = make_teacher(school)
        other_teacher = make_teacher(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, executor_user=executor)
        client.force_login(other_teacher)
        # GET should work but is_executor=False
        resp = client.get(reverse("task_update_modal", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        assert resp.context["is_executor"] is False
        # POST should be forbidden
        resp = client.post(
            reverse("task_update_modal", kwargs={"proc_id": proc.pk}),
            {"status": "Completed"},
        )
        assert resp.status_code == 403

    def test_admin_can_always_edit(self, client, school):
        """المدير يستطيع تحرير أي إجراء"""
        admin = make_admin(school)
        teacher = make_teacher(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, executor_user=teacher)
        client.force_login(admin)
        resp = client.get(reverse("task_update_modal", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        assert resp.context["is_executor"] is True
        # Admin can POST too
        resp = client.post(
            reverse("task_update_modal", kwargs={"proc_id": proc.pk}),
            {"status": "Completed", "comments": "اعتمد من المدير"},
        )
        assert resp.status_code in (200, 302)
        proc.refresh_from_db()
        assert proc.status == "Completed"


# ══════════════════════════════════════════════
#  4. TestReviewEvaluateModal
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestReviewEvaluateModal:
    """اختبارات modal تقييم المراجعة review_evaluate_modal."""

    def test_get_returns_modal(self, client, school):
        reviewer = make_teacher(school)
        make_committee_member(school, reviewer, QualityCommitteeMember.REVIEW)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(reviewer)
        resp = client.get(reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 200
        assert "task" in resp.context

    def test_post_updates_review_fields(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(admin)
        resp = client.post(
            reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}),
            {
                "quality_rating": "متحقق",
                "review_note": "عمل ممتاز",
                "status": "Completed",
            },
        )
        assert resp.status_code in (200, 302)
        proc.refresh_from_db()
        assert proc.quality_rating == "متحقق"
        assert proc.review_note == "عمل ممتاز"
        assert proc.status == "Completed"

    def test_post_creates_status_log(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        client.force_login(admin)
        client.post(
            reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}),
            {"status": "Completed", "review_note": "تمت الموافقة"},
        )
        log = ProcedureStatusLog.objects.filter(procedure=proc).first()
        assert log is not None
        assert log.old_status == "Pending Review"
        assert log.new_status == "Completed"

    def test_evidence_request_update(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        client.post(
            reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}),
            {
                "evidence_request_status": "requested",
                "evidence_request_note": "نحتاج مستندات إضافية",
                "status": proc.status,
            },
        )
        proc.refresh_from_db()
        assert proc.evidence_request_status == "requested"
        assert proc.evidence_request_note == "نحتاج مستندات إضافية"

    def test_sets_reviewed_by(self, client, school):
        reviewer = make_teacher(school)
        make_committee_member(school, reviewer, QualityCommitteeMember.REVIEW)
        domain = make_domain(school)
        proc = make_procedure(school, domain, status="Pending Review")
        assert proc.reviewed_by is None
        assert proc.reviewed_at is None
        client.force_login(reviewer)
        client.post(
            reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}),
            {"status": "Completed", "review_note": "مقبول"},
        )
        proc.refresh_from_db()
        assert proc.reviewed_by == reviewer
        assert proc.reviewed_at is not None

    def test_non_reviewer_forbidden(self, client, school):
        teacher = make_teacher(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(teacher)
        # GET should be forbidden
        resp = client.get(reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 403
        # POST should also be forbidden
        resp = client.post(
            reverse("review_evaluate_modal", kwargs={"proc_id": proc.pk}),
            {"status": "Completed"},
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════
#  5. TestToggleEvidenceRequest
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestToggleEvidenceRequest:
    """اختبارات تبديل طلب الدليل toggle_evidence_request."""

    def test_toggle_to_requested(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, evidence_request_status="not_requested")
        client.force_login(admin)
        resp = client.post(reverse("toggle_evidence_request", kwargs={"proc_id": proc.pk}))
        assert resp.status_code in (200, 302)
        proc.refresh_from_db()
        assert proc.evidence_request_status == "requested"

    def test_toggle_to_not_requested(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain, evidence_request_status="requested")
        client.force_login(admin)
        resp = client.post(reverse("toggle_evidence_request", kwargs={"proc_id": proc.pk}))
        assert resp.status_code in (200, 302)
        proc.refresh_from_db()
        assert proc.evidence_request_status == "not_requested"

    def test_non_reviewer_forbidden(self, client, school):
        teacher = make_teacher(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(teacher)
        resp = client.post(reverse("toggle_evidence_request", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 403

    def test_requires_post(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        proc = make_procedure(school, domain)
        client.force_login(admin)
        resp = client.get(reverse("toggle_evidence_request", kwargs={"proc_id": proc.pk}))
        assert resp.status_code == 405


# ══════════════════════════════════════════════
#  6. TestDashboardNewKPIs
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDashboardNewKPIs:
    """اختبارات مؤشرات الأداء الجديدة في لوحة التحكم."""

    def test_context_has_new_kpis(self, client, school):
        admin = make_admin(school)
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200
        assert "pending_review" in resp.context
        assert "overdue_count" in resp.context
        assert "evidence_requested" in resp.context

    def test_overdue_count_accurate(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        yesterday = date.today() - timedelta(days=1)
        tomorrow = date.today() + timedelta(days=1)
        # Overdue: deadline passed + not completed
        make_procedure(school, domain, status="In Progress", deadline=yesterday)
        make_procedure(school, domain, status="In Progress", deadline=yesterday)
        # Not overdue: future deadline
        make_procedure(school, domain, status="In Progress", deadline=tomorrow)
        # Not overdue: completed even though deadline passed
        make_procedure(school, domain, status="Completed", deadline=yesterday)
        # Not overdue: no deadline
        make_procedure(school, domain, status="In Progress")
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200
        assert resp.context["overdue_count"] == 2

    def test_pending_review_count(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, status="Pending Review")
        make_procedure(school, domain, status="Pending Review")
        make_procedure(school, domain, status="In Progress")
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200
        assert resp.context["pending_review"] == 2

    def test_evidence_requested_count(self, client, school):
        admin = make_admin(school)
        domain = make_domain(school)
        make_procedure(school, domain, evidence_request_status="requested")
        make_procedure(school, domain, evidence_request_status="not_requested")
        make_procedure(school, domain, evidence_request_status="requested")
        client.force_login(admin)
        resp = client.get(reverse("quality_dashboard"))
        assert resp.status_code == 200
        assert resp.context["evidence_requested"] == 2
