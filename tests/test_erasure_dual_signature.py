"""[U-11 المرحلة 2 (أ)] لا يُنفَّذ محوُ طالبٍ إلّا بتوقيعين من شخصين: الإدارةُ ومسؤولُ حماية البيانات (قرارُ المالك 2026-11-27)."""

import pytest
from django.contrib import admin
from django.forms.models import modelform_factory
from rest_framework.test import APIClient

from core.models import AuditLog, ErasureRequest, School

from .conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db


def _user(school, role, **extra):
    user = UserFactory(full_name=f"حسابُ {role}", **extra)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _client(user):
    client = APIClient()
    client.force_login(user)
    return client


def _appoint(school, user):
    school.data_protection_officer = user
    school.save(update_fields=["data_protection_officer"])
    return user


def _request(school, student, filer):
    return ErasureRequest.objects.create(
        school=school, student=student, requested_by=filer, reason="طلبٌ للاختبار"
    )


def _sign(user, req):
    return _client(user).post(f"/api/v1/erasure/requests/{req.pk}/approve/", format="json", data={})


def _reject(user, req, note="سببُ الرفض"):
    return _client(user).post(
        f"/api/v1/erasure/requests/{req.pk}/reject/", format="json", data={"note": note}
    )


def _untouched(student, req, status="pending"):
    student.refresh_from_db()
    req.refresh_from_db()
    return student.is_active and "ERASED-" not in student.full_name and req.status == status


@pytest.fixture
def principal(school):
    return _user(school, "principal")


@pytest.fixture
def officer(school):
    return _appoint(school, _user(school, "it_technician"))


@pytest.fixture
def req(school, student_user):
    """طلبٌ قدّمه وليُّ أمر."""
    return _request(school, student_user, _user(school, "parent"))


@pytest.mark.parametrize("first", ["principal", "officer"])
def test_the_erasure_runs_only_on_the_second_signature_in_any_order(
    request, principal, officer, req, student_user, first
):
    order = [principal, officer] if first == "principal" else [officer, principal]

    assert _sign(order[0], req).status_code == 202
    assert _untouched(student_user, req)

    assert _sign(order[1], req).status_code == 200
    req.refresh_from_db()
    assert req.status == "completed"
    assert (req.admin_signed_by, req.dpo_signed_by) == (principal, officer)
    lines = AuditLog.objects.filter(object_repr="محوُ طالبٍ — توقيع", object_id=str(req.pk))
    assert lines.count() == 2
    for line in lines:
        assert set(line.changes) == {"request", "signer", "slot"}


def test_the_same_person_cannot_sign_twice(officer, principal, req, student_user):
    assert _sign(principal, req).status_code == 202
    assert _sign(principal, req).status_code == 409
    assert _untouched(student_user, req)


def test_a_principal_who_is_the_officer_cannot_fill_both_slots(school, principal, student_user):
    _appoint(school, principal)
    erasure = _request(school, student_user, _user(school, "parent"))

    assert _sign(principal, erasure).status_code == 202
    assert _sign(principal, erasure).status_code == 409
    assert _untouched(student_user, erasure)


def test_the_filer_can_neither_sign_nor_reject(school, officer, student_user):
    erasure = _request(school, student_user, officer)

    assert _sign(officer, erasure).status_code == 403
    assert _reject(officer, erasure).status_code == 403
    assert _untouched(student_user, erasure)


def test_a_principals_request_is_signed_by_the_admin_vice_principal(
    school, principal, officer, student_user
):
    erasure = _request(school, student_user, principal)
    other_principal = _user(school, "principal")
    academic = _user(school, "vice_academic")
    vice = _user(school, "vice_admin")

    assert _sign(principal, erasure).status_code == 403
    assert _sign(other_principal, erasure).status_code == 403
    assert _sign(academic, erasure).status_code == 403
    assert _sign(officer, erasure).status_code == 202
    assert _sign(vice, erasure).status_code == 200


def test_the_vice_principal_does_not_sign_a_request_the_principal_did_not_file(
    school, officer, req
):
    assert _sign(_user(school, "vice_admin"), req).status_code == 403


def test_without_an_officer_nothing_is_erased_and_the_message_says_why(
    principal, req, student_user
):
    response = _sign(principal, req)

    assert response.status_code == 409
    assert "لم يُعيَّن مسؤولُ حماية البيانات" in response.data["detail"]
    assert _untouched(student_user, req)


def test_a_legacy_approved_request_without_signatures_does_not_run(
    school, principal, officer, req, student_user
):
    ErasureRequest.objects.filter(pk=req.pk).update(status="approved", reviewed_by=principal)

    assert _sign(principal, req).status_code == 202
    assert _untouched(student_user, req, status="approved")


