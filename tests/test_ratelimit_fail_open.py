"""سقوطُ Redis كان يُسقط باب الدخول كلَّه — لا حدّاً مرفوضاً بل خطأً 500.

`django_ratelimit.core.get_usage` يلتقط ``socket.gaierror`` وحده حول
``cache.add()``؛ استثناءُ Redis الحقيقيّ (``redis.exceptions.ConnectionError``)
يفلت منه فيسقط العرضَ كلَّه. إعدادُ المكتبة ``RATELIMIT_FAIL_OPEN`` لا يعالج
هذا الفرع (هو لفرعٍ آخر: قيمةٌ فارغة بلا استثناء) — فالإصلاحُ الفعليّ مُزيِّنٌ
في ``core/ratelimit_safe.py`` يلفّ ``ratelimit`` الأصليّ ويعامل خطأ Redis
كـ«غير محدود». وقفلُ axes الحقيقيّ يبقى عاملاً كاملاً لأنّه في القاعدة لا
في Redis (``AxesDatabaseHandler`` الافتراضيّ)، فلا خسارة أمنيّةٍ حقيقيّة.
"""

import pytest
import redis
from django.core.cache import caches
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django_ratelimit.decorators import ratelimit as _raw_ratelimit

from core.ratelimit_safe import ratelimit as _safe_ratelimit

WRONG = {"identifier": "00000000000", "password": "wrong-password"}  # pragma: allowlist secret


def _break_cache(monkeypatch):
    backend = caches["default"]

    def _raise(*a, **k):
        raise redis.exceptions.ConnectionError("redis down")

    for method in ("get", "incr", "set", "add"):
        monkeypatch.setattr(backend, method, _raise, raising=False)


def _view(request):
    return HttpResponse("ok")


class TestTheSafeDecoratorItself:
    """وحدويّاً — بلا شبكة HTTP ولا قاعدة — يعزل أثر المُزيِّن وحده.

    ``RATELIMIT_ENABLE=False`` افتراضُ بيئة الاختبار (testing.py) — بلا
    ``@override_settings(RATELIMIT_ENABLE=True)`` على كلّ دالّة يعود
    ``get_usage`` صفراً قبل أن يلمس الـcache، فلا يُثبت شيئاً.
    """

    @override_settings(RATELIMIT_ENABLE=True)
    def test_the_raw_decorator_crashes_when_redis_is_down(self, monkeypatch):
        """ضبطٌ سالب: يُثبت أنّ العلّة في المكتبة نفسها، لا في وهمٍ افترضناه."""
        _break_cache(monkeypatch)
        decorated = _raw_ratelimit(key="ip", rate="1/m", block=True)(_view)
        request = RequestFactory().post("/x/")

        with pytest.raises(redis.exceptions.ConnectionError):
            decorated(request)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_the_safe_decorator_lets_the_request_through_when_redis_is_down(self, monkeypatch):
        _break_cache(monkeypatch)
        decorated = _safe_ratelimit(key="ip", rate="1/m", block=True)(_view)
        request = RequestFactory().post("/x/")

        response = decorated(request)

        assert response.status_code == 200
        assert response.content == b"ok"

    @override_settings(RATELIMIT_ENABLE=True)
    def test_the_safe_decorator_still_blocks_a_real_excess(self, monkeypatch):
        """لا يُخدَع المُزيِّن: تجاوزُ الحدّ الحقيقيّ (لا سقوطَ Redis) يبقى محجوباً."""
        from django.core.cache import cache

        cache.clear()
        decorated = _safe_ratelimit(key="ip", rate="1/m", method="POST", block=True)(_view)
        request = RequestFactory().post("/x/")

        decorated(request)  # الأولى تمرّ
        from django_ratelimit.exceptions import Ratelimited

        with pytest.raises(Ratelimited):
            decorated(request)  # الثانية خلال الدقيقة نفسِها تُحجب
        cache.clear()


@pytest.mark.django_db
@override_settings(RATELIMIT_ENABLE=True)
def test_login_survives_a_broken_cache_end_to_end(client, monkeypatch):
    """تكامليّاً على `/auth/login/` الحقيقيّ — لا تفويضاً بمحاكاة."""
    _break_cache(monkeypatch)

    resp = client.post("/auth/login/", WRONG)

    assert resp.status_code != 500


class TestTheFailOpenAlertIsMonitored:
    """كان السقوطُ الفعليّ يُسجَّل بـ`warning` فقط — وSentry (production.py)
    لا يرفع إلى حدثٍ إلّا عند `event_level="ERROR"` فما فوق، فلا يصل تنبيهٌ
    فعليّ لأحد حين يُفتح الباب. `_report_fail_open` يرفع أوّل سقوطٍ إلى
    `error` (تنبيهٌ حقيقيّ)، ويُهدّئ ما بعده خلال نافذة التهدئة إلى
    `warning` وحده — لئلّا يُغرق Sentry بحادثةٍ واحدة مستمرّة.
    """

    @override_settings(RATELIMIT_ENABLE=True)
    def test_the_first_failure_is_logged_as_an_error(self, monkeypatch, caplog):
        import core.ratelimit_safe as rl

        monkeypatch.setattr(rl, "_last_alert_at", 0.0)
        _break_cache(monkeypatch)
        decorated = _safe_ratelimit(key="ip", rate="1/m", block=True)(_view)
        request = RequestFactory().post("/x/")

        with caplog.at_level("WARNING", logger="core.ratelimit_safe"):
            decorated(request)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "ERROR"
        assert "failed open" in caplog.records[0].message

    @override_settings(RATELIMIT_ENABLE=True)
    def test_a_second_failure_within_the_cooloff_is_only_a_warning(self, monkeypatch, caplog):
        import core.ratelimit_safe as rl

        monkeypatch.setattr(rl, "_last_alert_at", 0.0)
        _break_cache(monkeypatch)
        decorated = _safe_ratelimit(key="ip", rate="1/m", block=True)(_view)
        request = RequestFactory().post("/x/")

        with caplog.at_level("WARNING", logger="core.ratelimit_safe"):
            decorated(request)  # الأولى: error
            decorated(request)  # الثانية خلال نفس النافذة: warning مهدَّأ

        levels = [r.levelname for r in caplog.records]
        assert levels == ["ERROR", "WARNING"]
