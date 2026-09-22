"""[SECURITY] P1-1 — بابُ JWT مغلقٌ ما لم تُفتح رايتُه.

كان ``/api/v1/auth/token/`` يُصدر رمزَ دخولٍ بكلمة المرور وحدَها: لا ثنائيّة، ولا
axes، ولا حدَّ للمحاولات — ورمزُ التجديد صالحٌ سبعةَ أيّام. وكان «للتطبيق المحمول
المستقبليّ»، ولم يُصدَر منه رمزٌ واحد على الإنتاج. فأُغلق: لا مسار، ولا مُصادِق.
"""

import pytest
from django.conf import settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse


def test_flag_is_off_by_default():
    assert settings.API_JWT_ENABLED is False


@pytest.mark.parametrize("path", ["/api/v1/auth/token/", "/api/v1/auth/token/refresh/"])
def test_token_routes_do_not_exist(path):
    with pytest.raises(Resolver404):
        resolve(path)


@pytest.mark.parametrize("name", ["api_v1:token_obtain", "api_v1:token_refresh"])
def test_token_route_names_do_not_reverse(name):
    with pytest.raises(NoReverseMatch):
        reverse(name)


def test_jwt_authenticator_is_not_installed():
    """رمزٌ صُنع بطريقٍ آخر لا يُقبل — لا مُصادِقَ يقرؤه."""
    classes = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]

    assert not any("JWT" in c for c in classes), classes


@pytest.mark.django_db
def test_posting_credentials_to_the_old_path_issues_nothing(client):
    response = client.post(
        "/api/v1/auth/token/",
        {"national_id": "x", "password": "y"},  # pragma: allowlist secret
        content_type="application/json",
    )

    assert response.status_code != 200
    assert b"access" not in response.content