def test_a_replaced_officers_signature_no_longer_counts(
    school, principal, officer, req, student_user
):
    assert _sign(officer, req).status_code == 202
    successor = _appoint(school, _user(school, "it_technician"))

    assert _sign(principal, req).status_code == 202
    assert _untouched(student_user, req)
    assert _sign(successor, req).status_code == 200


def test_after_a_failure_both_signatures_are_required_again(
    principal, officer, req, student_user, monkeypatch
):
    def boom(student, *, actor=None, school=None):
        raise RuntimeError("انقطع التخزين")

    assert _sign(principal, req).status_code == 202
    with monkeypatch.context() as patch:
        patch.setattr("operations.attendance_entries.erase_attendance_ledger", boom)
        assert _sign(officer, req).status_code == 409
    req.refresh_from_db()
    assert (req.status, req.admin_signed_by, req.dpo_signed_by) == ("approved", None, None)

    assert _sign(officer, req).status_code == 202
    assert _untouched(student_user, req, status="approved")
    assert _sign(principal, req).status_code == 200


@pytest.mark.parametrize("who", ["principal", "officer"])
def test_one_signers_rejection_with_a_reason_is_enough(
    request, principal, officer, req, student_user, who
):
    signer = request.getfixturevalue(who)

    assert _reject(signer, req, note="").status_code == 400
    assert _reject(signer, req).status_code == 200
    assert _untouched(student_user, req, status="rejected")


# ── المطوّر ──────────────────────────────────────────────────


@pytest.mark.parametrize("is_superuser", [False, True])
def test_an_appointed_developer_signs_but_never_executes_alone(
    school, principal, req, student_user, is_superuser
):
    developer = _appoint(school, _user(school, "platform_developer", is_superuser=is_superuser))

    assert _sign(developer, req).status_code == 202
    assert _sign(developer, req).status_code == 409
    assert _untouched(student_user, req)
    assert _sign(principal, req).status_code == 200


def test_an_appointed_developer_may_reject_but_not_file(school, req, student_user):
    developer = _appoint(school, _user(school, "platform_developer"))

    filed = _client(developer).post(
        "/api/v1/erasure/request/",
        format="json",
        data={"student_id": str(student_user.pk), "reason": "طلبٌ من المطوّر المعيَّن"},
    )

    assert filed.status_code == 403
    assert _reject(developer, req).status_code == 200


@pytest.mark.parametrize("is_superuser", [False, True])
def test_a_developer_who_is_not_the_officer_stays_blocked(
    school, officer, req, student_user, is_superuser
):
    developer = _user(school, "platform_developer", is_superuser=is_superuser)

    assert _sign(developer, req).status_code == 403
    assert _reject(developer, req).status_code == 403
    assert _untouched(student_user, req)


# ── التعيين ──────────────────────────────────────────────────


def _assign(actor, candidate):
    return _client(actor).post(
        "/api/v1/erasure/officer/", format="json", data={"user_id": str(candidate.pk)}
    )


def test_the_principal_appoints_the_officer_and_it_is_audited_by_ids(school, principal):
    candidate = _user(school, "it_technician")

    assert _assign(principal, candidate).status_code == 200

    school.refresh_from_db()
    assert school.data_protection_officer == candidate
    line = AuditLog.objects.get(object_repr="تعيينُ مسؤول حماية البيانات")
    assert line.changes == {"officer": str(candidate.pk), "previous_officer": None}


@pytest.mark.parametrize("role", ["vice_admin", "vice_academic", "teacher", "platform_developer"])
def test_nobody_but_the_principal_appoints(school, role):
    actor = _user(school, role)

    assert _assign(actor, _user(school, "it_technician")).status_code == 403
    school.refresh_from_db()
    assert school.data_protection_officer is None


def test_a_superuser_without_the_principal_role_does_not_appoint(school):
    actor = _user(school, "teacher", is_superuser=True)

    assert _assign(actor, _user(school, "it_technician")).status_code == 403


@pytest.mark.parametrize("role", ["student", "parent"])
def test_only_the_schools_staff_can_be_appointed(school, principal, role):
    assert _assign(principal, _user(school, role)).status_code == 400
    assert _assign(principal, _user(SchoolFactory(), "it_technician")).status_code == 400
    school.refresh_from_db()
    assert school.data_protection_officer is None


def test_the_officer_field_is_not_editable_from_the_admin_or_forms(rf, school):
    assert "data_protection_officer" not in modelform_factory(School, fields="__all__").base_fields
    request = rf.get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)
    form = admin.site._registry[School].get_form(request, school)
    assert "data_protection_officer" not in form.base_fields
