"""عدّادُ أخطاء الخادم (5xx) وبطاقتُه في رئيسيّة الإدارة (OWN-23) — يعدّ الحقيقيَّ وحدَه، ولا يُسرّب، ولا يُسقط طلباً."""

import asyncio
import time

import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from core import error_counter
from core.middleware_errors import ServerErrorCounterMiddleware, route_of
from roadmap import admin_monitor
from roadmap.admin_monitor import BAD, OK, WARN
from tests import urls_server_errors

pytestmark = pytest.mark.django_db

HOUR = error_counter.BUCKET_SECONDS
NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def urls(settings):
    """مسارات الاختبار خلف الوسيط وحدَه — وسطاءُ المنصّة (المصادقة وحارس المسارات) خارج ما يُختبَر هنا."""
    settings.ROOT_URLCONF = "tests.urls_server_errors"
    settings.MIDDLEWARE = ["core.middleware_errors.ServerErrorCounterMiddleware"]


def _client(client):
    client.raise_request_exception = False
    return client


# ── التخزين ─────────────────────────────────────────────────────────────────────


def test_the_last_24_hours_are_counted_apart_from_the_24_before():
    error_counter.record("GET a/", now=NOW)
    error_counter.record("GET a/", now=NOW - 5 * HOUR)
    error_counter.record("GET a/", now=NOW - 30 * HOUR)  # الأربعُ والعشرون التي قبلها
    error_counter.record("GET a/", now=NOW - 47 * HOUR)

    assert error_counter.counts(NOW) == (2, 2)


def test_an_error_older_than_48_hours_is_not_counted():
    error_counter.record("GET a/", now=NOW - 60 * HOUR)

    assert error_counter.counts(NOW) == (0, 0)


def test_only_the_route_pattern_and_class_are_kept_and_the_route_is_capped():
    error_counter.record("GET " + "x" * 500, "ValueError", now=NOW)

    last = error_counter.last_error()

    assert last is not None
    assert last["exc"] == "ValueError" and last["at"] == NOW
    assert len(last["route"]) == 120


def test_a_dead_cache_never_raises(monkeypatch):
    class _Dead:
        def __getattr__(self, name):
            raise ConnectionError("redis down")

    monkeypatch.setattr(error_counter, "cache", _Dead())

    error_counter.record("GET a/", "X")  # لا استثناء — العدُّ لا يُسقط طلباً


def test_a_bucket_that_expires_between_add_and_incr_still_counts(monkeypatch):
    real_incr = cache.incr

    def expired(key, *args, **kwargs):
        cache.delete(key)
        return real_incr(key, *args, **kwargs)  # ValueError: المفتاحُ غير موجود

    monkeypatch.setattr(cache, "incr", expired)

    error_counter.record("GET a/", now=NOW)

    assert error_counter.counts(NOW)[0] == 1


# ── الوسيط ──────────────────────────────────────────────────────────────────────


def test_an_unhandled_exception_is_counted_with_the_route_pattern_not_the_raw_url(client, urls):
    response = _client(client).get("/boom/4242/")

    assert response.status_code == 500
    assert error_counter.counts()[0] == 1
    last = error_counter.last_error()
    assert last is not None
    assert last["route"] == "GET boom/<int:pk>/" and last["exc"] == "RuntimeError"


def test_nothing_personal_is_stored(client, urls):
    """نصُّ الاستثناء (وفيه رقمٌ شخصيّ هنا) وقيمةُ المعرّف في الرابط لا يُخزَّنان."""
    _client(client).get("/boom/4242/")

    bucket = f"err5xx:{int(time.time() // HOUR)}"
    stored = repr(error_counter.last_error()) + repr(cache.get_many([bucket]))

    assert urls_server_errors.SECRET not in stored and "4242" not in stored


def test_an_explicit_5xx_response_is_counted_without_an_exception_class(client, urls):
    _client(client).get("/explicit/")

    last = error_counter.last_error()
    assert error_counter.counts()[0] == 1
    assert last is not None and last["exc"] == ""


