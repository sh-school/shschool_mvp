"""لا يضيع ما أدخله المستخدم بانتهاء جلسته — الجانب الخادميّ (W-20261005-003، س١).

الخادم: 401 بعلامة `HX-Trigger: session-expired` لما تُحيله الصفحة بنفسها (HTMX/fetch/تنقّل بلا تحميل)
وبقاء 302 للمتصفّح؛ و`GET /auth/session/status/` قراءةٌ لا تكتب؛ و`POST /auth/session/touch/` يجدّد
الخمول ضمن المطلقة وبكتابةٍ واحدةٍ في الدقيقة؛ وصفحاتُ الدخول تُدرَج في إطارٍ من الأصل نفسِه وحدَه.
والعميل (session-guard.js) تغطّيه tests/e2e/test_session_guard.py.
"""

import time

import pyotp
import pytest
from django.test import Client
from django.urls import reverse

from core.models import encrypt_field
from core.session_policy import limits_for
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

PASSWORD = "Probe-Passw0rd-2FA!"  # pragma: allowlist secret
STATUS = "/auth/session/status/"
TOUCH = "/auth/session/touch/"


def _protected_url():
    return reverse("dashboard")


@pytest.mark.django_db
class TestExpiredSessionAnswers401ForPageRequests:
    """ما يطلبه السكربت لا يُحوَّل إلى صفحة دخول يُدرجها في موضع الاستجابة."""

    @pytest.mark.parametrize(
        "headers",
        [
            {"HTTP_HX_REQUEST": "true"},
            {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"},
            {"HTTP_ACCEPT": "application/json"},
            {"HTTP_X_PAGE_NAV": "1", "HTTP_ACCEPT": "text/html"},
        ],
        ids=["htmx", "xhr", "json-accept", "page-nav"],
    )
    def test_background_request_gets_401_with_the_trigger(self, client, headers):
        resp = client.get(_protected_url(), **headers)
        assert resp.status_code == 401
        assert resp["HX-Trigger"] == "session-expired"
        assert resp.json()["code"] == "session_expired"
        assert "no-store" in resp["Cache-Control"]

    def test_post_from_a_page_keeps_its_401_so_the_form_data_can_be_replayed(self, client):
        resp = client.post(_protected_url(), {"x": "1"}, HTTP_X_PAGE_NAV="1")
        assert resp.status_code == 401 and resp["HX-Trigger"] == "session-expired"

    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"HTTP_ACCEPT": "*/*"},
            {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/json;q=0.9"},
        ],
        ids=["plain", "any", "browser-navigation"],
    )
    def test_browser_navigation_still_redirects_to_login(self, client, headers):
        resp = client.get(_protected_url(), **headers)
        assert resp.status_code == 302
        assert resp["Location"].startswith(reverse("login"))
        assert "HX-Trigger" not in resp

    def test_a_live_session_is_not_answered_401(self, client, teacher_user):
        client.force_login(teacher_user)
        resp = client.get(_protected_url(), HTTP_HX_REQUEST="true")
        assert resp.status_code != 401


@pytest.mark.django_db
class TestSessionIsStampedAtLogin:
    def test_login_stamps_login_and_touch_times(self, client, teacher_user):
        before = int(time.time())
        client.force_login(teacher_user)
        session = client.session
        assert before <= session["_login_at"] <= int(time.time())
        assert session["_last_touch"] == session["_login_at"]

    def test_password_login_stamps_too(self, client, teacher_user):
        resp = client.post(
            reverse("login"), {"identifier": teacher_user.national_id, "password": "testpass123"}
        )
        assert resp.status_code == 302
        assert "_login_at" in client.session


