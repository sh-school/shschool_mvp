"""مِفصلُ اليوم يعمل مرّةً في اليوم لكلّ عمليّة — ولو غاب Redis.

كان الارتدادُ عند سقوط الـcache سمةً على الطلب، فيعمل المِفصل — حارسُ العام
وتوليدُ حصص اليوم — مع **كلّ** طلبٍ حتّى يعود Redis. ذاكرةُ العمليّة تُبقيه
مرّةً في اليوم مهما كان حالُ الـcache.
"""

from types import SimpleNamespace

import pytest
import redis

from operations import middleware as mw


@pytest.fixture(autouse=True)
def _fresh_memo():
    mw._DONE_TODAY.clear()
    yield
    mw._DONE_TODAY.clear()


class _BrokenCache:
    """cache يرمي — كما يفعل عميلُ Redis حين يسقط الخادم."""

    def get(self, key):
        raise ConnectionError("redis down")

    def set(self, key, value, timeout=None):
        raise ConnectionError("redis down")


class _BrokenRedisCache:
    """cache يرمي استثناء `redis` الحقيقيّ — لا `ConnectionError` المدمجة.

    `redis.exceptions.ConnectionError` لا يرث من `ConnectionError` المدمجة
    (`issubclass(...) is False`) — فهذا هو الاستثناء الذي كان يفلت من
    `except (OSError, ConnectionError)` ويُسقط المِفصل على **كلّ** طلب.
    """

    def get(self, key):
        raise redis.exceptions.ConnectionError("redis down")

    def set(self, key, value, timeout=None):
        raise redis.exceptions.ConnectionError("redis down")


def _request(user):
    return SimpleNamespace(path="/dashboard/", user=user)


def test_the_seam_runs_once_per_day_when_the_cache_is_down(school, teacher_user, monkeypatch):
    calls = {"retire": 0, "sessions": 0}
    monkeypatch.setattr(mw, "cache", _BrokenCache())
    from operations.services import ScheduleService

    def fake_retire(s, on=None):
        calls["retire"] += 1
        return {"assignments": 0, "slots": 0}

    def fake_sessions(s, day):
        calls["sessions"] += 1
        return 0

    monkeypatch.setattr(ScheduleService, "retire_past_year_records", staticmethod(fake_retire))
    monkeypatch.setattr(ScheduleService, "ensure_sessions_for_date", staticmethod(fake_sessions))

    seam = mw.SessionAutoGenerateMiddleware(lambda r: None)
    for _ in range(5):
        seam._ensure_sessions(_request(teacher_user))

    assert calls == {"retire": 1, "sessions": 1}, "خمسةُ طلباتٍ — عملٌ واحد"


def test_a_cache_hit_from_another_worker_is_remembered_locally(school, teacher_user, monkeypatch):
    """عاملٌ آخر أنجزه وكتبه في الـcache: نقرؤه مرّةً ثمّ لا نعود إلى Redis."""
    reads = {"n": 0}

    class _Cache:
        def get(self, key):
            reads["n"] += 1
            return True

        def set(self, key, value, timeout=None):
            pass

    monkeypatch.setattr(mw, "cache", _Cache())
    seam = mw.SessionAutoGenerateMiddleware(lambda r: None)
    for _ in range(3):
        seam._ensure_sessions(_request(teacher_user))

    assert reads["n"] == 1


def test_a_real_redis_connection_error_does_not_crash_the_seam(school, teacher_user, monkeypatch):
    """`redis.exceptions.ConnectionError` الحقيقيّ — لا مجرّد `ConnectionError` مدمجة."""
    monkeypatch.setattr(mw, "cache", _BrokenRedisCache())
    from operations.services import ScheduleService

    monkeypatch.setattr(
        ScheduleService, "retire_past_year_records", staticmethod(lambda s, on=None: {})
    )
    monkeypatch.setattr(ScheduleService, "ensure_sessions_for_date", staticmethod(lambda s, d: 0))

    seam = mw.SessionAutoGenerateMiddleware(lambda r: "ok")
    response = seam(_request(teacher_user))  # لا يجوز أن يرفع — الطلب كلّه ينهار لولا الإصلاح

    assert response == "ok"
