"""سرُّ TOTP الذي لا يُقرأ بمفتاح هذه البيئة لا يحبس صاحبَه ولا يُسقط الصفحة.

وقع على الإنتاج 2026-09-14: سرّان مشفَّران بمفتاح Fernet آخر (تدويرٌ أو قاعدةٌ من
بيئةٍ أخرى). `decrypt_field` تُعيد النصَّ المشفَّر كما هو عند الفشل، فكان الإعدادُ
يرسم QR من النصّ المشفَّر (لا يطابقه رمزٌ أبداً) والتحقّقُ يسقط 500 على
«Non-base32 digit found» — والمفعِّلُ محبوسٌ بلا مخرج.
"""

import io

import pyotp
import pytest
from django.core.management import call_command
from django.urls import reverse

from core.models import AuditLog, decrypt_field
from core.views_auth import usable_totp_secret
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

PASSWORD = "Probe-Passw0rd-2FA!"
#: رمزُ Fernet شكلاً لا يُفكّ بأيّ مفتاح — كما يبدو السرُّ المشفَّرُ بمفتاحٍ آخر.
FOREIGN_TOKEN = "gAAAAABo" + "x" * 132


def _staff(school, *, secret=FOREIGN_TOKEN, enabled=False):
    user = UserFactory(password=PASSWORD)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    user.totp_secret = secret
    user.totp_enabled = enabled
    user.save(update_fields=["totp_secret", "totp_enabled"])
    return user


def test_the_helper_rejects_a_foreign_token_and_accepts_a_real_secret(db, school):
    assert usable_totp_secret(_staff(school)) is None
    from core.models import encrypt_field

    real = pyotp.random_base32()
    user = _staff(school, secret=encrypt_field(real) or real)
    assert usable_totp_secret(user) == real


@pytest.mark.django_db
class TestSetupRegeneratesWhatItCannotRead:
    def test_setup_draws_a_fresh_secret_and_the_code_from_it_enables(self, client, school):
        user = _staff(school)
        client.force_login(user)

        assert client.get(reverse("setup_2fa")).status_code == 200
        user.refresh_from_db()
        assert user.totp_secret != FOREIGN_TOKEN, "السرُّ غيرُ المقروء يُستبدل"
        raw = decrypt_field(user.totp_secret) or user.totp_secret
        resp = client.post(reverse("setup_2fa"), {"code": pyotp.TOTP(raw).now()})
        user.refresh_from_db()
        assert resp.status_code == 302 and user.totp_enabled

    def test_an_enabled_user_with_a_foreign_secret_is_re_enrolled_not_trapped(self, client, school):
        user = _staff(school, enabled=True)
        client.force_login(user)

        client.get(reverse("setup_2fa"))
        user.refresh_from_db()
        assert not user.totp_enabled and usable_totp_secret(user)

    def test_a_code_with_spaces_is_accepted_at_setup(self, client, school):
        user = _staff(school, secret="")
        client.force_login(user)
        client.get(reverse("setup_2fa"))
        user.refresh_from_db()
        raw = decrypt_field(user.totp_secret) or user.totp_secret
        code = pyotp.TOTP(raw).now()

        client.post(reverse("setup_2fa"), {"code": f"{code[:3]} {code[3:]}"})

        user.refresh_from_db()
        assert user.totp_enabled


@pytest.mark.django_db
def test_verification_explains_instead_of_crashing(client, school):
    user = _staff(school, enabled=True)
    resp = client.post(reverse("login"), {"identifier": user.national_id, "password": PASSWORD})
    assert resp["Location"].endswith(reverse("verify_2fa"))

    resp = client.post(reverse("verify_2fa"), {"code": "123456"})

    assert resp.status_code == 200
    assert "reset_2fa" in resp.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_the_reset_command_clears_and_audits(school):
    user = _staff(school, enabled=True)
    out = io.StringIO()

    call_command("reset_2fa", "--unreadable", stdout=out)

    user.refresh_from_db()
    assert user.totp_secret == "" and not user.totp_enabled
    assert AuditLog.objects.filter(model_name="CustomUser", object_id=str(user.pk)).exists()
    assert "1 حساباً" in out.getvalue()
