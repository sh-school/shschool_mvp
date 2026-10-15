"""فشلُ CSRF يُعرض بصفحةٍ عربيّةٍ بالهويّة وزرّ إعادة تحميل، لا بنصّ Django الخام (W-20261015-018)."""

import pytest
from django.conf import settings
from django.test import Client

from core.views_errors import DEFAULT_RELOAD_URL

pytestmark = pytest.mark.django_db

RAW_MARKERS = ("CSRF verification failed", "Forbidden (403)", "Reason given for failure")


def _failing_post(client: Client, **extra):
    """POST بلا رمز CSRF إلى مسارٍ عامّ (الدخول) — يفشل التحقّقُ قبل أيّ منطق."""
    return client.post("/auth/login/", {"identifier": "x", "password": "y"}, **extra)


def test_setting_points_to_the_branded_view():
    assert settings.CSRF_FAILURE_VIEW == "core.views_errors.csrf_failure"


def test_csrf_failure_is_a_branded_arabic_page_with_reload_button():
    client = Client(enforce_csrf_checks=True)
    response = _failing_post(client)
    body = response.content.decode()
    assert response.status_code == 403
    assert not any(marker in body for marker in RAW_MARKERS)
    assert 'lang="ar"' in body and "إعادة تحميل الصفحة" in body
    assert f'href="{DEFAULT_RELOAD_URL}"' in body


def test_reload_button_returns_to_same_site_referer_only():
    client = Client(enforce_csrf_checks=True)
    own = _failing_post(client, HTTP_REFERER="http://testserver/schedule/")
    assert 'href="http://testserver/schedule/"' in own.content.decode()
    foreign = _failing_post(client, HTTP_REFERER="https://evil.example/phish")
    assert "evil.example" not in foreign.content.decode()
    assert f'href="{DEFAULT_RELOAD_URL}"' in foreign.content.decode()
