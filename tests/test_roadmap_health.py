"""[ROADMAP] صحّةُ الخارطة: عمرُ القرار ومغلقٌ بلا مرجع ولقطةُ الدفتر وحارسُ الانحراف والمسرد (W-20261009-026).

كلُّها قراءةٌ بلا هجرة. العيّنةُ مصطنعةٌ صغيرة (لا بياناتَ الخارطة ولا الدفترَ الحقيقيّين).
"""

from __future__ import annotations

import io
import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from roadmap import health, ledger_health
from roadmap.models import DecisionStatus, RoadmapDecision, RoadmapItem, RoadmapMeta
from roadmap.services import page_context

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 10)
ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "js" / "roadmap.js").read_text(encoding="utf-8")


def _item(code: str, **fields) -> RoadmapItem:
    values = {"lane": "sec", "title": f"بند {code}", "status": "todo", "src": "U", **fields}
    return RoadmapItem.objects.create(code=code, **values)


def _decision(code: str, days_old: int, status: str = DecisionStatus.OPEN) -> RoadmapDecision:
    row = RoadmapDecision.objects.create(code=code, title=f"قرار {code}", status=status)
    stamp = datetime(2026, 10, 10, 12, tzinfo=UTC) - timedelta(days=days_old)
    RoadmapDecision.objects.filter(pk=row.pk).update(
        created_at=stamp
    )  # auto_now_add لا يُمرَّر عند الإنشاء
    return RoadmapDecision.objects.get(pk=row.pk)


# ── مغلقٌ بلا مرجع ────────────────────────────────────────────────────────


class TestClosedWithoutReference:
    def test_a_pr_number_or_a_documented_note_is_evidence(self):
        with_pr = _item("A-1", status="done", pr="#912")
        with_note = _item("A-2", status="done", note="تحقّق: الطلب #913 دُمج")
        with_decision = _item("A-3", status="done", note="بقرار D-155م")
        with_card = _item("A-4", status="done", note="W-20261009-026")
        with_kpi = _item("A-5", status="done", note="تحرّك UK12 إلى 3")
        assert all(
            health.has_closing_evidence(o)
            for o in (with_pr, with_note, with_decision, with_card, with_kpi)
        )

    def test_ref_is_the_plan_source_not_evidence(self):
        bare = _item("B-1", status="done", ref="الخطّة الموحّدة §3")
        assert not health.has_closing_evidence(bare)

    def test_only_closed_items_without_evidence_are_listed(self):
        _item("C-1", status="done")
        _item("C-2", status="done", pr="#5000")
        _item("C-3", status="doing")
        _item("C-4", status="deferred")
        red, archived = health.closed_without_reference(RoadmapItem.objects.all())
        assert [o.code for o in red] == ["C-1"] and archived == 0

    def test_archive_items_are_counted_apart_not_listed(self):
        _item("D-1", status="done", src="DONE")
        _item("D-2", status="done", src="U")
        red, archived = health.closed_without_reference(RoadmapItem.objects.all())
        assert [o.code for o in red] == ["D-2"] and archived == 1

    def test_a_stray_number_without_hash_is_not_evidence(self):
        assert not health.has_closing_evidence(_item("E-1", status="done", note="مرّ 5 أيّام وانتهى"))


# ── عمر القرار ────────────────────────────────────────────────────────────


class TestDecisionAge:
    def test_only_open_decisions_have_an_age_in_days(self):
        _decision("DX-1", 8)
        _decision("DX-2", 0)
        _decision("DX-3", 30, status=DecisionStatus.DECIDED)
        ages = health.open_decision_ages(RoadmapDecision.objects.all(), TODAY)
        assert ages == {"DX-1": 8, "DX-2": 0}

    def test_a_future_stamp_is_zero_not_negative(self):
        row = _decision("DX-4", 0)
        assert health.open_decision_ages([row], TODAY - timedelta(days=3)) == {"DX-4": 0}

    def test_the_threshold_is_seven_days(self):
        assert health.DECISION_STALE_DAYS == 7
        assert "7" in health.GLOSSARY["decision_age"][1]


# ── لقطةُ الدفتر ──────────────────────────────────────────────────────────


