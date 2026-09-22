"""[SECURITY] P1-4 — المفعِّلُ لا تُقبل جلستُه إلّا وفيها دليلُ الرمز.

كان الإلزامُ يسأل «هل فعّل الثنائيّة؟». فجلسةٌ فُتحت بكلمة المرور وحدَها — من
``/admin/login/`` مثلاً — كانت تبلغ كلَّ شيء. الآن: رمزٌ في هذه الجلسة، أو لا جلسة.
"""

import pyotp
import pytest
from django.urls import reverse

from core.mfa_session import MFA_SESSION_KEY
from core.models import encrypt_field
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

PASSWORD = "Probe-Passw0rd-MFA!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _two_factor_on(settings):
    settings.TWO_FACTOR_REQUIRED_FOR_STAFF = True


def _principal(school, *, superuser=False):
    user = UserFactory(password=PASSWORD)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    secret = pyotp.random_base32()
    user.totp_secret = encrypt_field(secret) or secret
    user.totp_enabled = True
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["totp_secret", "totp_enabled", "is_staff", "is_superuser"])
    return user, secret


@pytest.mark.django_db
class TestSessionMustCarryTheCode:
    def test_a_session_opened_without_the_code_is_closed(self, client, school):
        user, _ = _principal(school)
        client.force_login(user)  # كما يفعل أيُّ بابٍ يفتح الجلسةَ بكلمة المرور وحدَها

        resp = client.get(reverse("dashboard"))

        assert resp.status_code == 302
        assert resp["Location"].startswith(reverse("login"))
        assert "_auth_user_id" not in client.session

    def test_api_and_htmx_get_a_machine_answer(self, client, school):
        user, _ = _principal(school)
        client.force_login(user)
        assert client.get("/api/v1/me/").status_code == 401

        client.force_login(user)
        resp = client.get(reverse("dashboard"), HTTP_HX_REQUEST="true")
        assert resp.status_code == 204 and resp["HX-Redirect"].startswith(reverse("login"))

    def test_the_code_at_login_marks_the_session(self, client, school):
        user, secret = _principal(school)
        client.post(reverse("login"), {"identifier": user.national_id, "password": PASSWORD})
        client.post(reverse("verify_2fa"), {"code": pyotp.TOTP(secret).now()})

        assert client.session.get(MFA_SESSION_KEY) is True
        assert client.get(reverse("dashboard")).status_code == 200

    def test_enabling_at_setup_marks_the_session(self, client, school):
        user, _ = _principal(school)
        user.totp_enabled = False
        user.totp_secret = ""
        user.save(update_fields=["totp_enabled", "totp_secret"])
        client.force_login(user)
        client.get(reverse("setup_2fa"))
        user.refresh_from_db()
        from core.models import decrypt_field

        secret = decrypt_field(user.totp_secret) or user.totp_secret
        client.post(reverse("setup_2fa"), {"code": pyotp.TOTP(secret).now()})

        assert client.session.get(MFA_SESSION_KEY) is True
        assert client.get(reverse("dashboard")).status_code == 200

    def test_the_freeze_flag_asks_for_nothing(self, client, school, settings):
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = False
        user, _ = _principal(school)
        client.force_login(user)

        assert client.get(reverse("dashboard")).status_code == 200


@pytest.mark.django_db
class TestAdminLoginGoesThroughTheOneDoor:
    def test_admin_login_redirects_to_the_platform_login(self, client):
        resp = client.get("/admin/login/?next=/admin/core/")

        assert resp.status_code == 302
        assert resp["Location"] == reverse("login") + "?next=%2Fadmin%2Fcore%2F"

    def test_admin_login_form_cannot_open_a_session(self, client, school):
        user, _ = _principal(school, superuser=True)

        client.post("/admin/login/", {"username": user.national_id, "password": PASSWORD})

        assert "_auth_user_id" not in client.session

    def test_an_unverified_superuser_cannot_reach_admin(self, client, school):
        user, _ = _principal(school, superuser=True)
        client.force_login(user)

        resp = client.get("/admin/")

        assert resp.status_code == 302
        assert "_auth_user_id" not in client.session
