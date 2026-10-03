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


# ══════════════════════════════════════════════════════════════════
# حكمُ 0105 الثاني (N1/N2/N3): الملفّاتُ لا تُمحى قبل فشل، وأيُّ استثناءٍ لا يترك processing، وإعادةٌ بتدقيق المراجع
# ══════════════════════════════════════════════════════════════════


def _stored_attachment(school, kid):
    """نشاطٌ طلابيٌّ بمرفقٍ في التخزين (StoredFile) — ملفٌّ يُمحى مع الطالب."""
    import datetime

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from student_affairs.models import StudentActivity

    name = default_storage.save("student_activities/2026/10/w020.pdf", ContentFile(b"PII"))
    StudentActivity.objects.create(
        school=school,
        student=kid,
        activity_type="certificate",
        title="شهادة",
        date=datetime.date(2026, 10, 1),
        attachment=name,
    )
    return name


def test_the_uploaded_files_survive_when_the_ledger_step_fails(
    school, admin_client, monkeypatch, kid, django_capture_on_commit_callbacks
):
    """N1: «لم يُمسّ شيء» صادقةٌ — الملفُّ لا يُحذف قبل أن يفشل المحو (على S3 لا يتراجع)."""
    from core.models import StoredFile

    client, _admin = admin_client
    name = _stored_attachment(school, kid)
    request_id = _file_request(client, kid)
    _break_the_ledger_eraser(monkeypatch)

    with django_capture_on_commit_callbacks(execute=True):
        response = _approve(client, request_id)

    assert response.status_code == 409
    assert StoredFile.objects.filter(name=name).exists()


def test_the_uploaded_files_are_purged_only_after_a_successful_commit(
    school, admin_client, kid, django_capture_on_commit_callbacks
):
    from core.models import StoredFile

    client, _admin = admin_client
    name = _stored_attachment(school, kid)
    request_id = _file_request(client, kid)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = _approve(client, request_id)
        assert response.status_code == 200, response.data
        # قبل التثبيت: الملفُّ باقٍ.
        assert StoredFile.objects.filter(name=name).exists()
    for callback in callbacks:
        callback()
    assert not StoredFile.objects.filter(name=name).exists()


def test_any_unexpected_exception_also_leaves_the_request_retryable(
    admin_client, monkeypatch, kid, caplog
):
    """N2: ليس EntryError وحدَه — أيُّ استثناءٍ يعيد الطلبَ approved ويُكتب رمزٌ عامّ ويُسجَّل للمراقبة."""
    client, admin = admin_client
    request_id = _file_request(client, kid)

    def boom(student, *, actor=None, school=None):
        raise RuntimeError("انقطع التخزين")

    monkeypatch.setattr("operations.attendance_entries.erase_attendance_ledger", boom)

    response = _approve(client, request_id)

    assert response.status_code == 409
    assert response.data["code"] == "erasure_error"
    assert ErasureRequest.objects.get(pk=request_id).status == "approved"
    line = AuditLog.objects.filter(user=admin, object_repr__contains="تعثّر محوٍ").get()
    assert line.changes["code"] == "erasure_error"
    assert any("فشل محوٌ غيرُ متوقَّع" in record.getMessage() for record in caplog.records)


def test_a_retry_records_the_previous_reviewer_in_the_audit(school, monkeypatch, kid):
    """N3: reviewed_by يتبدّل بالإعادة — فيُدوَّن المراجعُ الأصليُّ."""
    first = _staff(school, "principal", "المدير الأوّل", "29000006010")
    second = _staff(school, "principal", "المدير الثاني", "29000006011")
    first_client, second_client = APIClient(), APIClient()
    first_client.force_login(first)
    second_client.force_login(second)
    request_id = _file_request(first_client, kid)
    with monkeypatch.context() as patch:
        _break_the_ledger_eraser(patch)
        assert _approve(first_client, request_id).status_code == 409

    assert _approve(second_client, request_id).status_code == 200

    line = AuditLog.objects.filter(object_repr__contains="إعادةُ تنفيذٍ").get()
    assert line.user_id == second.id
    assert line.changes["previous_reviewer"] == str(first.id)


def test_a_request_already_processing_is_refused(school, admin_client, kid):
    """N3: الثاني المتزامن يجد الحالةَ processing فيُردّ (قفلُ الصفّ يسلسل الاثنين)."""
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    ErasureRequest.objects.filter(pk=request_id).update(status="processing")
    assert _approve(client, request_id).status_code == 400


def test_a_file_that_fails_to_delete_is_logged_by_key_not_content(
    school, admin_client, kid, monkeypatch, django_capture_on_commit_callbacks
):
    """P3 (0105 أ): بعد التثبيت لا إعادةَ محاولةٍ ممكنة — فيُسجَّل مفتاحُ الملفّ اليتيم (لا محتواه) ليُزال، والعدّادُ «مجدوَل»."""
    from django.db.models.fields.files import FieldFile

    client, _admin = admin_client
    name = _stored_attachment(school, kid)
    request_id = _file_request(client, kid)

    def broken(self, save=True):
        raise OSError("التخزين متوقّف")

    monkeypatch.setattr(FieldFile, "delete", broken)
    with django_capture_on_commit_callbacks(execute=True):
        response = _approve(client, request_id)

    assert response.status_code == 200
    assert response.data["summary"]["files_scheduled_for_purge"] == 1
    line = AuditLog.objects.filter(object_repr__contains="ملفٌّ يتيمٌ بعد محو").get()
    assert line.changes["key"] == name
    assert "PII" not in str(line.changes)


def test_a_student_outside_the_requests_school_keeps_the_request_retryable_with_a_409(
    school, admin_client, kid
):
    """W-040 فوق N1–N3: `execute` يرفع ValueError لطالبٍ ليس من مدرسة الطلب، و`execute_safely` يلتقطه فيعود الطلبُ «approved» بـ409
    ولا يبقى «processing» ولا يُمسّ الطالب."""
    client, _admin = admin_client
    request_id = _file_request(client, kid)
    kid.memberships.all().delete()

    response = _approve(client, request_id)

    assert response.status_code == 409
    assert ErasureRequest.objects.get(pk=request_id).status == "approved"
    kid.refresh_from_db()
    assert kid.is_active is True and "ERASED-" not in kid.full_name


def test_the_school_admin_gate_and_the_developer_exclusion_survive_the_merge(school, kid):
    """`IsSchoolAdmin` و`NotPlatformDeveloper` وحصرُ المدرسة على طرق الموافقة والرفض معاً."""
    from api.views_erasure import approve_erasure, reject_erasure

    for view in (approve_erasure, reject_erasure):
        classes = {p.__name__ for p in view.cls.permission_classes}
        assert {"IsSchoolAdmin", "NotPlatformDeveloper"} <= classes
