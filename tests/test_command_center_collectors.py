"""[COMMAND-CENTER] الجمعُ الآليّ ومؤشّراتُ القرص — مجمِّعاتُ اللوحات الخمس والجمعُ الذاتيّ وجدولةُ Beat.

الصفحةُ تقرأ الـcache وحدَه (`test_command_center.py`)؛ وهذا الملفُّ يحرس من يكتب فيه: كلُّ لوحةٍ لها مجمِّعٌ واحد، وعطلُ مصدرٍ لا يُخضِّر لوحتَه
ولا يُسقط غيرَها، وGitHub يُجلب شرطيّاً ولا يُخزَّن منه نصٌّ، والجمعُ الذاتيّ مرّةً لكلّ قفل، والمهمّتان في جدول Beat.
"""

import json
import time
from types import SimpleNamespace

import pytest
import requests
from django.core.cache import cache

from command_center import collectors, contract, refresh
from command_center.collectors import ci, github, guards, production, publish, pulls
from command_center.collectors import roadmap as roadmap_collector
from roadmap.models import DecisionStatus, ItemStatus, RoadmapDecision, RoadmapItem
from shschool.celery import app as celery_app

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _panel(key):
    return next(p for p in contract.read_panels() if p["key"] == key)


# ── عقدُ القرص والمؤشّرات ─────────────────────────────────────────────────────


def test_a_gauge_and_metrics_are_read_back_clamped_and_in_order():
    contract.store(
        "production",
        {
            "status": "ok",
            "gauge": 130,
            "m1_l": "العامل",
            "m1_v": "يعمل",
            "m3_l": "5xx",
            "m3_v": 2,
            "m2_l": "",
            "m2_v": "x",
        },
    )
    panel = _panel("production")
    assert panel["gauge"] == 100
    assert panel["metrics"] == [
        {"label": "العامل", "value": "يعمل"},
        {"label": "5xx", "value": "2"},
    ]


def test_a_missing_or_non_numeric_gauge_is_none_never_zero():
    contract.store("ci", {"status": "ok", "gauge": "high"})
    assert _panel("ci")["gauge"] is None
    contract.store("ci", {"status": "ok", "gauge": True})
    assert _panel("ci")["gauge"] is None
    assert _panel("roadmap")["gauge"] is None and _panel("roadmap")["metrics"] == []


def test_publish_trims_long_text_and_caps_metrics_at_four():
    publish.publish(
        "guards",
        status="ok",
        headline="ه" * 500,
        gauge=-5,
        metrics=[(f"l{i}", i) for i in range(9)],
    )
    panel = _panel("guards")
    assert len(panel["headline"]) == contract.MAX_STRING
    assert panel["gauge"] == 0
    assert len(panel["metrics"]) == contract.MAX_METRICS


def test_score_penalises_red_more_than_amber_and_never_goes_negative():
    assert publish.score([contract.OK] * 4) == 100
    assert publish.score([contract.WARN]) == 88
    assert publish.score([contract.BAD]) == 65
    assert publish.score([contract.BAD] * 5) == 0
    assert publish.worst([contract.OK, contract.WARN]) == contract.WARN
    assert publish.worst([contract.WARN, contract.BAD]) == contract.BAD


# ── السجلُّ والعزل ────────────────────────────────────────────────────────────


def test_every_panel_has_exactly_one_collector():
    grouped = [*collectors.LOCAL, *collectors.REMOTE]
    assert sorted(grouped) == sorted(p.key for p in contract.PANELS)
    assert len(grouped) == len(set(grouped))


def test_a_broken_collector_does_not_stop_the_others_or_raise():
    calls = []

    def bad():
        raise RuntimeError("boom")

    outcome = collectors.run({"a": bad, "b": lambda: calls.append("b")})
    assert outcome == {"a": False, "b": True} and calls == ["b"]


# ── الإنتاج ───────────────────────────────────────────────────────────────────


def _card(level, value="v", title="t"):
    return SimpleNamespace(level=level, value=value, title=title, detail="", url="")


