"""[COMMAND-CENTER] اللوحاتُ الخمس الأخيرة: قاعدةُ البيانات، والأداءُ والأخطاء (الويب)، وإيقاعُ النشر، وجودةُ الاختبارات، والفحصُ الأمنيّ والاعتماديّات.

كلٌّ منها أرقامٌ لا نصوص، وعطلُ مصدرها لا يُخضِّرها، ولا حكمَ على عيّنةٍ قليلة. وGitHub بلا رمزٍ (الأصل) وبرمزٍ اختياريٍّ يُرسَل رأسُه ولا يُخزَّن.
"""

import time

import pytest
import requests
from django.core.cache import cache
from django.db import connection

from command_center import collectors, contract, webstats
from command_center.collectors import database, delivery, github, quality, supply

pytestmark = pytest.mark.django_db

NOW = 1_800_000_000.0
DAY = 86400


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _panel(key):
    return next(p for p in contract.read_panels() if p["key"] == key)


def _iso(seconds_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - seconds_ago))


def test_the_new_panels_are_registered_once_in_the_right_group():
    assert {"database"} <= set(collectors.LOCAL)
    assert {"supply", "quality", "delivery"} <= set(collectors.REMOTE)
    assert set(collectors.WEB) == {"latency"}


# ── قاعدة البيانات ────────────────────────────────────────────────────────────


def test_database_level_rules():
    assert database.connections_level(10, 100) == contract.OK
    assert database.connections_level(70, 100) == contract.WARN
    assert database.connections_level(90, 100) == contract.BAD
    assert database.connections_level(1, 0) == contract.OK
    assert database.query_level(5) == contract.OK
    assert database.query_level(31) == contract.WARN
    assert database.query_level(121) == contract.BAD


def test_the_database_panel_reads_the_real_database():
    database.collect(NOW)
    panel = _panel("database")
    assert panel["status"] in contract.STATUSES and isinstance(panel["gauge"], int)
    labels = [m["label"] for m in panel["metrics"]]
    assert labels == ["الحجم", "الاتّصالات", "أطولُ استعلامٍ نشط"]
    assert "MB" in panel["metrics"][0]["value"] or "GB" in panel["metrics"][0]["value"]


