"""
tests/test_erasure.py — Right to Erasure (PDPPL م.18)
اختبارات API المحو + خدمة التنفيذ
"""

import pytest
from rest_framework.test import APIClient

from core.models import (
    AuditLog,
    ErasureRequest,
    ParentStudentLink,
    StudentEnrollment,
)

from .conftest import (
    BehaviorInfractionFactory,
    BookBorrowingFactory,
    ClassGroupFactory,
    ClinicVisitFactory,
    HealthRecordFactory,
    LibraryBookFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)


@pytest.fixture
def api_admin(db, school):
    """مدير مع API client (force_login لتجاوز SchoolPermissionMiddleware)"""
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المحو")
    MembershipFactory(user=user, school=school, role=role)
    client = APIClient()
    client.force_login(user)
    return client, user


@pytest.fixture
def api_parent(db, school, student_user):
    """ولي أمر مع API client — مع موافقة PDPPL"""
    from django.utils import timezone

    role = RoleFactory(school=school, name="parent")
    user = UserFactory(full_name="ولي أمر المحو")
    user.consent_given_at = timezone.now()
    user.save(update_fields=["consent_given_at"])
    MembershipFactory(user=user, school=school, role=role)
    ParentStudentLink.objects.create(
        parent=user,
        student=student_user,
        school=school,
    )
    client = APIClient()
    client.force_login(user)
    return client, user


@pytest.fixture
def student_with_data(db, school, student_user, teacher_user, nurse_user):
    """طالب مع بيانات في عدة نماذج"""
    cg = ClassGroupFactory(school=school)
    StudentEnrollmentFactory(student=student_user, class_group=cg)
    HealthRecordFactory(student=student_user)
    ClinicVisitFactory(school=school, student=student_user, nurse=nurse_user)
    BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
    book = LibraryBookFactory(school=school, available_qty=5, quantity=5)
    BookBorrowingFactory(book=book, user=student_user)
    return student_user