def test_production_is_red_when_any_card_is_red_and_the_dial_drops(monkeypatch):
    monkeypatch.setattr(production, "CARDS", (lambda: _card("ok"), lambda: _card("bad")))
    monkeypatch.setattr(production, "pending_migrations", lambda: 0)
    production.collect()
    panel = _panel("production")
    assert panel["status"] == contract.BAD
    assert panel["gauge"] == 65
    assert "1 من 3" in panel["headline"]


def test_a_card_that_raises_counts_as_a_warning_not_as_healthy(monkeypatch):
    def broken():
        raise RuntimeError("card down")

    monkeypatch.setattr(production, "CARDS", (broken,))
    monkeypatch.setattr(production, "pending_migrations", lambda: 0)
    production.collect()
    assert _panel("production")["status"] == contract.WARN


def test_all_green_cards_give_a_full_dial(monkeypatch):
    monkeypatch.setattr(production, "CARDS", (lambda: _card("ok"),))
    monkeypatch.setattr(production, "pending_migrations", lambda: 0)
    production.collect()
    panel = _panel("production")
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert [m["label"] for m in panel["metrics"]][-1] == "هجراتٌ معلَّقة"


def test_pending_migrations_are_amber_then_red_after_ten_minutes():
    now = 1_000_000.0
    assert production.migrations_level(0, now) == contract.OK
    assert production.migrations_level(2, now) == contract.WARN
    assert production.migrations_level(2, now + 9 * 60) == contract.WARN
    assert production.migrations_level(2, now + 11 * 60) == contract.BAD
    assert production.migrations_level(0, now + 12 * 60) == contract.OK
    assert production.migrations_level(1, now + 13 * 60) == contract.WARN  # العدّادُ بدأ من جديد


def test_the_real_production_collector_runs_against_the_test_database():
    production.collect()
    panel = _panel("production")
    assert panel["status"] in contract.STATUSES
    assert isinstance(panel["gauge"], int) and len(panel["metrics"]) == 4


def test_the_production_collector_leaves_out_the_tenant_scoped_cards():
    """AuditLog وNotificationDelivery بسياسة RLS لكلّ مدرسة والمجمِّعُ بلا مدرسة — قراءةٌ صفريّةٌ كاذبة."""
    titles = {build.__name__ for build in production.CARDS}
    assert "security" not in titles and "notifications" not in titles


# ── الخارطة ───────────────────────────────────────────────────────────────────


def test_roadmap_dial_is_the_share_of_closed_items_out_of_the_non_deferred():
    for code, status in (
        ("T-1", ItemStatus.DONE),
        ("T-2", ItemStatus.DONE),
        ("T-3", ItemStatus.TODO),
        ("T-4", ItemStatus.DEFERRED),
    ):
        RoadmapItem.objects.create(code=code, lane="ops", title="x", status=status)
    roadmap_collector.collect()
    panel = _panel("roadmap")
    assert panel["gauge"] == 67 and panel["status"] == contract.OK
    assert panel["headline"] == "2 من 3 بنداً مُغلَق"


def test_a_blocked_item_or_an_open_decision_is_amber_and_never_red():
    RoadmapItem.objects.create(code="T-1", lane="ops", title="x", status=ItemStatus.BLOCKED)
    RoadmapDecision.objects.create(code="D-T1", title="x", status=DecisionStatus.OPEN)
    roadmap_collector.collect()
    panel = _panel("roadmap")
    assert panel["status"] == contract.WARN
    assert {"label": "قراراتٌ بانتظارك", "value": "1"} in panel["metrics"]


def test_an_empty_roadmap_has_no_dial_reading():
    roadmap_collector.collect()
    panel = _panel("roadmap")
    assert panel["status"] == contract.WARN and panel["gauge"] is None


# ── الحرّاس ───────────────────────────────────────────────────────────────────


def test_the_guards_panel_reads_the_real_budget_and_baselines():
    guards.collect()
    panel = _panel("guards")
    assert panel["status"] in contract.STATUSES
    assert "بايتاً" in panel["headline"]
    assert len(panel["metrics"]) == 3


def test_the_css_margin_thresholds():
    assert guards.margin_level(100) == contract.BAD
    assert guards.margin_level(1500) == contract.WARN
    assert guards.margin_level(5000) == contract.OK
    assert guards.margin_level(-10) == contract.BAD