def _snapshot(**over):
    base = {
        "asOf": "2026-10-10",
        "total": 10,
        "routed": 4,
        "routedNoHolder": 2,
        "routedOldestDays": 6,
        "byState": {"routed": {"n": 4, "oldestDays": 6}},
        "drift": {"prsWithoutItem": 1, "itemsWithUnknownCard": 0},
    }
    return {"ledger": {**base, **over}}


class TestLedgerSnapshot:
    def test_absent_is_unmeasured_not_zero(self):
        assert health.ledger_snapshot({}, TODAY) is None
        assert health.ledger_snapshot({"ledger": "x"}, TODAY) is None

    def test_a_valid_snapshot_is_read_with_its_age(self):
        snap = health.ledger_snapshot(_snapshot(), TODAY)
        assert snap["routedNoHolder"] == 2 and snap["ageDays"] == 0 and snap["stale"] is False
        assert snap["drift"] == {"prsWithoutItem": 1, "itemsWithUnknownCard": 0}

    def test_an_old_snapshot_is_flagged_stale(self):
        snap = health.ledger_snapshot(_snapshot(asOf="2026-10-01"), TODAY)
        assert snap["stale"] is True and snap["ageDays"] == 9

    @pytest.mark.parametrize(
        "bad",
        [
            {"routed": "4"},
            {"routedNoHolder": None},
            {"total": True},
            {"asOf": "أمس"},
            {"asOf": None},
        ],
    )
    def test_a_malformed_field_drops_the_whole_snapshot(self, bad):
        assert health.ledger_snapshot(_snapshot(**bad), TODAY) is None


# ── الاشتقاق من أحداث الدفتر ──────────────────────────────────────────────


def _ev(ts, card, kind, **data):
    return {"ts": ts, "id": card, "kind": kind, "data": data}


EVENTS = [
    _ev("2026-10-01T09:00:00+03:00", "W-1", "created", problem="x"),
    _ev("2026-10-02T09:00:00+03:00", "W-1", "state", state="routed", held_by="0702"),
    _ev("2026-10-03T09:00:00+03:00", "W-2", "created"),
    _ev("2026-10-04T09:00:00+03:00", "W-2", "state", state="routed"),
    _ev("2026-10-05T09:00:00+03:00", "W-3", "created"),
    _ev("2026-10-06T09:00:00+03:00", "W-3", "state", state="merged"),
    _ev("2026-10-06T09:30:00+03:00", "W-3", "note", text="دُمج بالطلب 934"),
    _ev("2026-10-07T09:00:00+03:00", "W-4", "created"),
    _ev("2026-10-07T09:10:00+03:00", "W-4", "state", state="published"),
    _ev("2026-10-07T09:20:00+03:00", "W-4", "note", text="OR-01"),
    _ev("2026-10-08T09:00:00+03:00", "W-9", "state", state="routed"),  # حدثٌ ليتيمٍ بلا created: يُهمَل
]


