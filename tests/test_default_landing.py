"""الوجهةُ الافتراضيّة: لا حلقةَ بين الدخول والمنع — W-20261003-024 (P1).

دخل المالكُ بحساب دور `specialist` فخرج على «ليس لديك صلاحيات»؛ و/auth/login/ ← /dashboard/ ← 403 حلقةٌ بلا مخرج.
والدورُ يملك `behavior.committee` فيُفتح له /behavior/committee/. فالوجهةُ تُحسب من القدرة الفعليّة (`core/landing.py`).
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from core.landing import ROLE_LANDINGS, default_landing
from core.models.access import Role
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_staff_register_screen import principal, school  # noqa: F401

pytestmark = pytest.mark.django_db


def _user_with_role(school, role_name: str, national_id: str):
    user = UserFactory(full_name=f"مستخدم {role_name}", national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


class TestTheLandingIsComputedFromTheCapability:
    def test_a_role_with_a_dashboard_lands_on_it(self, principal):
        assert default_landing(principal) == reverse("dashboard")

    def test_a_specialist_lands_on_the_committee(self, school):
        user = _user_with_role(school, "specialist", "29100000001")

        assert default_landing(user) == reverse("behavior:committee")

    def test_the_table_never_overrides_a_missing_capability(self, school, monkeypatch):
        """الجدولُ وجهةٌ لا صلاحيّة: إن لم يملك الدورُ القدرةَ المرافقة فلا وجهةَ."""
        from core import landing

        user = _user_with_role(school, "specialist", "29100000002")
        real = landing.has_capability
        monkeypatch.setattr(
            landing,
            "has_capability",
            lambda u, key: False if key == "behavior.committee" else real(u, key),
        )

        assert default_landing(user) is None


class TestNoLoopBetweenLoginAndTheDenial:
    def test_the_dashboard_sends_a_specialist_to_the_committee_not_to_403(self, client, school):
        user = _user_with_role(school, "specialist", "29100000003")
        client.force_login(user)

        response = client.get(reverse("dashboard"))

        assert response.status_code == 302
        assert response["Location"] == reverse("behavior:committee")

    def test_the_login_page_for_a_signed_in_specialist_ends_on_the_committee(self, client, school):
        user = _user_with_role(school, "specialist", "29100000004")
        client.force_login(user)

        response = client.get(reverse("login"), follow=True)

        assert response.redirect_chain[-1][0] == reverse("behavior:committee")
        assert response.status_code == 200

    def test_a_role_with_no_landing_still_gets_the_denial_with_a_logout(
        self, client, school, monkeypatch
    ):
        """بلا وجهةٍ تبقى صفحةُ المنع — وفيها زرُّ الخروج (إيداعٌ سابق) فلا فخَّ."""
        user = _user_with_role(school, "specialist", "29100000005")
        monkeypatch.setattr("core.landing.ROLE_LANDINGS", {})
        client.force_login(user)

        response = client.get(reverse("dashboard"))

        assert response.status_code == 403


class TestEveryRoleHasAWayIn:
    """حارسٌ: كلُّ دورٍ في المنصّة له لوحةٌ أو وجهةٌ تُفتح له فعلاً — فإضافةُ دورٍ بلا مدخلٍ تُسقطه."""

    @pytest.mark.parametrize(
        ("index", "code"), list(enumerate(code for code, _label in Role.ROLES))
    )
    def test_the_role_has_a_dashboard_or_a_reachable_landing(self, client, school, index, code):
        user = _user_with_role(school, code, f"29200{index:05d}")

        landing = default_landing(user)

        assert landing is not None, f"الدورُ {code} بلا لوحةٍ ولا وجهةٍ — يقع في فخّ 403"
        if code in ROLE_LANDINGS:
            client.force_login(user)
            assert client.get(landing).status_code == 200, f"وجهةُ {code} لا تُفتح له"
