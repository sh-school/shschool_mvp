"""نبضةُ العامل تُختَم في Redis ويقرؤها فحصٌ خارجيّ — 200 سليم و503 متوقّف/غائب."""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache
from django.test import Client

from core import worker_heartbeat as heartbeat
from core.tasks import worker_heartbeat as heartbeat_task

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_key():
    cache.delete(heartbeat.CACHE_KEY)
    yield
    cache.delete(heartbeat.CACHE_KEY)


def _get():
    return Client().get("/health/worker/")


def test_missing_beat_is_503():
    resp = _get()

    assert resp.status_code == 503
    assert resp.json() == {"status": "missing"}


def test_fresh_beat_is_200_with_its_age():
    heartbeat.record(time.time() - 30)

    resp = _get()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert 29 <= body["age_seconds"] <= 40


def test_stale_beat_is_503():
    heartbeat.record(time.time() - heartbeat.MAX_AGE_SECONDS - 60)

    resp = _get()

    assert resp.status_code == 503
    assert resp.json()["status"] == "stale"


def test_the_threshold_tolerates_a_missed_beat_and_a_deploy():
    assert heartbeat.MAX_AGE_SECONDS >= 3 * 300


def test_the_celery_task_stamps_the_beat():
    assert heartbeat.last_beat() is None

    heartbeat_task()

    beat = heartbeat.last_beat()
    assert beat is not None and abs(time.time() - beat) < 5


def test_the_endpoint_is_public_and_not_cached():
    resp = _get()

    assert resp.status_code in (200, 503)
    assert resp.status_code != 302
    assert "no-cache" in resp["Cache-Control"] or "no-store" in resp["Cache-Control"]


def test_a_broken_cache_is_reported_not_hidden(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(heartbeat, "last_beat", boom)

    resp = _get()

    assert resp.status_code == 503
    assert resp.json() == {"status": "cache-unavailable"}
