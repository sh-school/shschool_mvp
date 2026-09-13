"""المصادقةُ الثنائيّة تُدخل صاحبَها — لا تُقفل الباب في وجهه.

كان `verify_2fa` يستدعي `login(request, user)` لمستخدمٍ حُمِّل من القاعدة من جديد،
بلا سمة `backend` التي يعلّقها `authenticate()`. وللمنصّة خلفيّتان (axes + HMAC)،
فكان Django يرفع `ValueError` وتسقط الصفحةُ 500 — أي أنّ كلَّ من فعّل المصادقةَ
الثنائيّة لم يعد يستطيع الدخولَ إطلاقاً، ولا اختبارَ كان يلمس هذا المسار.
"""

import pyotp
import pytest
from django.urls import reverse

from core.models import encrypt_field
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

PASSWORD = "Probe-Passw0rd-2FA!"


def _leader_with_totp(school, *, enabled=True):
    user = UserFactory(password=PASSWORD)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="principal"))
    secret = pyotp.random_base32()
    user.totp_secret = encrypt_field(secret) or secret
    user.totp_enabled = enabled
    user.save(update_fields=["totp_secret", "totp_enabled"])
    return user, secret


def _login(client, user):
    return client.post(reverse("login"), {"identifier": user.national_id, "password": PASSWORD})


@pytest.mark.django_db
class TestVerificationLogsTheLeaderIn:
    def test_login_then_the_right_code_opens_a_session(self, client, school):
        user, secret = _leader_with_totp(school)

        first = _login(client, user)
        assert first.status_code == 302 and first["Location"].endswith(reverse("verify_2fa"))
        assert "_auth_user_id" not in client.session, "كلمةُ المرور وحدَها لا تفتح الجلسة"

        second = client.post(reverse("verify_2fa"), {"code": pyotp.TOTP(secret).now()})

        assert second.status_code == 302 and not second["Location"].endswith(reverse("login"))
        assert client.session.get("_auth_user_id") == str(user.pk)
        assert "pending_2fa_user" not in client.session
        assert "pending_2fa_backend" not in client.session

    def test_a_session_from_before_the_fix_still_gets_in(self, client, school):
        """جلسةٌ عالقةٌ عند صفحة التحقّق لحظةَ النشر لا تحمل اسمَ الخلفيّة — فيُفترَض."""
        user, secret = _leader_with_totp(school)
        session = client.session
        session["pending_2fa_user"] = str(user.pk)
        session.save()

        resp = client.post(reverse("verify_2fa"), {"code": pyotp.TOTP(secret).now()})

        assert resp.status_code == 302
        assert client.session.get("_auth_user_id") == str(user.pk)

    def test_a_wrong_code_keeps_the_door_shut(self, client, school):
        user, _secret = _leader_with_totp(school)
        _login(client, user)

        resp = client.post(reverse("verify_2fa"), {"code": "000000"})

        assert resp.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_setup_enables_and_the_next_login_asks_for_the_code(self, client, school):
        """الدورةُ كاملةً كما يعيشها المدير: إعدادٌ من القائمة ثمّ دخولٌ جديد."""
        user, _ = _leader_with_totp(school, enabled=False)
        user.totp_secret = ""
        user.save(update_fields=["totp_secret"])
        client.force_login(user)

        assert client.get(reverse("setup_2fa")).status_code == 200
        user.refresh_from_db()
        from core.models import decrypt_field

        secret = decrypt_field(user.totp_secret) or user.totp_secret
        assert secret, "الإعدادُ يولّد السرَّ عند أوّل فتح"
        client.post(reverse("setup_2fa"), {"code": pyotp.TOTP(secret).now()})
        user.refresh_from_db()
        assert user.totp_enabled

        client.logout()
        assert _login(client, user)["Location"].endswith(reverse("verify_2fa"))
        client.post(reverse("verify_2fa"), {"code": pyotp.TOTP(secret).now()})
        assert client.session.get("_auth_user_id") == str(user.pk)


def _staff(school, role="teacher"):
    user = UserFactory(password=PASSWORD)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.mark.django_db
class TestEveryStaffMemberMustSetItUp:
    """قرارُ 2026-09-14: الثنائيّةُ لكلّ الكادر — وسيطٌ يُلزم لا رايةٌ عند الدخول.

    الإلزامُ مُطفأٌ في إعدادات الاختبار (كما axes) فيُشعَل هنا وحدَه.
    """

    @pytest.fixture(autouse=True)
    def _enforced(self, settings):
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = True

    def test_a_teacher_without_totp_reaches_only_the_setup_page(self, client, school):
        user = _staff(school)
        client.force_login(user)

        resp = client.get(reverse("dashboard"))

        assert resp.status_code == 302 and resp["Location"].endswith(reverse("setup_2fa"))
        assert client.get(reverse("setup_2fa")).status_code == 200
        assert client.post(reverse("logout")).status_code == 302, "الخروجُ يبقى مفتوحاً"

    def test_an_htmx_request_asks_the_browser_to_redirect(self, client, school):
        client.force_login(_staff(school, "nurse"))

        resp = client.get(reverse("dashboard"), HTTP_HX_REQUEST="true")

        assert resp.status_code == 204 and resp["HX-Redirect"].endswith(reverse("setup_2fa"))

    def test_a_teacher_with_totp_passes(self, client, school):
        user, _ = _leader_with_totp(school)
        client.force_login(user)

        assert client.get(reverse("dashboard")).status_code == 200

    @pytest.mark.parametrize("role", ["student", "parent"])
    def test_students_and_parents_are_outside_the_rule(self, client, school, role):
        client.force_login(_staff(school, role))

        resp = client.get(reverse("dashboard"))

        assert not (resp.status_code == 302 and resp["Location"].endswith(reverse("setup_2fa")))

    def test_the_password_change_comes_first(self, client, school):
        """المؤقّتةُ تُبدَّل قبل أيّ شيء — ثمّ الثنائيّة."""
        user = _staff(school)
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])
        client.force_login(user)

        resp = client.get(reverse("dashboard"))

        assert resp["Location"].endswith(reverse("force_change_password"))

    def test_the_emergency_flag_lifts_the_rule(self, client, school, settings):
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = False
        client.force_login(_staff(school))

        assert client.get(reverse("dashboard")).status_code == 200
