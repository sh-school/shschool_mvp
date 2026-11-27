"""[U-11 المرحلة 2 (ب)] شاشةُ توقيع طلبات المحو: الصلاحياتُ والتوقيعُ والرفضُ والتعيينُ والإشعار."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import ErasureRequest
from notifications.models import InAppNotification

from .conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/governance/erasure/"


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
        school=school, student=student, requested_by=filer, reason="طلبٌ للاختبار"
    )


def _get(client, user):
    client.force_login(user)
    return client.get(LIST_URL)


def _post(client, user, name, *args, **data):
    client.force_login(user)
    return client.post(reverse(name, args=args), data)


def _messages(response):
    return " ".join(str(m) for m in get_messages(response.wsgi_request))


@pytest.fixture
def principal(school):
    return _user(school, "principal")


@pytest.fixture
def officer(school):
    return _appoint(school, _user(school, "it_technician"))


@pytest.fixture
def req(school, student_user):
    return _request(school, student_user, _user(school, "parent"))


@pytest.mark.parametrize("role", ["principal", "vice_admin"])
def test_the_signing_roles_open_the_screen(client, school, officer, req, role):
    response = _get(client, _user(school, role))

    assert response.status_code == 200
    assert "طلبٌ للاختبار" in response.content.decode()


@pytest.mark.parametrize("role", ["teacher", "vice_academic", "nurse", "platform_developer"])
def test_everyone_else_is_refused(client, school, officer, req, role):
    user = _user(school, role)

    assert _get(client, user).status_code == 403
    assert _post(client, user, "erasure_sign", req.pk, confirm="on").status_code == 403
    assert _post(client, user, "erasure_reject", req.pk, note="سبب").status_code == 403
    assert _post(client, user, "erasure_assign_officer", user_id=user.pk).status_code == 403


def test_a_developer_who_is_the_officer_signs_and_rejects_but_cannot_assign(
    client, school, student_user
):
    developer = _appoint(school, _user(school, "platform_developer"))
    erasure = _request(school, student_user, _user(school, "parent"))

    assert _get(client, developer).status_code == 200
    assert (
        _post(client, developer, "erasure_assign_officer", user_id=developer.pk).status_code == 403
    )
    assert _post(client, developer, "erasure_sign", erasure.pk, confirm="on").status_code == 302
    erasure.refresh_from_db()
    assert erasure.dpo_signed_by == developer
    assert _post(client, developer, "erasure_reject", erasure.pk, note="سبب").status_code == 302
    erasure.refresh_from_db()
    assert erasure.status == "rejected"


def test_a_request_of_another_school_is_not_found(client, principal, student_user):
    other = SchoolFactory()
    foreign = _request(other, student_user, _user(other, "parent"))

    assert _post(client, principal, "erasure_sign", foreign.pk, confirm="on").status_code == 404
    assert _post(client, principal, "erasure_reject", foreign.pk, note="سبب").status_code == 404
    assert str(foreign.pk) not in _get(client, principal).content.decode()


def test_signing_needs_confirmation_and_the_second_signature_erases(
    client, principal, officer, req, student_user
):
    _post(client, principal, "erasure_sign", req.pk)
    req.refresh_from_db()
    assert req.admin_signed_by is None

    _post(client, principal, "erasure_sign", req.pk, confirm="on")
    req.refresh_from_db()
    assert (req.status, req.admin_signed_by) == ("pending", principal)
    page = _get(client, officer).content.decode()
    assert "توقيعُك هو الثاني" in page
    assert reverse("erasure_sign", args=[req.pk]) in page

    _post(client, officer, "erasure_sign", req.pk, confirm="on")
    req.refresh_from_db()
    assert req.status == "completed"


def test_the_buttons_appear_only_for_who_may_still_act(client, school, principal, officer, req):
    sign_url = reverse("erasure_sign", args=[req.pk])
    reject_url = reverse("erasure_reject", args=[req.pk])
    _post(client, principal, "erasure_sign", req.pk, confirm="on")

    page = _get(client, principal).content.decode()
    assert sign_url not in page
    assert reject_url in page

    page = _get(client, _user(school, "vice_admin")).content.decode()
    assert sign_url not in page
    assert reject_url not in page


def test_the_service_refusal_is_shown(client, principal, req):
    response = _post(client, principal, "erasure_sign", req.pk, confirm="on")

    assert "لم يُعيَّن مسؤولُ حماية البيانات" in _messages(response)


def test_a_failed_erasure_is_shown_without_the_exception_text(
    client, principal, officer, req, monkeypatch
):
    def _boom(_request_obj):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr("governance.erasure_service.ErasureService.execute", _boom)
    _post(client, principal, "erasure_sign", req.pk, confirm="on")

    response = _post(client, officer, "erasure_sign", req.pk, confirm="on")

    assert "تعذّر تنفيذ المحو" in _messages(response)
    assert "secret-internal-detail" not in _messages(response)
    req.refresh_from_db()
    assert req.status == "approved"


def test_rejecting_requires_a_reason(client, principal, officer, req):
    response = _post(client, principal, "erasure_reject", req.pk, note="  ")
    req.refresh_from_db()
    assert req.status == "pending"
    assert "سبب الرفض مطلوب" in _messages(response)

    _post(client, principal, "erasure_reject", req.pk, note="لا يستوفي الشروط")
    req.refresh_from_db()
    assert (req.status, req.review_note) == ("rejected", "لا يستوفي الشروط")


def test_the_principal_assigns_the_officer_from_school_staff(client, school, principal):
    assert "لم يُعيَّن مسؤولُ حماية البيانات" in _get(client, principal).content.decode()
    staff = _user(school, "it_technician", "موظّفُ التقنية")
    outsider = _user(SchoolFactory(), "teacher")

    _post(client, principal, "erasure_assign_officer", user_id=outsider.pk)
    _post(client, principal, "erasure_assign_officer", user_id="ليس-معرّفاً")
    school.refresh_from_db()
    assert school.data_protection_officer is None

    _post(client, principal, "erasure_assign_officer", user_id=staff.pk)
    school.refresh_from_db()
    assert school.data_protection_officer == staff
    page = _get(client, principal).content.decode()
    assert "موظّفُ التقنية" in page
    assert "لم يُعيَّن مسؤولُ حماية البيانات" not in page


def test_only_the_principal_assigns(client, school, officer):
    vice = _user(school, "vice_admin")

    assert _post(client, vice, "erasure_assign_officer", user_id=vice.pk).status_code == 403
    assert reverse("erasure_assign_officer") not in _get(client, vice).content.decode()


def test_a_new_request_notifies_both_signers_without_the_student_name(
    school, principal, officer, student_user
):
    # المديرُ مقدِّمٌ فموقّعُ الإدارة النائبُ الإداريّ — ولا يُشعَر المقدِّم.
    vice = _user(school, "vice_admin")
    api = APIClient()
    api.force_login(principal)

    response = api.post(
        "/api/v1/erasure/request/",
        {"student_id": str(student_user.pk), "reason": "طلبٌ للاختبار من المدير"},
        format="json",
    )

    assert response.status_code == 201
    sent = InAppNotification.objects.filter(related_object_id=response.data["id"])
    assert {n.user for n in sent} == {vice, officer}
    for notification in sent:
        assert student_user.full_name not in notification.title + notification.body
        assert notification.related_url == LIST_URL


def test_the_first_signature_notifies_the_other_signer_only(client, principal, officer, req):
    _post(client, principal, "erasure_sign", req.pk, confirm="on")

    sent = InAppNotification.objects.filter(related_object_id=str(req.pk))
    assert [n.user for n in sent] == [officer]
    assert req.student.full_name not in sent[0].title + sent[0].body


def test_the_sidebar_link_follows_the_right(client, school, principal, officer):
    link = f'href="{LIST_URL}"'
    for user, shown in [
        (principal, True),
        (officer, True),
        (_user(school, "teacher"), False),
        (_user(school, "platform_developer"), False),
    ]:
        client.force_login(user)
        page = client.get(reverse("notification_inbox"), follow=True).content.decode()
        assert (link in page) is shown, user.full_name
