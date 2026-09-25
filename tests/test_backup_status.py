"""حالةُ النسخ الاحتياطيّ وبطاقتُها في رئيسيّة الإدارة (OWN-23) — تُجلب في الخلفيّة، ولا تُعرَض إلّا أرقامٌ وتصنيف."""

from datetime import UTC, datetime

import pytest
import requests
from django.core.cache import cache

from core import backup_status, tasks
from roadmap import admin_monitor
from roadmap.admin_monitor import BAD, OK, WARN
from shschool.celery import app

HOUR = 3600
NOW = 1_800_000_000.0


def _iso(seconds_ago: float) -> str:
    return datetime.fromtimestamp(NOW - seconds_ago, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(conclusion: str, hours_ago: float) -> dict:
    return {"conclusion": conclusion, "updated_at": _iso(hours_ago * HOUR), "html_url": "https://x"}


class _Reply:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _stub_get(monkeypatch, reply=None, error=None):
    calls = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        if error:
            raise error
        return reply

    monkeypatch.setattr(backup_status.requests, "get", fake)
    return calls


# ── التحليل ─────────────────────────────────────────────────────────────────────


def test_the_latest_success_and_the_latest_counted_run_are_read():
    parsed = backup_status.parse(
        {"workflow_runs": [_run("failure", 2), _run("success", 26), _run("success", 50)]}
    )

    assert parsed is not None
    assert parsed["latest_ok"] is False
    assert parsed["success_at"] == pytest.approx(NOW - 26 * HOUR, abs=1)
    assert parsed["latest_at"] == pytest.approx(NOW - 2 * HOUR, abs=1)


def test_cancelled_and_skipped_runs_are_neither_a_backup_nor_a_failure():
    parsed = backup_status.parse(
        {"workflow_runs": [_run("cancelled", 1), _run("skipped", 2), _run("success", 20)]}
    )

    assert parsed is not None
    assert parsed["latest_ok"] is True
    assert parsed["success_at"] == pytest.approx(NOW - 20 * HOUR, abs=1)


def test_a_page_with_no_success_reports_none():
    parsed = backup_status.parse({"workflow_runs": [_run("failure", 3)]})

    assert parsed is not None and parsed["success_at"] is None and parsed["latest_ok"] is False


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"workflow_runs": "x"}])
def test_an_unreadable_reply_is_rejected(payload):
    assert backup_status.parse(payload) is None


def test_a_run_with_a_bad_timestamp_is_skipped():
    parsed = backup_status.parse(
        {
            "workflow_runs": [
                {"conclusion": "success", "updated_at": "غير تاريخ"},
                _run("success", 5),
            ]
        }
    )

    assert parsed is not None and parsed["success_at"] == pytest.approx(NOW - 5 * HOUR, abs=1)


# ── الجلب ───────────────────────────────────────────────────────────────────────


def test_the_fetch_stores_numbers_only_and_calls_a_fixed_url_without_a_secret(monkeypatch):
    calls = _stub_get(monkeypatch, _Reply(payload={"workflow_runs": [_run("success", 4)]}))

    assert backup_status.refresh(NOW) is True

    url, kwargs = calls[0]
    assert url.startswith(
        "https://api.github.com/repos/sh-school/shschool_mvp/actions/workflows/backup.yml/runs"
    )
    assert "Authorization" not in kwargs["headers"]  # المستودعُ عامّ: لا رمزَ ولا سرّ
    assert kwargs["timeout"]  # لا طلبَ بلا مهلة
    stored = backup_status.read()
    assert stored is not None
    assert set(stored) == {"success_at", "latest_at", "latest_ok", "fetched_at"}
    assert "https://x" not in repr(stored)  # لا نصَّ من ردّ الطرف الخارجيّ


@pytest.mark.parametrize(
    "reply",
    [_Reply(status=403), _Reply(status=500), _Reply(bad_json=True), _Reply(payload={"x": 1})],
)
def test_a_failed_fetch_keeps_the_last_known_status(monkeypatch, reply):
    _stub_get(monkeypatch, _Reply(payload={"workflow_runs": [_run("success", 4)]}))
    backup_status.refresh(NOW)
    before = backup_status.read()

    _stub_get(monkeypatch, reply)
    assert backup_status.refresh(NOW + HOUR) is False

    assert backup_status.read() == before


def test_a_network_error_never_raises_and_changes_nothing(monkeypatch):
    _stub_get(monkeypatch, error=requests.ConnectionError("down"))

    assert backup_status.refresh(NOW) is False
    assert backup_status.read() is None


