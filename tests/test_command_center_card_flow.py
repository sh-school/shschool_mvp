"""[QCC] لوحةُ «مسارُ البطاقات» (W-20261020-012): الخطُّ الزمنيّ وعتباتُ المراحل الخمس وعدمُ تكرار التنبيه وغيابُ المصدر."""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache

from command_center import contract
from command_center.collectors import card_flow, github

NOW = 1_800_000_000.0
MIN = 60


def _card(card_id: str, **ages_min: float) -> dict:
    """بطاقةٌ بلغت المراحلَ المسمّاة قبل كذا دقيقة (الأحدثُ فيها هو المرحلةُ الجاريةُ)."""
    return {"id": card_id, "stamps": {k: NOW - v * MIN for k, v in ages_min.items()}}


def _panel(key: str = "card_flow") -> dict:
    return next(p for p in contract.read_panels(time.time()) if p["key"] == key)


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


class TestStages:
    def test_the_current_stage_is_the_last_one_reached_in_order(self):
        assert card_flow.current_stage({"ready": 1, "approved": 2}) == "approved"
        assert card_flow.current_stage({"ready": 1, "pushed": 3}) == "ready"  # قفزةٌ لا تُعدّ
        assert card_flow.current_stage({}) is None

    def test_a_published_card_has_no_running_stage(self):
        assert card_flow.current_stage(dict.fromkeys(card_flow.STAGES, 1.0)) is None


class TestThresholds:
    @pytest.mark.parametrize(
        ("stage", "limit_min"),
        [("ready", 240), ("approved", 30), ("pushed", 60), ("merged", 15)],
    )
    def test_each_threshold_stays_green_at_the_limit_and_turns_red_just_past_it(
        self, stage, limit_min
    ):
        reached = card_flow.STAGES[: card_flow.STAGES.index(stage) + 1]
        at_limit = _card("W-1", **dict.fromkeys(reached, limit_min))
        past = _card("W-2", **dict.fromkeys(reached, limit_min + 1))
        assert card_flow.breaches([at_limit], NOW) == []
        assert [(b["card"], b["stage"]) for b in card_flow.breaches([past], NOW)] == [
            ("W-2", stage)
        ]

    def test_the_worst_overrun_comes_first(self):
        found = card_flow.breaches([_card("W-A", ready=250), _card("W-B", ready=500)], NOW)
        assert [b["card"] for b in found] == ["W-B", "W-A"]

    def test_malformed_cards_are_skipped_not_raised(self):
        assert (
            card_flow.breaches([{"id": 5}, {"stamps": {}}, {"id": "W-1", "stamps": "x"}], NOW) == []
        )


class TestSnapshotReading:
    def test_a_ledger_snapshot_becomes_ids_and_seconds_only(self):
        out = card_flow.reduce_snapshot(
            {
                "schema": 1,
                "generated_at": "2026-10-20T14:00:00+00:00",
                "cards": [
                    {
                        "id": "W-1",
                        "state": "approved",
                        "head": "abcd1234",
                        "stages": {
                            "ready_for_review": "2026-10-20T13:00:00+00:00",
                            "approved": "2026-10-20T13:30:00+00:00",
                            "captured": "2026-10-19T00:00:00+00:00",
                        },
                    }
                ],
            }
        )
        assert out is not None
        assert out["generated_at"] == 1_792_504_800.0
        assert out["cards"] == [
            {"id": "W-1", "stamps": {"ready": 1_792_501_200.0, "approved": 1_792_503_000.0}}
        ]

    @pytest.mark.parametrize("bad", [None, [], {"cards": []}, {"generated_at": 5, "cards": []}])
    def test_an_unreadable_snapshot_is_none(self, bad):
        assert card_flow.reduce_snapshot(bad) is None


@pytest.mark.django_db
class TestCollect:
    def test_a_late_card_turns_the_panel_red(self):
        card_flow.collect(
            now=NOW, snapshot={"generated_at": NOW, "cards": [_card("W-1", ready=300)]}
        )
        assert _panel()["status"] == contract.BAD

    def test_all_within_limits_is_green(self):
        card_flow.collect(
            now=NOW, snapshot={"generated_at": NOW, "cards": [_card("W-1", ready=10)]}
        )
        assert _panel()["status"] == contract.OK

    def test_a_missing_source_is_never_green(self, monkeypatch):
        monkeypatch.setattr(github, "fetch", lambda *a, **k: None)
        card_flow.collect(now=NOW)
        assert _panel()["status"] == contract.UNKNOWN

    def test_a_stale_snapshot_is_never_green(self):
        snap = {"generated_at": NOW - 3600, "cards": [_card("W-1", ready=10)]}
        card_flow.collect(now=NOW, snapshot=snap)
        assert _panel()["status"] != contract.OK

    def test_one_incident_alerts_once(self, monkeypatch):
        sent = []
        monkeypatch.setattr("command_center.alerts.notify", lambda *a, **k: sent.append(a[1]) or 1)
        for tick in range(3):
            moment = NOW + tick * 180
            snap = {"generated_at": moment, "cards": [_card("W-1", ready=300 + tick * 3)]}
            card_flow.collect(now=moment, snapshot=snap)
        assert len(sent) == 1

    def test_a_new_stage_for_the_same_card_is_a_new_incident(self, monkeypatch):
        sent = []
        monkeypatch.setattr("command_center.alerts.notify", lambda *a, **k: sent.append(a[1]) or 1)
        card_flow.collect(
            now=NOW, snapshot={"generated_at": NOW, "cards": [_card("W-1", ready=300)]}
        )
        later = {"generated_at": NOW, "cards": [_card("W-1", ready=400, approved=40)]}
        card_flow.collect(now=NOW, snapshot=later)
        assert len(sent) == 2


def test_the_panel_and_the_beat_task_are_registered():
    from shschool.celery import app

    assert "card_flow" in [p.key for p in contract.PANELS]
    entry = app.conf.beat_schedule["qcc-collect-card-flow"]
    assert entry["task"] == "command_center.collect_card_flow"
    assert entry["schedule"].minute == set(range(0, 60, 3))