def test_a_successful_response_is_not_counted(client, urls):
    _client(client).get("/fine/")

    assert error_counter.counts() == (0, 0)
    assert error_counter.last_error() is None


def test_the_health_endpoints_are_excluded(client, urls):
    """`/health/…` تُرجع 503 عمداً حين يتوقّف العاملُ أو الـcache — ذلك يخصّ بطاقاتٍ أخرى."""
    _client(client).get("/health/down/")

    assert error_counter.counts() == (0, 0)


def test_the_async_path_counts_too():
    async def get_response(request):
        return HttpResponse(status=502)

    middleware = ServerErrorCounterMiddleware(get_response)
    request = HttpRequest()
    request.method = "POST"
    request.path = "/api/x/"

    response = asyncio.run(middleware(request))

    assert response.status_code == 502
    assert error_counter.counts()[0] == 1
    assert error_counter.last_error()["route"] == "POST بلا مسار"


def test_a_request_without_a_resolved_route_is_named_plainly():
    request = HttpRequest()
    request.method = "GET"

    assert route_of(request) == "GET بلا مسار"


def test_the_counter_sits_before_the_middleware_that_can_fail():
    """مبكّرٌ عمداً: ما يُنتجه الوسطاءُ الداخليّون (503 من RLS، وانقطاعُ القاعدة في المصادقة) يمرّ به."""
    order = list(django_settings.MIDDLEWARE)
    counter = order.index("core.middleware_errors.ServerErrorCounterMiddleware")

    for later in (
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "core.middleware_rls.RLSMiddleware",
    ):
        assert counter < order.index(later), later


# ── البطاقة ─────────────────────────────────────────────────────────────────────


def test_the_card_is_green_with_no_errors():
    card = admin_monitor.server_errors(NOW)

    assert card.level == OK and card.value == "0"
    assert "= أمس 0" in card.detail


@pytest.mark.parametrize(
    ("count", "level"),
    [
        (1, WARN),
        (admin_monitor.SERVER_ERRORS_BAD - 1, WARN),
        (admin_monitor.SERVER_ERRORS_BAD, BAD),
    ],
)
def test_the_card_turns_amber_then_red(count, level):
    for _ in range(count):
        error_counter.record("GET a/", "X", now=NOW - 60)

    card = admin_monitor.server_errors(NOW)

    assert card.level == level and card.value == str(count)


def test_the_card_names_the_last_error_and_how_long_ago():
    error_counter.record("GET reports/<int:pk>/", "OperationalError", now=NOW - 3 * 60)

    detail = admin_monitor.server_errors(NOW).detail

    assert "GET reports/<int:pk>/" in detail and "OperationalError" in detail
    assert "قبل 3 دقيقة" in detail


def test_the_card_shows_the_trend_against_the_day_before():
    error_counter.record("GET a/", now=NOW)
    error_counter.record("GET a/", now=NOW - 30 * HOUR)
    error_counter.record("GET a/", now=NOW - 31 * HOUR)

    assert "↓ أمس 2" in admin_monitor.server_errors(NOW).detail


def test_the_card_reports_whether_sentry_is_configured(settings):
    settings.SENTRY_DSN = ""
    assert "Sentry غير مضبوط" in admin_monitor.server_errors(NOW).detail

    settings.SENTRY_DSN = "https://key@o1.ingest.sentry.io/2"
    detail = admin_monitor.server_errors(NOW).detail

    assert "Sentry مضبوط" in detail and "key@" not in detail  # المفتاحُ لا يُعرض


def test_the_card_links_to_sentry_only_over_https(settings):
    settings.SENTRY_ISSUES_URL = "https://sentry.io/organizations/x/issues/"
    assert admin_monitor.server_errors(NOW).url == settings.SENTRY_ISSUES_URL

    for unsafe in ("", "http://sentry.io/x", "javascript:alert(1)"):
        settings.SENTRY_ISSUES_URL = unsafe
        assert admin_monitor.server_errors(NOW).url == "", unsafe


def test_the_card_is_one_of_the_developer_cards():
    assert admin_monitor.server_errors in admin_monitor.BUILDERS
