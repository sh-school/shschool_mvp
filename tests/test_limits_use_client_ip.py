"""[SECURITY] P1-2 — الحدُّ والقفلُ بعنوان العميل لا بعنوان الوكيل.

على Railway يصل كلُّ طلبٍ من الوكيل الداخليّ نفسِه (REMOTE_ADDR)، والعميلُ في
X-Forwarded-For. فكان ``ratelimit(key="ip")`` وaxes يريان عنواناً واحداً للجميع:
عشرُ محاولاتٍ خاطئة من شخصٍ واحد تُغلق بابَ الدخول على المدرسة كلّها.
"""

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

PROXY = "100.64.0.8"
EDGE = "152.233.12.245"


def _via_proxy(client_ip):
    return {"REMOTE_ADDR": PROXY, "HTTP_X_FORWARDED_FOR": f"{client_ip}, {EDGE}"}


@override_settings(TRUSTED_PROXY_HOPS=1)
def test_axes_sees_the_client_not_the_proxy():
    from axes.helpers import get_client_ip_address

    request = RequestFactory().post("/auth/login/", **_via_proxy("203.0.113.7"))

    assert get_client_ip_address(request) == "203.0.113.7"


@override_settings(TRUSTED_PROXY_HOPS=1, RATELIMIT_ENABLE=True)
def test_ratelimit_sees_the_client_not_the_proxy():
    from django_ratelimit.core import get_usage

    request = RequestFactory().post("/auth/login/", **_via_proxy("203.0.113.7"))
    other = RequestFactory().post("/auth/login/", **_via_proxy("198.51.100.9"))

    kw = {"group": "p1-2", "key": "ip", "rate": "10/m", "method": "POST", "increment": False}
    cache.clear()
    for _ in range(3):
        get_usage(request, **{**kw, "increment": True})

    assert get_usage(request, **kw)["count"] == 3
    assert get_usage(other, **kw)["count"] == 0


@pytest.mark.django_db
@override_settings(TRUSTED_PROXY_HOPS=1, RATELIMIT_ENABLE=True)
def test_one_client_exhausting_the_login_limit_does_not_block_another(client):
    cache.clear()
    wrong = {"national_id": "00000000000", "password": "wrong-password"}  # pragma: allowlist secret

    for _ in range(10):
        assert client.post("/auth/login/", wrong, **_via_proxy("203.0.113.7")).status_code != 403

    assert client.post("/auth/login/", wrong, **_via_proxy("203.0.113.7")).status_code == 403
    assert client.post("/auth/login/", wrong, **_via_proxy("198.51.100.9")).status_code != 403
    cache.clear()