def test_growth_needs_a_sample_from_seven_days_ago():
    assert database._growth(1000, NOW) == "—"
    cache.set(database.SIZE_KEY.format(day=int(NOW // DAY) - 7), 800)
    assert database._growth(1000, NOW) == "+25.0%"


def test_a_non_postgres_database_fails_the_panel_instead_of_inventing_numbers(monkeypatch):
    monkeypatch.setattr(connection, "vendor", "sqlite")
    database.collect(NOW)
    panel = _panel("database")
    assert panel["status"] == contract.UNKNOWN and panel["err"] == "not_postgres"


def test_no_query_text_reaches_the_cache():
    database.collect(NOW)
    assert "SELECT" not in str(_panel("database"))


# ── الأداء والأخطاء (الويب) ───────────────────────────────────────────────────


def test_p95_is_the_upper_edge_of_the_bucket_holding_the_95th_percentile():
    buckets = {0.1: 50, 0.5: 90, 1.0: 96, 5.0: 100, float("inf"): 100}
    assert webstats.p95(buckets) == 1.0
    assert webstats.p95({}) is None
    assert webstats.p95({0.1: 0, float("inf"): 0}) is None


def test_web_levels_need_a_sample_and_judge_latency_and_errors():
    assert webstats.levels(0.3, 50, 0) == [contract.WARN]  # عيّنةٌ قليلة
    assert webstats.levels(0.3, 1000, 0) == [contract.OK, contract.OK]
    assert webstats.levels(3.0, 1000, 0)[0] == contract.WARN
    assert webstats.levels(6.0, 1000, 0)[0] == contract.BAD
    assert webstats.levels(0.3, 1000, 10)[1] == contract.WARN  # 1%
    assert webstats.levels(0.3, 1000, 50)[1] == contract.BAD  # 5%
    assert webstats.levels(float("inf"), 1000, 0)[0] == contract.BAD


def test_a_thin_web_sample_is_amber_with_no_gauge(monkeypatch):
    monkeypatch.setattr(webstats, "read_registry", lambda: ({0.1: 10, float("inf"): 10}, 10, 0))
    webstats.sample()
    panel = _panel("latency")
    assert panel["status"] == contract.WARN and panel["gauge"] is None
    assert "عيّنةٌ قليلةٌ" in panel["headline"]


def test_healthy_and_failing_web_samples(monkeypatch):
    healthy = ({0.1: 900, 0.5: 990, float("inf"): 1000}, 1000, 2)
    monkeypatch.setattr(webstats, "read_registry", lambda: healthy)
    webstats.sample()
    assert _panel("latency")["status"] == contract.OK
    sick = ({0.1: 100, 5.0: 500, 10.0: 1000, float("inf"): 1000}, 1000, 80)
    monkeypatch.setattr(webstats, "read_registry", lambda: sick)
    webstats.sample()
    panel = _panel("latency")
    assert panel["status"] == contract.BAD and panel["gauge"] == 30


def test_the_registry_reader_sums_the_prometheus_families(client_as, teacher_user):
    """الاسمان حقيقيّان: بعد طلباتٍ فعليّةٍ تظهر عدّاداتُ django_prometheus في سجلّ العمليّة."""
    client = client_as(teacher_user)
    for _ in range(3):
        client.get("/health/")
    buckets, total, errors = webstats.read_registry()
    assert total >= 3 and buckets and max(buckets) == float("inf") and errors >= 0


def test_the_web_sample_is_locked_thirty_seconds_and_never_raises(monkeypatch, settings):
    settings.QCC_LAZY_REFRESH = True
    calls = []
    monkeypatch.setattr(webstats, "sample", lambda: calls.append(1))
    assert webstats.sample_safe(NOW) is True
    assert webstats.sample_safe(NOW + 1) is False and calls == [1]
    cache.clear()
    monkeypatch.setattr(webstats, "sample", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert webstats.sample_safe(NOW) is False


def test_opening_the_page_takes_a_web_sample(client_as, developer_user, monkeypatch, settings):
    settings.QCC_LAZY_REFRESH = True
    calls = []
    monkeypatch.setattr(webstats, "sample", lambda: calls.append(1))
    client_as(developer_user).get("/command-center/")
    assert calls == [1]


# ── إيقاع النشر ───────────────────────────────────────────────────────────────


def test_delivery_summaries_keep_only_timestamps():
    deploys = delivery.reduce_deploys(
        [
            {"created_at": _iso(3600), "sha": "abc", "creator": {"login": "someone"}},
            {"created_at": _iso(DAY)},
        ]
    )
    assert set(deploys) == {"stamps"} and len(deploys["stamps"]) == 2
    runs = delivery.reduce_rollbacks(
        {
            "workflow_runs": [
                {"created_at": _iso(DAY), "conclusion": "success"},
                {"created_at": _iso(2 * DAY), "conclusion": "failure"},
            ]
        }
    )
    assert len(runs["stamps"]) == 1
    assert delivery.reduce_deploys({"x": 1}) is None and delivery.reduce_rollbacks([]) is None


def test_delivery_levels():
    assert delivery.levels(1, 0) == [contract.OK, contract.OK]
    assert delivery.levels(8, 0)[0] == contract.WARN
    assert delivery.levels(None, 0)[0] == contract.WARN
    assert delivery.levels(1, 1)[1] == contract.WARN
    assert delivery.levels(1, 2)[1] == contract.BAD


def _fake_fetch(monkeypatch, deploys, rollbacks):
    def fetch(path, reduce):
        return deploys if path.startswith("deployments") else rollbacks

    monkeypatch.setattr(github, "fetch", fetch)


def test_delivery_panel_regular_cadence_is_green(monkeypatch):
    _fake_fetch(monkeypatch, {"stamps": [NOW - 3600, NOW - DAY, NOW - 2 * DAY]}, {"stamps": []})
    delivery.collect(NOW)
    panel = _panel("delivery")
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert {"label": "نشراتُ آخر 7 أيّام", "value": "3"} in panel["metrics"]


def test_two_rollbacks_in_a_week_are_red(monkeypatch):
    _fake_fetch(monkeypatch, {"stamps": [NOW - 3600]}, {"stamps": [NOW - DAY, NOW - 2 * DAY]})
    delivery.collect(NOW)
    panel = _panel("delivery")
    assert panel["status"] == contract.BAD and panel["headline"] == "2 تراجعاً في آخر 7 أيّام"


def test_a_stale_delivery_is_amber_and_a_github_failure_keeps_the_last_value(monkeypatch):
    _fake_fetch(monkeypatch, {"stamps": [NOW - 9 * DAY]}, {"stamps": []})
    delivery.collect(NOW)
    assert _panel("delivery")["status"] == contract.WARN
    monkeypatch.setattr(github, "fetch", lambda path, reduce: None)
    delivery.collect(NOW)
    panel = _panel("delivery")
    assert panel["ok"] is False and panel["err"] == "github"


# ── جودة الاختبارات ───────────────────────────────────────────────────────────


def _run(conclusion="success", attempt=1, event="push", minutes=10):
    return {
        "conclusion": conclusion,
        "run_attempt": attempt,
        "event": event,
        "run_started_at": _iso(minutes * 60 + 60),
        "updated_at": _iso(60),
    }


def test_quality_summary_counts_reruns_pr_failures_and_the_median_duration():
    summary = quality.reduce(
        {
            "workflow_runs": [
                _run(),
                _run(attempt=2),
                _run("failure", event="pull_request"),
                _run(event="pull_request", minutes=20),
                _run("cancelled"),
            ]
        }
    )
    assert summary["total"] == 4 and summary["reruns"] == 1
    assert summary["pr_total"] == 2 and summary["pr_failed"] == 1
    assert summary["median_seconds"] in (600, 1200)
    assert quality.reduce([]) is None


def test_quality_levels():
    ok = {"total": 20, "reruns": 1, "pr_total": 10, "pr_failed": 1, "median_seconds": 600}
    assert quality.levels(ok) == [contract.OK] * 3
    assert quality.levels({**ok, "reruns": 4})[0] == contract.WARN  # 20%
    assert quality.levels({**ok, "reruns": 8})[0] == contract.BAD  # 40%
    assert quality.levels({**ok, "pr_failed": 5})[1] == contract.WARN
    assert quality.levels({**ok, "median_seconds": 31 * 60})[2] == contract.WARN


def test_quality_panel_with_enough_runs_and_with_too_few(monkeypatch):
    good = {"total": 20, "reruns": 1, "pr_total": 10, "pr_failed": 1, "median_seconds": 540}
    monkeypatch.setattr(github, "fetch", lambda path, reduce: good)
    quality.collect()
    panel = _panel("quality")
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert {"label": "إعادةُ التشغيل (تذبذب)", "value": "5%"} in panel["metrics"]
    monkeypatch.setattr(github, "fetch", lambda path, reduce: {**good, "total": 4})
    quality.collect()
    assert _panel("quality")["gauge"] is None


# ── الفحص الأمنيّ والاعتماديّات ───────────────────────────────────────────────


def test_supply_scan_summary_and_levels():
    scan = supply.reduce_scan(
        {
            "workflow_runs": [
                {"conclusion": "failure", "updated_at": _iso(3600)},
                {"conclusion": "success", "updated_at": _iso(DAY)},
            ]
        }
    )
    assert scan["ok"] is False
    assert supply.scan_level(scan, NOW) == contract.WARN
    assert supply.scan_level({"at": NOW - 25 * 3600, "ok": False}, NOW) == contract.BAD
    assert supply.scan_level({"at": NOW - 3 * DAY, "ok": True}, NOW) == contract.OK
    assert supply.scan_level({"at": NOW - 10 * DAY, "ok": True}, NOW) == contract.WARN
    assert supply.scan_level({"at": NOW - 17 * DAY, "ok": True}, NOW) == contract.BAD
    assert supply.scan_level({"at": None, "ok": None}, NOW) == contract.WARN


def test_supply_alert_counts_keep_no_package_or_description():
    alerts = supply.reduce_alerts(
        [
            {
                "security_advisory": {"severity": "critical", "summary": "وصفٌ", "cve_id": "CVE-1"},
                "dependency": {"package": {"name": "pkg"}},
            },
            {"security_advisory": {"severity": "high"}},
            {"security_advisory": {"severity": "high"}},
        ]
    )
    assert alerts == {"critical": 1, "high": 2, "medium": 0, "low": 0}
    assert supply.alerts_level(alerts) == contract.BAD
    assert supply.alerts_level({"critical": 0, "high": 1, "medium": 0, "low": 0}) == contract.WARN


def test_without_a_token_alerts_are_not_shown_as_zero(monkeypatch, settings):
    settings.QCC_GITHUB_TOKEN = ""
    monkeypatch.setattr(github, "fetch", lambda path, reduce: {"at": NOW - DAY, "ok": True})
    supply.collect(NOW)
    panel = _panel("supply")
    assert panel["status"] == contract.OK
    assert {"label": "تنبيهاتٌ حرجة / عالية", "value": "غيرُ مفعَّلة (بلا رمز)"} in panel["metrics"]


def test_with_a_token_a_critical_alert_makes_the_panel_red(monkeypatch, settings):
    settings.QCC_GITHUB_TOKEN = "test-token-not-real"

    def fetch(path, reduce):
        if path.startswith("dependabot"):
            return {"critical": 2, "high": 1, "medium": 0, "low": 0}
        return {"at": NOW - DAY, "ok": True}

    monkeypatch.setattr(github, "fetch", fetch)
    supply.collect(NOW)
    panel = _panel("supply")
    assert panel["status"] == contract.BAD and panel["headline"] == "2 تنبيهاً حرجاً في الاعتماديّات"


def test_the_token_is_sent_as_a_header_only_when_set_and_never_cached(monkeypatch, settings):
    seen = []

    class Reply:
        status_code = 200
        headers = {"ETag": '"e"'}

        @staticmethod
        def json():
            return [1]

    def fake_get(url, headers, timeout):
        seen.append(headers)
        return Reply()

    monkeypatch.setattr(requests, "get", fake_get)
    settings.QCC_GITHUB_TOKEN = ""
    github.fetch("p1", lambda payload: {"n": len(payload)})
    settings.QCC_GITHUB_TOKEN = "secret-token-value"
    github.fetch("p2", lambda payload: {"n": len(payload)})
    assert "Authorization" not in seen[0]
    assert seen[1]["Authorization"] == "Bearer secret-token-value"
    assert "secret-token-value" not in str(cache.get(github.cache_key("p2")))


def test_the_web_sample_is_off_when_lazy_refresh_is_off(monkeypatch, settings):
    settings.QCC_LAZY_REFRESH = False
    monkeypatch.setattr(webstats, "sample", lambda: pytest.fail("لا عيّنة"))
    assert webstats.sample_safe(NOW) is False
