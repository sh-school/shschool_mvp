"""[W-20261002-040] عروضُ المحو محصورةٌ بمدرسة المدير.

المحوُ لا رجعةَ فيه: مديرُ مدرسةٍ أخرى لا يُنشئ طلبَ محوٍ لطالبٍ ليس من مدرسته
ولا يرى طلبَ غيره ولا يعتمده ولا يرفضه. الردُّ 404 لا 403 فلا يُعرَف وجودُ الطلب.
"""

import pytest
from rest_framework.test import APIClient

from core.models import ErasureRequest

from .conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory


def _admin_client(school, name):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    client = APIClient()
    client.force_login(user)
    return client, user


@pytest.fixture
def other_admin(db):
    return _admin_client(SchoolFactory(), "مدير مدرسة أخرى")[0]


@pytest.fixture
def own_admin(db, school):
    return _admin_client(school, "مدير المدرسة")[0]


@pytest.fixture
def pending_request(db, school, student_user):
    admin = UserFactory(full_name="مقدِّم")
    return ErasureRequest.objects.create(
        school=school, student=student_user, requested_by=admin, reason="سببٌ كافٍ للمحو"
    )


@pytest.mark.django_db
class TestCrossSchoolAdminDenied:
    def test_cannot_create_for_student_of_another_school(self, other_admin, student_user):
        r = other_admin.post(
            "/api/v1/erasure/request/",
            {"student_id": str(student_user.id), "reason": "محاولةٌ عابرةٌ للمدارس"},
            format="json",
        )

        assert r.status_code == 404
        assert not ErasureRequest.objects.filter(student=student_user).exists()

    def test_cannot_see_detail(self, other_admin, pending_request):
        assert other_admin.get(f"/api/v1/erasure/requests/{pending_request.id}/").status_code == 404

    def test_cannot_approve_and_nothing_is_erased(self, other_admin, pending_request):
        r = other_admin.post(f"/api/v1/erasure/requests/{pending_request.id}/approve/", {})

        assert r.status_code == 404
        pending_request.refresh_from_db()
        assert pending_request.status == "pending"
        pending_request.student.refresh_from_db()
        assert pending_request.student.is_active is True

    def test_cannot_reject(self, other_admin, pending_request):
        r = other_admin.post(
            f"/api/v1/erasure/requests/{pending_request.id}/reject/", {"note": "رفضٌ عابر"}
        )

        assert r.status_code == 404
        pending_request.refresh_from_db()
        assert pending_request.status == "pending"


@pytest.mark.django_db
class TestOwnSchoolStillWorks:
    def test_create_detail_reject(self, own_admin, student_user, school):
        r = own_admin.post(
            "/api/v1/erasure/request/",
            {"student_id": str(student_user.id), "reason": "طلبٌ من مدرسة الطالب"},
            format="json",
        )
        assert r.status_code == 201
        rid = r.data["id"]

        assert own_admin.get(f"/api/v1/erasure/requests/{rid}/").status_code == 200
        r = own_admin.post(f"/api/v1/erasure/requests/{rid}/reject/", {"note": "سببٌ للرفض"})
        assert r.status_code == 200

    def test_approve_in_own_school(self, own_admin, pending_request):
        r = own_admin.post(f"/api/v1/erasure/requests/{pending_request.id}/approve/", {})

        assert r.status_code == 200
