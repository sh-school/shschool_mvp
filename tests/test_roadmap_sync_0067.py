"""[ROADMAP] هجرةُ المزامنة 0067 حارسة: ستّةُ بنودٍ جديدةٍ فقط، وملاحظةُ ثباتٍ على VI-13 بلا لمس حالتها، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0067_sync_items_2026_10_08"
_sync67 = importlib.import_module(_MOD)
NEW = ["N-097", "N-098", "N-099", "N-100", "N-101", "N-102"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="VI-13", lane="design", title="لقطات", status="doing", progress=25, note="قديم"
    )


def test_creates_the_six_items_with_their_states_and_is_idempotent():
    assert _sync67.add_new_items(RoadmapItem) == NEW
    assert _sync67.add_new_items(RoadmapItem) == []
    by = {i.code: i for i in RoadmapItem.objects.filter(code__in=NEW)}
    assert (by["N-097"].status, by["N-097"].progress, by["N-097"].lane) == ("todo", 0, "ops")
    assert (by["N-097"].start_date, by["N-097"].end_date) == (None, None)
    assert by["N-098"].pr == "#881 #884 #886" and by["N-100"].pr == "#887 #894"
    assert (by["N-101"].status, by["N-102"].status) == ("done", "done")
    assert all("لم يُقَس" in by[c].note for c in NEW if c != "N-097")


def test_the_key_stays_off_in_production_and_is_stated_so():
    _sync67.add_new_items(RoadmapItem)
    note = RoadmapItem.objects.get(code="N-099").note
    assert "غيرُ مفعَّلٍ في الإنتاج" in note and "50%" in note


def test_no_item_claims_done_without_its_pr_and_nothing_is_closed_that_has_owner_decisions_left():
    _sync67.add_new_items(RoadmapItem)
    for item in RoadmapItem.objects.filter(code__in=NEW):
        if item.status == "done":
            assert item.pr.startswith("#")
    assert RoadmapItem.objects.get(code="N-097").status == "todo"


def test_an_existing_code_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-098", lane="x", title="عدّله المطوّر", status="done", progress=90, note="يدويّ"
    )
    assert _sync67.add_new_items(RoadmapItem) == [c for c in NEW if c != "N-098"]
    item = RoadmapItem.objects.get(code="N-098")
    assert (item.title, item.status, item.progress, item.note) == (
        "عدّله المطوّر",
        "done",
        90,
        "يدويّ",
    )


def test_the_vi13_note_is_appended_once_and_never_changes_its_state():
    _seed()
    assert _sync67.sync_notes(RoadmapItem) == ["VI-13"]
    assert _sync67.sync_notes(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="VI-13")
    assert (item.status, item.progress) == ("doing", 25)
    assert item.note.startswith("قديم") and "#896" in item.note and "N-097" in item.note


def test_a_missing_vi13_is_skipped_not_created():
    assert _sync67.sync_notes(RoadmapItem) == []
    assert not RoadmapItem.objects.filter(code="VI-13").exists()


def test_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    _sync67.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync67.forwards(_Apps, None)
    first = list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note"))
    _sync67.forwards(_Apps, None)
    assert list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note")) == first
    assert RoadmapItem.objects.filter(code__in=NEW).count() == 6


def test_orders_the_new_items_after_0066():
    assert [row[-1] for row in _sync67.NEW_ITEMS] == [825, 826, 827, 828, 829, 830]


def test_publishes_nothing_a_public_repo_must_not_say():
    origin = importlib.util.find_spec(_MOD).origin
    with open(origin, encoding="utf-8") as f:
        body = f.read()
    banned = (
        "FERNET",
        "كلمة المرور",
        "كلمة مرور",
        "C:/",
        "localhost",
        "up.railway.app",
        "railway ssh",
        "Temp@",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