class TestLedgerReduce:
    def test_state_holder_and_notes_are_derived(self):
        cards = ledger_health.reduce_cards(EVENTS)
        assert set(cards) == {"W-1", "W-2", "W-3", "W-4"}
        assert cards["W-1"]["state"] == "routed" and cards["W-1"]["held_by"] == "0702"
        assert cards["W-2"]["held_by"] == "" and cards["W-3"]["notes"] == ["دُمج بالطلب 934"]

    def test_summary_counts_routed_without_holder_and_ages(self):
        summary = ledger_health.ledger_summary(ledger_health.reduce_cards(EVENTS), TODAY)
        assert summary["total"] == 4 and summary["routed"] == 2 and summary["routedNoHolder"] == 1
        assert summary["routedOldestDays"] == 8  # W-1 دخلت routed في 10-02
        assert summary["byState"]["routed"] == {"n": 2, "oldestDays": 8}
        assert summary["asOf"] == "2026-10-10"

    def test_the_summary_is_accepted_by_the_page_reader(self):
        summary = ledger_health.ledger_summary(ledger_health.reduce_cards(EVENTS), TODAY)
        assert health.ledger_snapshot({"ledger": summary}, TODAY) is not None

    def test_read_events_rejects_a_corrupt_line(self, tmp_path):
        bad = tmp_path / "e.jsonl"
        bad.write_text(json.dumps(EVENTS[0], ensure_ascii=False) + "\n{oops\n", encoding="utf-8")
        with pytest.raises(ValueError, match="السطر 2"):
            ledger_health.read_events(bad)

    def test_read_events_rejects_a_line_missing_fields(self, tmp_path):
        bad = tmp_path / "e.jsonl"
        bad.write_text('{"ts": "x"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="ينقصه"):
            ledger_health.read_events(bad)

    @pytest.mark.skipif(
        not Path(os.environ.get("LEDGER_TOOLS", "C:/Users/mesue/delivery_manager_work/tools"))
        .joinpath("ledger.py")
        .is_file(),
        reason="أداةُ الدفتر خارج المستودع (اختبارُ عقدٍ للمضيف)",
    )
    def test_matches_the_real_ledger_tool_on_state_and_holder(self):
        import importlib.util

        tools = Path(os.environ.get("LEDGER_TOOLS", "C:/Users/mesue/delivery_manager_work/tools"))
        spec = importlib.util.spec_from_file_location("ledger_tool", tools / "ledger.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        real = tool.reduce_state(EVENTS)
        mine = ledger_health.reduce_cards(EVENTS)
        for card_id, card in mine.items():
            assert card["state"] == real[card_id]["state"], card_id
            assert (card["held_by"] or "") == (real[card_id].get("held_by") or ""), card_id
            assert card["state_ts"] == real[card_id]["state_ts"], card_id


# ── الانحراف ──────────────────────────────────────────────────────────────


class TestDrift:
    def test_a_merged_pr_no_item_mentions_is_reported(self):
        _item("F-1", status="done", pr="#934")
        report = ledger_health.drift_report(
            ledger_health.reduce_cards(EVENTS), list(RoadmapItem.objects.all())
        )
        assert report["prsWithoutItem"] == []

        RoadmapItem.objects.all().delete()
        report = ledger_health.drift_report(
            ledger_health.reduce_cards(EVENTS), list(RoadmapItem.objects.all())
        )
        assert report["prsWithoutItem"] == [{"pr": 934, "card": "W-3"}]

    def test_a_merged_card_without_a_pr_number_is_listed_not_guessed(self):
        report = ledger_health.drift_report(ledger_health.reduce_cards(EVENTS), [])
        assert report["mergedWithoutPr"] == ["W-4"]

    def test_unmerged_cards_are_not_expected_in_the_roadmap(self):
        report = ledger_health.drift_report(ledger_health.reduce_cards(EVENTS[:2]), [])
        assert report["prsWithoutItem"] == [] and report["mergedWithoutPr"] == []

    def test_an_item_citing_an_unknown_card_is_reported(self):
        _item("G-1", note="سببه W-20261001-001 وW-1")
        report = ledger_health.drift_report(
            ledger_health.reduce_cards(EVENTS), list(RoadmapItem.objects.all())
        )
        assert report["itemsWithUnknownCard"] == [{"item": "G-1", "card": "W-20261001-001"}]

    def test_closed_without_reference_is_part_of_the_report(self):
        _item("H-1", status="done")
        report = ledger_health.drift_report({}, list(RoadmapItem.objects.all()))
        assert report["closedWithoutReference"] == ["H-1"]

    def test_counts_collapse_each_category_to_a_number(self):
        report = {
            "prsWithoutItem": [1, 2],
            "mergedWithoutPr": [],
            "closedWithoutReference": [3],
            "itemsWithUnknownCard": [],
        }
        assert ledger_health.drift_counts(report) == {
            "prsWithoutItem": 2,
            "mergedWithoutPr": 0,
            "closedWithoutReference": 1,
            "itemsWithUnknownCard": 0,
        }


# ── الأمر ─────────────────────────────────────────────────────────────────


@pytest.fixture
def ledger_file(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in EVENTS) + "\n", encoding="utf-8"
    )
    return path


class TestCommand:
    def test_the_report_names_each_category_and_writes_nothing(self, ledger_file):
        _item("I-1", status="done")
        meta_before = RoadmapMeta.objects.count()
        out = io.StringIO()
        call_command("roadmap_drift", ledger=str(ledger_file), stdout=out)
        text = out.getvalue()
        assert "routed 2 منها 1 بلا حامل" in text and "#934  ← W-3" in text and "I-1" in text
        assert RoadmapMeta.objects.count() == meta_before
        assert ledger_file.read_text(encoding="utf-8").count("\n") == len(EVENTS)

    def test_json_is_a_snapshot_the_page_accepts(self, ledger_file):
        out = io.StringIO()
        call_command("roadmap_drift", ledger=str(ledger_file), as_json=True, stdout=out)
        payload = json.loads(out.getvalue())
        snap = health.ledger_snapshot(payload, date.fromisoformat(payload["ledger"]["asOf"]))
        assert snap is not None and snap["routedNoHolder"] == 1
        assert set(payload["ledger"]["drift"]) == {
            "prsWithoutItem",
            "mergedWithoutPr",
            "closedWithoutReference",
            "itemsWithUnknownCard",
        }

    def test_the_limit_truncates_a_long_list(self, ledger_file):
        for n in range(5):
            _item(f"J-{n}", status="done")
        out = io.StringIO()
        call_command("roadmap_drift", ledger=str(ledger_file), limit=2, stdout=out)
        assert "و3 أخرى" in out.getvalue()

    def test_a_missing_path_or_file_is_a_clear_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LEDGER_PATH", raising=False)
        with pytest.raises(CommandError, match="لم يُحدَّد"):
            call_command("roadmap_drift")
        with pytest.raises(CommandError, match="لا ملفَّ"):
            call_command("roadmap_drift", ledger=str(tmp_path / "nope.jsonl"))

    def test_a_corrupt_ledger_fails_loudly(self, tmp_path):
        bad = tmp_path / "bad.jsonl"
        bad.write_text("{oops\n", encoding="utf-8")
        with pytest.raises(CommandError, match="تعذّرت"):
            call_command("roadmap_drift", ledger=str(bad))


# ── الصفحة والمسرد ────────────────────────────────────────────────────────


class TestPage:
    def test_the_payload_carries_health_and_the_glossary(self):
        _item("K-1", status="done")
        _decision("DK-1", 9)
        data = page_context()["roadmap_data"]
        assert data["health"]["closedNoRef"] == ["K-1"]
        assert data["health"]["decisionAges"]["DK-1"] >= 8
        assert data["health"]["ledger"] is None
        assert data["glossary"]["done"]["meaning"]

    def test_a_ledger_snapshot_in_the_document_reaches_the_page(self):
        # تاريخٌ بعيدٌ: العمرُ سالبٌ فيُقصّ إلى 0 والقياسُ حيٌّ، بلا قراءة ساعةٍ في الاختبار (سقّاطةُ تثبيت الساعة)
        RoadmapMeta.objects.create(key=RoadmapMeta.KEY, data=_snapshot(asOf="2999-01-01"))
        ledger = page_context()["roadmap_data"]["health"]["ledger"]
        assert ledger["routedNoHolder"] == 2 and ledger["stale"] is False

    def test_the_rendered_page_embeds_health(self, client_as, developer_user):
        response = client_as(developer_user).get(reverse("improvement_roadmap"))
        assert response.status_code == 200
        assert '"health"' in response.content.decode() and '"glossary"' in response.content.decode()


class TestGlossaryAgreesWithTheScript:
    def test_every_literal_tip_key_exists(self):
        used = set(re.findall(r"tip\('([a-z_]+)'\)", JS)) | set(re.findall(r"tip: '([a-z_]+)'", JS))
        assert used and used <= set(health.GLOSSARY), used - set(health.GLOSSARY)

    def test_every_glossary_key_is_used_by_the_script(self):
        literals = set(re.findall(r"'([a-z]+(?:_[a-z]+)*)'", JS))
        composed = {f"st_{s}" for s in ("todo", "doing", "done", "blocked", "deferred")} | {
            f"dc_{s}" for s in ("open", "decided", "deferred")
        }
        for key in health.GLOSSARY:
            assert key in literals or key in composed, f"مفتاحٌ في المسرد لا تستعمله الواجهة: {key}"
        # المركّبةُ لا تُحسب مستعملةً إلا إن ركّبها السكربت فعلاً
        assert "'st_' + it.status" in JS and "'dc_' + d.status" in JS

    def test_every_meaning_is_a_real_sentence(self):
        for key, (name, meaning) in health.GLOSSARY.items():
            assert name.strip() and len(meaning) >= 12, key

    def test_statuses_in_the_script_match_the_models(self):
        from roadmap.models import DecisionStatus, ItemStatus

        assert {f"st_{v}" for v in ItemStatus.values} <= set(health.GLOSSARY)
        assert {f"dc_{v}" for v in DecisionStatus.values} <= set(health.GLOSSARY)