@pytest.mark.django_db
class TestStatusEndpoint:
    def test_unauthenticated_gets_401_with_the_trigger(self, client):
        resp = client.get(STATUS)
        assert resp.status_code == 401 and resp["HX-Trigger"] == "session-expired"
        assert resp.json()["authenticated"] is False

    def test_reports_remaining_time_and_user(self, client, teacher_user):
        client.force_login(teacher_user)
        body = client.get(STATUS).json()
        idle = limits_for("teacher").idle
        assert body["authenticated"] is True
        assert body["user_id"] == str(teacher_user.pk)
        assert body["must_change_password"] is False
        assert body["idle_limit"] == idle
        assert 0 < body["idle_remaining"] <= idle
        assert 0 < body["absolute_remaining"] <= 8 * 3600
        assert body["csrf_token"]

    def test_staff_get_eight_hours_and_a_parent_two(self, client, teacher_user, parent_user):
        client.force_login(teacher_user)
        assert client.get(STATUS).json()["absolute_limit"] == 8 * 3600
        other = Client()
        other.force_login(parent_user)
        assert other.get(STATUS).json()["absolute_limit"] == 2 * 3600

    def test_status_never_writes_the_session(self, client, teacher_user):
        client.force_login(teacher_user)
        session = client.session
        session["_last_touch"] -= 1000  # عتيقٌ ليظهر أيُّ تجديدٍ خفيّ
        session.save()
        stamp = client.session["_last_touch"]
        for _ in range(3):
            client.get(STATUS)
        assert client.session["_last_touch"] == stamp

    def test_a_session_from_before_the_stamp_is_stamped_by_its_first_request(
        self, client, teacher_user
    ):
        client.force_login(teacher_user)
        session = client.session
        del session["_login_at"], session["_last_touch"]
        session.save()
        body = client.get(STATUS).json()
        assert body["idle_remaining"] > 0 and body["absolute_remaining"] > 0
        assert "_login_at" in client.session

    def test_post_is_not_allowed(self, client, teacher_user):
        client.force_login(teacher_user)
        assert client.post(STATUS).status_code == 405


@pytest.mark.django_db
class TestTouchEndpoint:
    def test_requires_a_session(self, client):
        resp = client.post(TOUCH)
        assert resp.status_code == 401 and resp["HX-Trigger"] == "session-expired"

    def test_get_is_not_allowed(self, client, teacher_user):
        client.force_login(teacher_user)
        assert client.get(TOUCH).status_code == 405

    def test_csrf_is_enforced(self, teacher_user):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(teacher_user)
        assert strict.post(TOUCH).status_code == 403

    def test_a_second_touch_within_a_minute_writes_nothing(self, client, teacher_user):
        client.force_login(teacher_user)
        body = client.post(TOUCH).json()
        assert body["renewed"] is False and body["reason"] == "recent"

    def test_renews_the_idle_clock_after_the_minimum_interval(self, client, teacher_user):
        client.force_login(teacher_user)
        session = client.session
        session["_last_touch"] -= 600
        session.save()
        body = client.post(TOUCH).json()
        assert body["renewed"] is True and body["reason"] == ""
        assert body["idle_remaining"] > limits_for("teacher").idle - 5
        assert int(time.time()) - client.session["_last_touch"] <= 2

    def test_never_extends_past_the_absolute_limit(self, client, teacher_user):
        """بعد المطلقة يُنهي الميدلوير الجلسةَ قبل الوصول إلى النبضة: لا تجديدَ ولا جلسة."""
        client.force_login(teacher_user)
        session = client.session
        session["_login_at"] -= 9 * 3600
        session["_last_touch"] -= 600
        session.save()
        resp = client.post(TOUCH)
        assert resp.status_code == 401 and resp["HX-Trigger"] == "session-expired"
        assert client.get(STATUS).status_code == 401

    def test_a_parent_is_ended_after_two_hours(self, client, parent_user):
        client.force_login(parent_user)
        session = client.session
        session["_login_at"] -= 3 * 3600
        session["_last_touch"] -= 60
        session.save()
        assert client.post(TOUCH).status_code == 401

    def test_a_session_from_before_the_stamp_is_stamped_by_its_first_request(
        self, client, teacher_user
    ):
        """الميدلوير يختم الجلسةَ السابقةَ للختم عند أوّل طلب، فيجد النبضُ ختماً حديثاً."""
        client.force_login(teacher_user)
        session = client.session
        del session["_login_at"], session["_last_touch"]
        session.save()
        body = client.post(TOUCH).json()
        assert body["reason"] == "recent"
        assert "_login_at" in client.session and body["idle_remaining"] > 0