def test_a_missing_tests_directory_fails_the_panel_instead_of_inventing_numbers(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    guards.collect()
    panel = _panel("guards")
    assert panel["status"] == contract.UNKNOWN and panel["err"] == "no_tests"


def test_the_budget_is_read_from_the_budget_test_not_duplicated(tmp_path):
    (tmp_path / "test_css_budget.py").write_text(
        "MAX_SHIPPED_BYTES = 300 * 1024\n", encoding="utf-8"
    )
    assert guards._budget_bytes(tmp_path) == 300 * 1024


# ── GitHub: شرطيٌّ ولا نصَّ من طرفٍ ثالث ──────────────────────────────────────


class _Reply:
    def __init__(self, status, body=None, etag=""):
        self.status_code = status
        self._body = body
        self.headers = {"ETag": etag} if etag else {}

    def json(self):
        return self._body


def test_a_200_reply_stores_only_the_summary_with_its_etag(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen["headers"] = headers
        return _Reply(200, [{"title": "عنوانٌ من طرفٍ ثالث", "draft": False}], etag='"abc"')

    monkeypatch.setattr(requests, "get", fake_get)
    summary = github.fetch("pulls?x", lambda payload: {"n": len(payload)})
    assert summary == {"n": 1}
    assert cache.get(github.cache_key("pulls?x")) == {"etag": '"abc"', "summary": {"n": 1}}
    assert "عنوانٌ من طرفٍ ثالث" not in json.dumps(
        cache.get(github.cache_key("pulls?x")), ensure_ascii=False
    )
    assert "If-None-Match" not in seen["headers"]


def test_a_304_reply_returns_the_saved_summary_and_sends_the_etag(monkeypatch):
    replies = iter([_Reply(200, [1, 2], etag='"e1"'), _Reply(304)])
    sent = []

    def fake_get(url, headers, timeout):
        sent.append(headers.get("If-None-Match"))
        return next(replies)

    monkeypatch.setattr(requests, "get", fake_get)
    reduce = lambda payload: {"n": len(payload)}  # noqa: E731
    assert github.fetch("p", reduce) == {"n": 2}
    assert github.fetch("p", reduce) == {"n": 2}
    assert sent == [None, '"e1"']


@pytest.mark.parametrize(
    "failure", [_Reply(403), _Reply(429), _Reply(500), requests.ConnectionError("down")]
)
def test_a_failed_fetch_is_none_so_the_last_good_value_stays(monkeypatch, failure):
    def fake_get(url, headers, timeout):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(requests, "get", fake_get)
    assert github.fetch("p", lambda payload: {"n": 1}) is None


def test_an_unreadable_reply_is_none(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, headers, timeout: _Reply(200, {"odd": 1}))
    assert github.fetch("p", lambda payload: None) is None


# ── CI ────────────────────────────────────────────────────────────────────────


def _runs(*results):
    return {
        "workflow_runs": [
            {"conclusion": r, "updated_at": f"2026-09-26T1{i}:00:00Z"}
            for i, r in enumerate(results)
        ]
    }


def test_ci_summary_counts_only_decided_runs_and_the_red_streak():
    summary = ci.reduce(_runs("failure", "failure", "success", "cancelled", "skipped", "success"))
    assert summary["total"] == 4 and summary["passed"] == 2
    assert summary["red_streak"] == 2 and summary["latest_ok"] is False


def test_ci_is_red_only_after_an_hour_of_continuous_red():
    now = time.time()
    fresh = {"total": 3, "passed": 2, "latest_at": now - 600, "latest_ok": False, "red_streak": 1}
    old = {**fresh, "latest_at": now - 7200}
    assert ci.level(fresh, now) == contract.WARN
    assert ci.level(old, now) == contract.BAD
    assert ci.level({**fresh, "latest_ok": True}, now) == contract.OK
    assert ci.level({**fresh, "total": 0}, now) == contract.WARN


def test_ci_collect_writes_the_dial_from_the_pass_rate(monkeypatch):
    now = time.time()
    summary = {"total": 10, "passed": 9, "latest_at": now, "latest_ok": True, "red_streak": 0}
    monkeypatch.setattr(github, "fetch", lambda path, reduce: summary)
    ci.collect(now)
    panel = _panel("ci")
    assert panel["status"] == contract.OK and panel["gauge"] == 90


def test_ci_collect_keeps_the_last_good_value_and_flags_it_when_github_fails(monkeypatch):
    now = time.time()
    good = {"total": 4, "passed": 4, "latest_at": now, "latest_ok": True, "red_streak": 0}
    monkeypatch.setattr(github, "fetch", lambda path, reduce: good)
    ci.collect(now)
    monkeypatch.setattr(github, "fetch", lambda path, reduce: None)
    ci.collect(now)
    panel = _panel("ci")
    assert panel["ok"] is False and panel["err"] == "github"
    assert panel["status"] == contract.WARN and panel["gauge"] == 100  # لا اخضرارَ بعد عطلٍ


# ── الطلبات ───────────────────────────────────────────────────────────────────


def test_open_pulls_summary_keeps_numbers_only():
    payload = [
        {
            "created_at": "2026-09-01T00:00:00Z",
            "draft": False,
            "title": "نصٌّ خارجيّ",
            "user": {"login": "someone"},
        },
        {"created_at": "2026-09-20T00:00:00Z", "draft": True},
    ]
    summary = pulls.reduce_open(payload)
    assert set(summary) == {"open", "drafts", "oldest"}
    assert summary["open"] == 2 and summary["drafts"] == 1


def test_a_sha_from_the_deployments_reply_must_be_hex_like():
    full_sha = "b5b485d" + "0" * 33  # 40 خانةً سداسيّةً
    assert pulls.reduce_deploy([{"sha": full_sha}])["sha"].startswith("b5b485d")
    assert pulls.reduce_deploy([{"sha": "../../evil"}])["sha"] == ""
    assert pulls.reduce_deploy([]) == {"sha": ""}
    assert pulls.reduce_compare({"ahead_by": 3}) == {"ahead": 3}
    assert pulls.reduce_compare({"ahead_by": "3"}) is None


def test_pulls_collect_combines_open_pulls_and_deploy_lag(monkeypatch):
    now = time.time()

    def fake(path, reduce):
        if path.startswith("pulls"):
            return {"open": 12, "drafts": 2, "oldest": now - 3 * 86400}
        if path.startswith("deployments"):
            return {"sha": "b5b485d2e5fb1505"}
        return {"ahead": 4}

    monkeypatch.setattr(github, "fetch", fake)
    pulls.collect(now)
    panel = _panel("pulls")
    assert panel["status"] == contract.OK
    assert panel["gauge"] == 100 - 12 - 4
    assert {"label": "إيداعاتٌ غيرُ منشورة", "value": "4"} in panel["metrics"]


def test_pulls_without_a_recorded_deployment_is_amber_with_no_dial(monkeypatch):
    now = time.time()
    monkeypatch.setattr(
        github,
        "fetch",
        lambda path, reduce: {"open": 1, "drafts": 0, "oldest": now}
        if path.startswith("pulls")
        else {"sha": ""},
    )
    pulls.collect(now)
    panel = _panel("pulls")
    assert panel["status"] == contract.WARN and panel["gauge"] is None


# ── الجمعُ الذاتيّ ────────────────────────────────────────────────────────────


@pytest.fixture
def lazy(settings, monkeypatch):
    settings.QCC_LAZY_REFRESH = True
    settings.CELERY_TASK_ALWAYS_EAGER = True
    launched = []
    monkeypatch.setattr(refresh, "_in_thread", launched.append)
    return launched


def test_stale_or_empty_panels_launch_each_group_once_per_lock(lazy):
    assert refresh.ensure_fresh() == ["local", "remote"]
    assert lazy == ["local", "remote"]
    assert refresh.ensure_fresh() == []  # القفلُ: لا يُطلَق ثانيةً في نصف دقيقة


def test_fresh_panels_launch_nothing(lazy):
    for panel in contract.PANELS:
        contract.store(panel.key, {"status": "ok"})
    assert refresh.ensure_fresh() == [] and lazy == []


def test_one_old_panel_relaunches_only_its_group(lazy):
    for panel in contract.PANELS:
        contract.store(panel.key, {"status": "ok"})
    old = time.time() + 3 * refresh.CADENCE["remote"]
    assert refresh.stale_groups(old) == ["local", "remote"]
    assert refresh.stale_groups(time.time() + 2 * refresh.CADENCE["local"] + 5) == ["local"]


def test_lazy_refresh_can_be_turned_off(settings, monkeypatch):
    settings.QCC_LAZY_REFRESH = False
    monkeypatch.setattr(refresh, "_in_thread", lambda group: pytest.fail("لا خيط"))
    assert refresh.ensure_fresh() == []


def test_with_a_real_worker_the_task_is_sent_and_a_dead_broker_falls_back_to_a_thread(
    settings, monkeypatch
):
    settings.QCC_LAZY_REFRESH = True
    settings.CELERY_TASK_ALWAYS_EAGER = False
    monkeypatch.setattr(refresh, "_worker_shares_our_cache", lambda: True)  # Redis مشترك
    sent, threaded = [], []
    monkeypatch.setattr(refresh, "_in_thread", threaded.append)
    fake = SimpleNamespace(delay=lambda: sent.append("delay"))
    monkeypatch.setitem(refresh.GROUPS, "local", (collectors.LOCAL, fake))
    refresh._dispatch("local")
    assert sent == ["delay"] and threaded == []

    def down():
        raise ConnectionError("broker")

    monkeypatch.setitem(refresh.GROUPS, "local", (collectors.LOCAL, SimpleNamespace(delay=down)))
    refresh._dispatch("local")
    assert threaded == ["local"]


@pytest.mark.parametrize(
    "backend",
    [
        "django.core.cache.backends.locmem.LocMemCache",
        "django.core.cache.backends.dummy.DummyCache",
    ],
)
def test_a_process_local_cache_collects_in_a_thread_because_the_worker_would_write_elsewhere(
    settings, monkeypatch, backend
):
    """LocMem لكلّ عمليّة: ما يكتبه العاملُ لا يراه الويب — فالإرسالُ إليه يترك اللوحاتِ «غيرَ معلومة» إلى الأبد."""
    settings.QCC_LAZY_REFRESH = True
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CACHES = {"default": {"BACKEND": backend}}
    threaded = []
    monkeypatch.setattr(refresh, "_in_thread", threaded.append)
    monkeypatch.setitem(
        refresh.GROUPS,
        "local",
        (
            collectors.LOCAL,
            SimpleNamespace(delay=lambda: pytest.fail("لا إرسالَ إلى عاملٍ لا يشاركنا الـcache")),
        ),
    )
    refresh._dispatch("local")
    assert threaded == ["local"]


def test_an_error_inside_lazy_refresh_never_reaches_the_page(lazy, monkeypatch):
    monkeypatch.setattr(
        refresh, "stale_groups", lambda now=None: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert refresh.ensure_fresh() == []


def test_the_page_asks_for_a_refresh_when_it_is_stale(
    client_as, developer_user, settings, monkeypatch
):
    settings.QCC_LAZY_REFRESH = True
    settings.CELERY_TASK_ALWAYS_EAGER = True
    launched = []
    monkeypatch.setattr(refresh, "_in_thread", launched.append)
    assert client_as(developer_user).get("/command-center/snapshot/").status_code == 200
    assert launched == ["local", "remote"]


# ── الجدولةُ الآليّة ──────────────────────────────────────────────────────────


def test_both_collection_tasks_are_scheduled_and_registered():
    celery_app.loader.import_default_modules()
    schedule = {e["task"]: e["schedule"] for e in celery_app.conf.beat_schedule.values()}
    assert (
        "command_center.collect_local" in schedule and "command_center.collect_remote" in schedule
    )
    assert "command_center.collect_local" in celery_app.tasks
    assert "command_center.collect_remote" in celery_app.tasks
    assert len(schedule["command_center.collect_local"].minute) == 60  # كلَّ دقيقة = CADENCE["local"]
    assert sorted(schedule["command_center.collect_remote"].minute) == list(
        range(0, 60, 4)
    )  # كلَّ أربع = CADENCE["remote"]
    assert refresh.CADENCE == {"local": 60, "remote": 240}


def test_the_collection_tasks_run_and_report_per_panel(monkeypatch):
    from command_center import tasks

    monkeypatch.setattr(collectors, "LOCAL", {"production": lambda: None})
    assert tasks.collect_local() == {"production": True}
