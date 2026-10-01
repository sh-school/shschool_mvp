"""[COMMAND-CENTER] لوحةُ «ما نُشر اليوم» — عددُ الطلبات المدموجة اليوم وحالةُ نشرها، بلا عنوانٍ ولا رقمِ طلب."""

import pytest
from django.core.cache import cache

from command_center import collectors, contract
from command_center.collectors import github, today

pytestmark = pytest.mark.django_db

#: 2027-01-06T09:00:00Z — منتصفُ نهارٍ بتوقيت الدوحة، فمنتصفُ ليل اليوم واضحٌ لا حدّيّ.
NOW = 1_799_312_400.0
DAY = 86400


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _panel():
    return next(p for p in contract.read_panels() if p["key"] == "today")


def _iso(seconds_before_now):
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - seconds_before_now))


def _fetch_with(merged, deploy):
    def fake_fetch(path, reduce):
        if path == today.MERGED_PATH:
            return reduce(merged)
        if path == today.DEPLOY_PATH:
            return reduce(deploy)
        raise AssertionError(path)

    return fake_fetch


def test_the_panel_is_registered_as_remote():
    assert "today" in collectors.REMOTE


def test_no_third_party_text_is_ever_stored(monkeypatch):
    merged = [{"merged_at": _iso(3600), "title": "سرّ لا يُخزَّن", "number": 999}]
    deploy = [{"created_at": _iso(0)}]
    monkeypatch.setattr(github, "fetch", _fetch_with(merged, deploy))
    today.collect(NOW)
    panel = _panel()
    assert "999" not in str(panel) and "سرّ" not in str(panel)


def test_merged_today_all_published(monkeypatch):
    merged = [{"merged_at": _iso(3600)}, {"merged_at": _iso(7200)}]
    deploy = [{"created_at": _iso(0)}]
    monkeypatch.setattr(github, "fetch", _fetch_with(merged, deploy))
    today.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.OK
    assert panel["gauge"] == 100
    values = {m["label"]: m["value"] for m in panel["metrics"]}
    assert values["مدموجةٌ اليوم"] == "2"
    assert values["نُشرت منها"] == "2"
    assert values["بانتظار الدفعة"] == "0"


def test_merged_today_pending_publish(monkeypatch):
    merged = [{"merged_at": _iso(3600)}, {"merged_at": _iso(7200)}]
    deploy = [{"created_at": _iso(DAY)}]  # آخرُ نشرٍ كان أمس، قبل كلّ ما دُمج اليوم
    monkeypatch.setattr(github, "fetch", _fetch_with(merged, deploy))
    today.collect(NOW)
    panel = _panel()
    values = {m["label"]: m["value"] for m in panel["metrics"]}
    assert values["مدموجةٌ اليوم"] == "2"
    assert values["نُشرت منها"] == "0"
    assert values["بانتظار الدفعة"] == "2"
    assert panel["gauge"] == 0


def test_nothing_merged_today_has_no_gauge(monkeypatch):
    merged = [{"merged_at": _iso(2 * DAY)}]  # أمسِ الأوّل، خارج اليوم
    deploy = [{"created_at": _iso(0)}]
    monkeypatch.setattr(github, "fetch", _fetch_with(merged, deploy))
    today.collect(NOW)
    panel = _panel()
    assert panel["headline"] == "لا شيءَ دُمج اليوم"
    assert panel["gauge"] is None


def test_a_deploy_reply_missing_the_stamp_key_does_not_raise(monkeypatch):
    """W-20260930-001: قاموسُ نشرٍ خالٍ من "stamp" كان يُسقط المجمِّع بـKeyError."""
    merged = [{"merged_at": _iso(3600)}]

    def fake_fetch(path, reduce):
        if path == today.MERGED_PATH:
            return reduce(merged)
        if path == today.DEPLOY_PATH:
            return {}
        raise AssertionError(path)

    monkeypatch.setattr(github, "fetch", fake_fetch)
    today.collect(NOW)
    panel = _panel()
    assert panel["ok"] is True
    values = {m["label"]: m["value"] for m in panel["metrics"]}
    assert values["نُشرت منها"] == "0"
    assert values["بانتظار الدفعة"] == "1"


def test_a_github_failure_keeps_the_last_value(monkeypatch):
    merged = [{"merged_at": _iso(3600)}]
    deploy = [{"created_at": _iso(0)}]
    monkeypatch.setattr(github, "fetch", _fetch_with(merged, deploy))
    today.collect(NOW)
    ok_headline = _panel()["headline"]

    monkeypatch.setattr(github, "fetch", lambda path, reduce: None)
    today.collect(NOW)
    panel = _panel()
    assert panel["ok"] is False
    assert panel["headline"] == ok_headline