# ══════════════════════════════════════════════
#  API Tests
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestErasureAPI:
    def test_parent_can_request_erasure(self, api_parent, student_user, school):
        client, parent = api_parent
        resp = client.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_user.id),
                "reason": "أرغب في محو بيانات ابني من النظام بالكامل",
            },
        )
        assert resp.status_code == 201
        assert resp.data["status"] == "pending"

    def test_parent_cannot_request_for_others_child(self, api_parent, school):
        client, parent = api_parent
        other_student = UserFactory(full_name="طالب آخر")
        resp = client.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(other_student.id),
                "reason": "محاولة محو بيانات طالب غير تابع",
            },
        )
        assert resp.status_code == 403

    def test_admin_can_request_erasure(self, api_admin, student_user, school):
        client, admin = api_admin
        resp = client.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_user.id),
                "reason": "طلب إداري لمحو بيانات الطالب المنقول",
            },
        )
        assert resp.status_code == 201

    def test_duplicate_request_rejected(self, api_parent, student_user, school):
        client, parent = api_parent
        data = {"student_id": str(student_user.id), "reason": "طلب محو بيانات ابني"}
        client.post("/api/v1/erasure/request/", format="json", data=data)
        resp = client.post("/api/v1/erasure/request/", format="json", data=data)
        assert resp.status_code == 409

    def test_admin_list_requests(self, api_admin, student_user, school):
        client_a, admin = api_admin
        # Create request directly (avoid parent consent issues)
        ErasureRequest.objects.create(
            school=school,
            student=student_user,
            requested_by=admin,
            reason="طلب محو بيانات الطالب من النظام",
        )
        resp = client_a.get("/api/v1/erasure/requests/")
        assert resp.status_code == 200
        data = resp.data["results"] if "results" in resp.data else resp.data
        assert len(data) >= 1

    def test_admin_approve_executes_erasure(self, api_admin, student_with_data, school):
        client, admin = api_admin
        # Create request
        resp = client.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_with_data.id),
                "reason": "طلب إداري — الطالب انتقل لمدرسة أخرى",
            },
        )
        req_id = resp.data["id"]

        # Approve
        resp = client.post(
            f"/api/v1/erasure/requests/{req_id}/approve/",
            format="json",
            data={"note": "تمت الموافقة"},
        )
        assert resp.status_code == 200
        assert "ERASED-" in resp.data["anonymized_id"]

        # Verify student is anonymized
        student_with_data.refresh_from_db()
        assert "ERASED-" in student_with_data.full_name
        assert student_with_data.is_active is False

        # Verify child records deleted
        from behavior.models import BehaviorInfraction
        from clinic.models import ClinicVisit, HealthRecord

        assert not HealthRecord.objects.filter(student=student_with_data).exists()
        assert not ClinicVisit.objects.filter(student=student_with_data).exists()
        assert not BehaviorInfraction.objects.filter(student=student_with_data).exists()
        assert not StudentEnrollment.objects.filter(student=student_with_data).exists()

    def test_admin_reject_with_reason(self, api_admin, api_parent, student_user, school):
        client_p, _ = api_parent
        client_a, _ = api_admin
        resp = client_p.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_user.id),
                "reason": "طلب محو بيانات الطالب من النظام",
            },
        )
        req_id = resp.data["id"]
        resp = client_a.post(
            f"/api/v1/erasure/requests/{req_id}/reject/",
            format="json",
            data={
                "note": "الطالب لا يزال مسجلاً — لا يمكن المحو",
            },
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "rejected"

    def test_reject_requires_note(self, api_admin, api_parent, student_user, school):
        client_p, _ = api_parent
        client_a, _ = api_admin
        resp = client_p.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_user.id),
                "reason": "طلب محو بيانات الطالب من النظام",
            },
        )
        req_id = resp.data["id"]
        resp = client_a.post(f"/api/v1/erasure/requests/{req_id}/reject/", format="json", data={})
        assert resp.status_code == 400

    def test_cannot_approve_non_pending(self, api_admin, api_parent, student_user, school):
        client_p, _ = api_parent
        client_a, _ = api_admin
        resp = client_p.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_user.id),
                "reason": "طلب محو بيانات الطالب من النظام",
            },
        )
        req_id = resp.data["id"]
        # Reject first
        client_a.post(
            f"/api/v1/erasure/requests/{req_id}/reject/", format="json", data={"note": "مرفوض"}
        )
        # Try approve
        resp = client_a.post(f"/api/v1/erasure/requests/{req_id}/approve/", format="json", data={})
        assert resp.status_code == 400

    def test_unauthenticated_cannot_access(self, db):
        client = APIClient()
        resp = client.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": "00000000-0000-0000-0000-000000000000",
                "reason": "test",
            },
        )
        assert resp.status_code in (401, 403)

    def test_erasure_request_detail(self, api_parent, student_user, school):
        client, parent = api_parent
        resp = client.post(
            "/api/v1/erasure/request/",
            format="json",
            data={
                "student_id": str(student_user.id),
                "reason": "طلب محو تفصيلي لبيانات الطالب",
            },
        )
        req_id = resp.data["id"]
        resp = client.get(f"/api/v1/erasure/requests/{req_id}/")
        assert resp.status_code == 200
        assert resp.data["reason"] == "طلب محو تفصيلي لبيانات الطالب"


# ══════════════════════════════════════════════
#  Service Unit Tests
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestErasureService:
    def test_execute_anonymizes_student(self, student_with_data, school):
        from core.erasure_service import ErasureService

        admin = UserFactory(full_name="مدير التنفيذ", is_superuser=True)
        req = ErasureRequest.objects.create(
            school=school,
            student=student_with_data,
            requested_by=admin,
            reason="test erasure",
            status="approved",
            reviewed_by=admin,
        )
        summary = ErasureService.execute(req)
        assert "ERASED-" in summary["anon_id"]
        assert len(summary["models"]) > 0

        student_with_data.refresh_from_db()
        assert student_with_data.is_active is False
        assert "ERASED-" in student_with_data.full_name
        assert student_with_data.email == ""

    def test_execute_preserves_auditlog(self, student_with_data, school):
        from core.erasure_service import ErasureService

        # Create an audit log for the student
        before_count = AuditLog.objects.count()
        AuditLog.log(
            user=student_with_data,
            action="login",
            model_name="CustomUser",
            object_id=str(student_with_data.pk),
            school=school,
        )
        assert AuditLog.objects.count() == before_count + 1

        admin = UserFactory(full_name="مدير", is_superuser=True)
        req = ErasureRequest.objects.create(
            school=school,
            student=student_with_data,
            requested_by=admin,
            reason="test",
            status="approved",
            reviewed_by=admin,
        )
        ErasureService.execute(req)

        # AuditLog count should increase (erasure log added), not decrease
        assert AuditLog.objects.count() >= before_count + 1