def test_the_repo_can_be_overridden(settings):
    settings.BACKUP_STATUS_REPO = "someone/else"

    assert (
        backup_status.workflow_url()
        == "https://github.com/someone/else/actions/workflows/backup.yml"
    )


# ── البطاقة ─────────────────────────────────────────────────────────────────────


def _store(success_hours_ago=None, latest_ok=True, latest_hours_ago=None, fetched_minutes_ago=5):
    cache.set(
        backup_status.CACHE_KEY,
        {
            "success_at": None if success_hours_ago is None else NOW - success_hours_ago * HOUR,
            "latest_at": None if latest_hours_ago is None else NOW - latest_hours_ago * HOUR,
            "latest_ok": latest_ok,
            "fetched_at": NOW - fetched_minutes_ago * 60,
        },
    )


def test_before_the_first_fetch_the_card_is_unknown_not_green():
    card = admin_monitor.backup(NOW)

    assert card.level == WARN and card.value == "غير معلوم"


@pytest.mark.parametrize(
    ("hours", "level"),
    [
        (5, OK),
        (admin_monitor.BACKUP_OK_HOURS, OK),
        (40, WARN),
        (admin_monitor.BACKUP_WARN_HOURS, WARN),
        (60, BAD),
    ],
)
def test_the_card_colour_follows_the_age_of_the_last_success(hours, level):
    _store(success_hours_ago=hours, latest_hours_ago=hours)

    assert admin_monitor.backup(NOW).level == level


def test_a_run_that_failed_after_the_last_success_turns_the_card_red():
    _store(success_hours_ago=26, latest_ok=False, latest_hours_ago=2)

    card = admin_monitor.backup(NOW)

    assert card.level == BAD and "آخرُ تشغيلٍ فشل قبل 2 ساعة" in card.detail


def test_an_old_failure_before_a_newer_success_does_not_count():
    _store(success_hours_ago=2, latest_ok=True, latest_hours_ago=2)

    assert admin_monitor.backup(NOW).level == OK


def test_no_success_at_all_is_red():
    _store(success_hours_ago=None, latest_ok=False, latest_hours_ago=3)

    card = admin_monitor.backup(NOW)

    assert card.level == BAD and card.value == "لا نسخة"


def test_a_stale_status_is_marked_and_never_green():
    _store(success_hours_ago=5, latest_hours_ago=5, fetched_minutes_ago=5 * 60)

    card = admin_monitor.backup(NOW)

    assert card.level == WARN and "(قديمة)" in card.detail


def test_a_stale_status_does_not_soften_a_red_card():
    _store(success_hours_ago=70, latest_hours_ago=70, fetched_minutes_ago=5 * 60)

    assert admin_monitor.backup(NOW).level == BAD


def test_the_card_links_to_the_workflow_page_over_https():
    _store(success_hours_ago=5, latest_hours_ago=5)

    url = admin_monitor.backup(NOW).url

    assert url == "https://github.com/sh-school/shschool_mvp/actions/workflows/backup.yml"


def test_the_card_never_calls_the_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("رُسمت البطاقةُ بطلبٍ خارجيّ")

    monkeypatch.setattr(backup_status.requests, "get", boom)
    _store(success_hours_ago=5, latest_hours_ago=5)

    admin_monitor.backup(NOW)


def test_the_card_is_one_of_the_developer_cards():
    assert admin_monitor.backup in admin_monitor.BUILDERS


# ── المهمّة والجدولة ────────────────────────────────────────────────────────────


@pytest.mark.django_db  # قاعدةُ المهامّ `RLSIsolatedTask` تعيد ضبط سياق RLS عند كلّ استدعاء
def test_the_task_runs_the_refresh(monkeypatch):
    seen = []
    monkeypatch.setattr(backup_status, "refresh", lambda: seen.append(1))

    tasks.refresh_backup_status()

    assert seen == [1]


def test_the_refresh_is_scheduled_at_least_twice_an_hour_and_within_the_rate_limit():
    app.loader.import_default_modules()
    entries = [
        e for e in app.conf.beat_schedule.values() if e["task"] == "core.refresh_backup_status"
    ]

    assert len(entries) == 1 and "core.refresh_backup_status" in app.tasks
    minutes = sorted(entries[0]["schedule"].minute)
    assert 1 <= len(minutes) <= 4, "طلباتُ الساعة تحت حدّ GitHub غير المصادَق (60 لكلّ IP مشترك)"
    gaps = [b - a for a, b in zip(minutes, minutes[1:])] + [60 - minutes[-1] + minutes[0]]
    assert max(gaps) <= 30
