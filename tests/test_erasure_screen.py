"""[U-11 المرحلة 2 (ب)] شاشةُ توقيع طلبات المحو: الحراسةُ والتوقيعُ والرفضُ والتعيينُ والإشعار."""

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import ErasureRequest
from notifications.models import InAppNotification

from .conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

LIST = "governance:erasure_requests"


def _user(school, role, name=None):
    user = UserFactory(full_name=name or f"حسابُ {role}")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _appoint(school, user):
    school.data_protection_officer = user
    school.save(update_fields=["data_protection_officer"])
    return user


def _request(school, student, filer):
    return ErasureRequest.objects.create(
        school=school, student=student, requested_by=filer, reason="سببٌ للاختبار"
    )


@pytest.fixture
def principal(school):
    return _user(school, "principal")


@pytest.fixture
def officer(school):
    return _appoint(school, _user(school, "it_technician"))


@pytest.fixture
def req(school, student_user):
    return _request(school, student_user, _user(school, "parent"))


def _sign(client_as, user, req, confirm="1"):
    url = reverse("governance:erasure_sign", args=[req.pk])
    return client_as(user).post(url, {"confirm": confirm}, follow=True)


def _reject(client_as, user, req, note):
    url = reverse("governance:erasure_reject", args=[req.pk])
    return client_as(user).post(url, {"note": note}, follow=True)


def _messages(response):
    return " ".join(str(m) for m in response.context["messages"])


@pytest.mark.parametrize("role", ["principal", "vice_admin"])
def test_the_administrative_signers_see_the_list_and_the_sidebar_link(client_as, school, req, role):
    response = client_as(_user(school, role)).get(reverse(LIST))

    assert response.status_code == 200
    body = response.content.decode()
    assert "سببٌ للاختبار" in body
    assert "لم يُعيَّن مسؤولُ حماية البيانات" in body
    assert f'href="{reverse(LIST)}"' in body


def test_the_appointed_officer_enters_whatever_the_role(client_as, officer, req):
    response = client_as(officer).get(reverse(LIST))

    assert response.status_code == 200
    assert f'href="{reverse(LIST)}"' in response.content.decode()


@pytest.mark.parametrize("role", ["teacher", "vice_academic", "platform_developer", "parent"])
def test_everyone_else_gets_403_on_every_route(client_as, school, officer, req, role):
    user = _user(school, role)
    # وليُّ أمرٍ بلا موافقة تحوّله بوّابةُ الموافقة قبل الحارس؛ نمنحها ليُقاس الحارسُ نفسُه.
    user.consent_given_at = timezone.now()
    user.save(update_fields=["consent_given_at"])
    client = client_as(user)

    assert client.get(reverse(LIST)).status_code == 403
    for name in ("erasure_sign", "erasure_reject"):
        url = reverse(f"governance:{name}", args=[req.pk])
        assert client.post(url, {"confirm": "1", "note": "س"}).status_code == 403
    assert client.post(reverse("governance:erasure_officer"), {}).status_code == 403
    req.refresh_from_db()
    assert req.status == "pending"


def test_a_developer_officer_signs_but_does_not_appoint(client_as, school, req):
    developer = _appoint(school, _user(school, "platform_developer"))

    assert client_as(developer).get(reverse(LIST)).status_code == 200
    appoint = client_as(developer).post(
        reverse("governance:erasure_officer"), {"user_id": str(developer.pk)}
    )
    assert appoint.status_code == 403

    _sign(client_as, developer, req)
    req.refresh_from_db()
    assert req.dpo_signed_by == developer


def test_another_schools_request_is_404_and_not_listed(client_as, principal, officer):
    other = SchoolFactory()
    foreign = _request(other, _user(other, "student", "طالبٌ بعيد"), _user(other, "parent"))

    assert "طالبٌ بعيد" not in client_as(principal).get(reverse(LIST)).content.decode()
    for name in ("erasure_sign", "erasure_reject"):
        url = reverse(f"governance:{name}", args=[foreign.pk])
        response = client_as(principal).post(url, {"confirm": "1", "note": "س"})
        assert response.status_code == 404


def test_signing_needs_the_explicit_confirmation(client_as, principal, officer, req):
    response = _sign(client_as, principal, req, confirm="")

    assert "لم يُسجَّل توقيعك" in _messages(response)
    req.refresh_from_db()
    assert req.admin_signed_by is None


