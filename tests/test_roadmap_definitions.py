"""[ROADMAP] مطابقةُ حالات الدفتر بحالات الخارطة وتعريفُ الأولويّات (W-20261009-027).

الجدولان ثوابتُ في `roadmap/health.py` تقرؤهما الصفحةُ في «القواعد والتعريفات»؛ فالحرّاسُ: (1) تغطيةُ حالات الدفتر
كلِّها بترتيب دورتها (مصدرُها `tools/ledger.py::STATES` خارج المستودع فتُثبَّت هنا نصّاً)، (2) كلُّ أثرٍ يسمّي حالةَ خارطةٍ
موجودةً في النموذج، (3) الصفحةُ تحمل الجدولين والسكربتُ يقرؤهما، (4) لا نسخةَ ثانيةً للتعريف في السكربت.
"""

import re
from pathlib import Path

import pytest

from roadmap import health
from roadmap.models import ItemStatus
from roadmap.services import page_context

pytestmark = pytest.mark.django_db

JS = (Path(__file__).resolve().parent.parent / "static/js/roadmap.js").read_text(encoding="utf-8")

LEDGER_STATES = [
    "captured", "verified", "routed", "in_progress", "ready_for_review", "notes",
    "approved", "pushed", "merged", "published", "closed", "deferred",
]  # fmt: skip


class TestLedgerStateMap:
    def test_every_ledger_state_is_covered_once_in_cycle_order(self):
        assert [row[0] for row in health.LEDGER_STATE_MAP] == LEDGER_STATES

    def test_each_row_has_a_meaning_and_an_effect(self):
        for state, meaning, effect in health.LEDGER_STATE_MAP:
            assert len(meaning) >= 12 and len(effect) >= 8, state

    def test_effects_name_only_real_roadmap_statuses(self):
        names = {label for _, label in ItemStatus.choices}
        quoted = set()
        for _, _, effect in health.LEDGER_STATE_MAP:
            quoted |= set(re.findall(r"«([^»]+)»", effect))
        # كلُّ ما بين «» في الأثر حالةُ خارطةٍ حقيقيّةٌ أو اصطلاحٌ معروف (routed بلا حامل)
        allowed = names | {"routed بلا حامل", "متأخّر"}
        assert quoted <= allowed, quoted - allowed

    def test_the_closing_rows_point_at_the_sync_not_at_an_automatic_close(self):
        effects = {state: effect for state, _, effect in health.LEDGER_STATE_MAP}
        assert "مزامنة" in effects["merged"] and "مزامنة" in effects["published"]


class TestPriorities:
    def test_four_priorities_with_a_time_definition_each(self):
        assert [code for code, _ in health.PRIORITY_DEFS] == ["P0", "P1", "P2", "P3"]
        assert all(len(text) >= 4 for _, text in health.PRIORITY_DEFS)


class TestPage:
    def test_the_payload_carries_both_tables_from_the_constants(self):
        data = page_context()["roadmap_data"]["definitions"]
        assert data["ledgerMap"] == [list(r) for r in health.LEDGER_STATE_MAP]
        assert data["priorities"] == [list(r) for r in health.PRIORITY_DEFS]

    def test_the_script_reads_the_payload_and_holds_no_second_copy(self):
        assert "D.definitions" in JS and "ledgerMap" in JS and "priorities" in JS
        assert "'lmap'" in JS and "'prio'" in JS
        for state in (
            s for s in LEDGER_STATES if s != "deferred"
        ):  # deferred اسمٌ مشتركٌ مع حالة البند
            assert f"'{state}'" not in JS, f"الحالة {state} مكرَّرةٌ في السكربت بدل قراءتها من الخادم"
