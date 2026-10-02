"""[LEGAL] فشلُ محو سجلّ الرصد لا يترك طلبَ المحو عالقاً «processing» بلا مخرج (W-20261002-020، حكمُ 0105 M5).

`approve_erasure` كان يحفظ الحالةَ «processing» **قبل** `ErasureService.execute` ولا يلتقط استثناءً: فإذا رفعت
`erase_attendance_ledger` خطأً (`erasure_wrong_tenant`/`erasure_incomplete`) تراجعت معاملةُ التنفيذ (جيّد) لكنّ الطلبَ يبقى
«processing»، ويصير 500، وإعادةُ الموافقة تُردّ 400 لأنّ الحالةَ ليست `pending` — فيتوقّف حقُّ المحو (PDPPL م.18) بلا أثرٍ
ولا إعادة محاولة. الآن: الطلبُ يعود «approved» (قابلٌ للإعادة) مع 409 برسالةٍ مفهومةٍ بالعربيّة تذكر اسمَ المدرسة، وسطرُ
AuditLog بالفشل، وإعادةُ التنفيذ تنجح. وطالبٌ له عضويّاتٌ في مدرسةٍ أخرى لا يُقال له «اكتمل» بلا تنبيهٍ على الحدّ المعلَن.
"""

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog, ErasureRequest
from operations.attendance_entries import EntryError, submit_entry
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff, at
from tests.conftest import SchoolFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(school):
    admin = _staff(school, "principal", "مدير المحو", "29000006001")
    client = APIClient()
    client.force_login(admin)
    return client, admin


def _file_request(client, kid):
    response = client.post(
        "/api/v1/erasure/request/",
        format="json",
        data={"student_id": str(kid.id), "reason": "طلبُ محوٍ لاختبار الفشل"},
    )
    assert response.status_code == 201, response.data
    return response.data["id"]


def _approve(client, request_id):
    return client.post(f"/api/v1/erasure/requests/{request_id}/approve/", format="json", data={})


def _break_the_ledger_eraser(monkeypatch, code="erasure_wrong_tenant"):
    def boom(student, *, actor=None, school=None):
        raise EntryError(code, "تعذّر")

    monkeypatch.setattr("operations.attendance_entries.erase_attendance_ledger", boom)


def test_a_failed_ledger_erasure_returns_409_and_keeps_the_request_retryable(
    admin_client, monkeypatch, kid
):
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    _break_the_ledger_eraser(monkeypatch)

    response = _approve(client, request_id)

    assert response.status_code == 409
    assert "يمكن إعادة التنفيذ" in response.data["detail"]
    erasure = ErasureRequest.objects.get(pk=request_id)
    assert erasure.status == "approved"  # لا «processing» عالقةً
    kid.refresh_from_db()
    assert kid.is_active is True and "ERASED-" not in kid.full_name  # المعاملةُ تراجعت كلُّها


def test_the_failure_is_audited_with_its_code(admin_client, monkeypatch, kid):
    client, admin = admin_client
    request_id = _file_request(client, kid)
    _break_the_ledger_eraser(monkeypatch, code="erasure_incomplete")

    _approve(client, request_id)

    line = AuditLog.objects.filter(
        user=admin, model_name="other", object_repr__contains="تعثّر محوٍ"
    ).get()
    assert line.changes["code"] == "erasure_incomplete"
    assert line.changes["request"] == str(request_id)


def test_the_request_can_be_retried_after_the_cause_is_fixed(admin_client, monkeypatch, kid):
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    with monkeypatch.context() as patch:
        _break_the_ledger_eraser(patch)
        assert _approve(client, request_id).status_code == 409

    retry = _approve(client, request_id)

    assert retry.status_code == 200, retry.data
    assert ErasureRequest.objects.get(pk=request_id).status == "completed"
    kid.refresh_from_db()
    assert "ERASED-" in kid.full_name


def test_a_pending_request_still_works_as_before(admin_client, kid):
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    assert _approve(client, request_id).status_code == 200


def test_a_completed_request_cannot_be_approved_again(admin_client, kid):
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    _approve(client, request_id)
    assert _approve(client, request_id).status_code == 400


def test_the_wrong_tenant_message_names_the_school(school, session, teacher, holder, kid):
    """P3 (0105): رسالةٌ مفهومةٌ للمدير باسم المدرسة المطلوبة لا معرّفٍ."""
    from operations.attendance_entries import erase_attendance_ledger
    from tests.test_attendance_ledger_hardening import _as_tenant, _skip_unless_postgres

    _skip_unless_postgres()
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    other = SchoolFactory()
    with _as_tenant(other.pk), pytest.raises(EntryError) as caught:
        erase_attendance_ledger(kid, school=school)
    assert school.name in str(caught.value)


def test_a_student_with_another_school_membership_is_told_the_scope_is_limited(admin_client, kid):
    """الحدُّ المعلَن: صفوفُ مدرسةٍ سابقةٍ لا يراها دورُ الحاليّة — فلا يُقال «اكتمل» بلا تنبيه."""
    from tests.conftest import MembershipFactory, RoleFactory

    client, _admin = admin_client
    other = SchoolFactory()
    MembershipFactory(user=kid, school=other, role=RoleFactory(school=other, name="student"))
    request_id = _file_request(client, kid)

    response = _approve(client, request_id)

    assert response.status_code == 200, response.data
    assert "attendance_ledger_note" in response.data["summary"]
    assert "مدارس" in response.data["summary"]["attendance_ledger_note"]


def test_a_single_school_student_gets_no_scope_warning(admin_client, kid):
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    response = _approve(client, request_id)
    assert "attendance_ledger_note" not in response.data["summary"]