def test_two_signatures_execute_the_erasure_from_the_screen(
    client_as, principal, officer, req, student_user
):
    first = _sign(client_as, principal, req)
    assert "سُجّل توقيعك" in _messages(first)
    (row,) = first.context["rows"]
    assert row["missing"] == ["مسؤول حماية البيانات"]
    assert (row["can_sign"], row["can_reject"]) == (False, True)

    second = _sign(client_as, officer, req)
    assert "تم تنفيذ المحو" in _messages(second)
    req.refresh_from_db()
    student_user.refresh_from_db()
    assert req.status == "completed"
    assert not student_user.is_active


def test_the_service_refusal_is_shown(client_as, principal, req):
    response = _sign(client_as, principal, req)

    assert "لم يُعيَّن مسؤولُ حماية البيانات للمدرسة — يعيّنه المديرُ" in _messages(response)


def test_a_failed_erasure_is_shown_and_nothing_is_touched(
    client_as, principal, officer, req, student_user, monkeypatch
):
    from governance.erasure_service import ErasureService

    def _boom(erasure_request):
        raise RuntimeError("تفصيلٌ داخليّ")

    monkeypatch.setattr(ErasureService, "execute", _boom)
    _sign(client_as, principal, req)
    response = _sign(client_as, officer, req)

    shown = _messages(response)
    assert "تعذّر تنفيذ المحو" in shown and "لم يُمسّ شيء" in shown
    assert "تفصيلٌ داخليّ" not in response.content.decode()
    req.refresh_from_db()
    assert req.status == "approved"


def test_the_filer_gets_no_buttons(client_as, school, officer, principal, student_user):
    _request(school, student_user, principal)

    (row,) = client_as(principal).get(reverse(LIST)).context["rows"]

    assert (row["can_sign"], row["can_reject"]) == (False, False)


def test_rejection_needs_a_reason(client_as, principal, officer, req):
    assert "سبب الرفض مطلوب" in _messages(_reject(client_as, principal, req, "   "))
    req.refresh_from_db()
    assert req.status == "pending"

    _reject(client_as, principal, req, "لا يستوفي الشروط")
    req.refresh_from_db()
    assert (req.status, req.review_note) == ("rejected", "لا يستوفي الشروط")


def test_the_principal_appoints_from_school_staff_only(client_as, school, principal, student_user):
    staff = _user(school, "teacher", "معلّمٌ مرشَّح")
    url = reverse("governance:erasure_officer")
    page = client_as(principal).get(reverse(LIST))
    offered = {pk for pk, _ in page.context["candidates"]}
    assert str(staff.pk) in offered and str(student_user.pk) not in offered

    refused = client_as(principal).post(url, {"user_id": str(student_user.pk)}, follow=True)
    assert "من كادر المدرسة" in _messages(refused)

    done = client_as(principal).post(url, {"user_id": str(staff.pk)}, follow=True)
    school.refresh_from_db()
    assert school.data_protection_officer == staff
    assert done.context["officer"] == staff


def test_the_vice_admin_cannot_appoint(client_as, school):
    vice = _user(school, "vice_admin")

    response = client_as(vice).post(
        reverse("governance:erasure_officer"), {"user_id": str(vice.pk)}
    )

    assert response.status_code == 403
    school.refresh_from_db()
    assert school.data_protection_officer is None


def _notified(req):
    return set(
        InAppNotification.objects.filter(related_object_id=str(req.pk)).values_list(
            "user_id", flat=True
        )
    )


def test_a_new_request_notifies_both_signers_without_the_student_name(
    client_as, principal, officer, student_user, parent_user
):
    response = client_as(parent_user).post(
        "/api/v1/erasure/request/",
        {"student_id": str(student_user.pk), "reason": "سببٌ طويلٌ بما يكفي"},
        content_type="application/json",
    )

    assert response.status_code == 201
    req = ErasureRequest.objects.get()
    assert _notified(req) == {principal.pk, officer.pk}
    for note in InAppNotification.objects.filter(related_object_id=str(req.pk)):
        assert student_user.full_name not in f"{note.title} {note.body}"
        assert note.related_url == reverse(LIST)


@pytest.mark.parametrize("first", ["principal", "officer"])
def test_the_first_signature_notifies_the_other_signer_only(
    client_as, principal, officer, req, student_user, first
):
    signer, other = (principal, officer) if first == "principal" else (officer, principal)

    _sign(client_as, signer, req)

    assert _notified(req) == {other.pk}
    note = InAppNotification.objects.get(related_object_id=str(req.pk))
    assert student_user.full_name not in f"{note.title} {note.body}"