@pytest.mark.django_db
class TestLoginPagesCanBeFramedBySameOriginOnly:
    """نافذةُ إعادة الدخول تُدرج صفحةَ الدخول في إطار؛ وفي الإنتاج `X_FRAME_OPTIONS = "DENY"`."""

    @pytest.fixture(autouse=True)
    def _production_frame_policy(self, settings):
        settings.X_FRAME_OPTIONS = "DENY"

    def test_login_page(self, client):
        assert client.get(reverse("login"))["X-Frame-Options"] == "SAMEORIGIN"

    def test_done_page(self, client):
        assert client.get(reverse("session_done"))["X-Frame-Options"] == "SAMEORIGIN"

    def test_second_factor_step(self, client, school, settings):
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = True
        user = UserFactory(password=PASSWORD)
        MembershipFactory(
            user=user, school=school, role=RoleFactory(school=school, name="principal")
        )
        secret = pyotp.random_base32()
        user.totp_secret = encrypt_field(secret) or secret
        user.totp_enabled = True
        user.save(update_fields=["totp_secret", "totp_enabled"])
        session = client.session
        session["pending_2fa_user"] = str(user.pk)
        session.save()
        assert client.get(reverse("verify_2fa"))["X-Frame-Options"] == "SAMEORIGIN"

    def test_force_change_password_step(self, client, teacher_user):
        teacher_user.must_change_password = True
        teacher_user.save(update_fields=["must_change_password"])
        client.force_login(teacher_user)
        assert client.get(reverse("force_change_password"))["X-Frame-Options"] == "SAMEORIGIN"

    def test_every_other_page_stays_denied(self, client, teacher_user):
        client.force_login(teacher_user)
        assert client.get(reverse("dashboard"))["X-Frame-Options"] == "DENY"
        assert client.get(reverse("change_password"))["X-Frame-Options"] == "DENY"


@pytest.mark.django_db
class TestLoginInsideTheDialog:
    def test_the_form_keeps_the_query_so_next_survives_the_post(self, client):
        html = client.get(reverse("login") + "?next=/auth/session/done/&embed=1").content.decode()
        assert 'action="/auth/login/"' not in html
        assert "is-embedded" in html

    def test_login_returns_to_the_done_page(self, client, teacher_user):
        resp = client.post(
            reverse("login") + "?next=/auth/session/done/&embed=1",
            {"identifier": teacher_user.national_id, "password": "testpass123"},
        )
        assert resp.status_code == 302 and resp["Location"] == reverse("session_done")

    def test_next_is_carried_to_the_second_factor_step(self, client, school, settings):
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = True
        user = UserFactory(password=PASSWORD)
        MembershipFactory(
            user=user, school=school, role=RoleFactory(school=school, name="principal")
        )
        secret = pyotp.random_base32()
        user.totp_secret = encrypt_field(secret) or secret
        user.totp_enabled = True
        user.save(update_fields=["totp_secret", "totp_enabled"])

        first = client.post(
            reverse("login") + "?next=/auth/session/done/&embed=1",
            {"identifier": user.national_id, "password": PASSWORD},
        )
        verify = reverse("verify_2fa") + "?next=%2Fauth%2Fsession%2Fdone%2F"
        assert first["Location"] == verify

        second = client.post(verify, {"code": pyotp.TOTP(secret).now()})
        assert second["Location"] == reverse("session_done")

    def test_a_foreign_next_is_not_carried(self, client, school, settings):
        settings.TWO_FACTOR_REQUIRED_FOR_STAFF = True
        user = UserFactory(password=PASSWORD)
        MembershipFactory(
            user=user, school=school, role=RoleFactory(school=school, name="principal")
        )
        secret = pyotp.random_base32()
        user.totp_secret = encrypt_field(secret) or secret
        user.totp_enabled = True
        user.save(update_fields=["totp_secret", "totp_enabled"])
        first = client.post(
            reverse("login") + "?next=https://evil.example/x",
            {"identifier": user.national_id, "password": PASSWORD},
        )
        assert first["Location"] == reverse("verify_2fa")
