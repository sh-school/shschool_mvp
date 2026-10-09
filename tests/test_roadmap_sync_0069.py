"""[ROADMAP] هجرةُ المزامنة 0069 حارسة: أربعةُ بنودٍ جديدة N-105..N-108 وملاحظةُ تقدّمٍ على SCH-22 بلا لمس حالتها، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0069_sync_items_2026_10_09b"
_sync69 = importlib.import_module(_MOD)
NEW = ["N-105", "N-106", "N-107", "N-108"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="SCH-22",
        lane="x",
        title="V2",
        status="doing",
        progress=40,
        note="قديم",
        pr="#901 #902 #904",
    )


def test_creates_the_four_items_once_with_honest_states():
    assert _sync69.add_new_items(RoadmapItem) == NEW
    assert _sync69.add_new_items(RoadmapItem) == []
    by = {i.code: i for i in RoadmapItem.objects.filter(code__in=NEW)}
    assert by["N-105"].pr == "#909" and (by["N-105"].status, by["N-105"].progress) == ("doing", 40)
    assert by["N-106"].pr == "#906" and by["N-106"].deps == "N-100"
    assert (by["N-107"].status, by["N-107"].pr) == ("blocked", "#908")
    assert by["N-108"].pr == "#915 #917" and by["N-108"].progress == 10
    assert [by[c].sort_order for c in NEW] == [833, 834, 835, 836]


def test_no_new_item_claims_done_or_an_unmeasured_impact():
    _sync69.add_new_items(RoadmapItem)
    for item in RoadmapItem.objects.filter(code__in=NEW):
        assert item.status != "done"
        assert "لم يُقَس" in item.note


def test_n107_is_blocked_by_the_owner_decision_not_closed():
    _sync69.add_new_items(RoadmapItem)
    assert "محجوبٌ بقرار المالك" in RoadmapItem.objects.get(code="N-107").note


def test_an_existing_code_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-105", lane="x", title="عدّله المطوّر", status="done", progress=90, note="يدويّ"
    )
    assert _sync69.add_new_items(RoadmapItem) == ["N-106", "N-107", "N-108"]
    item = RoadmapItem.objects.get(code="N-105")
    assert (item.title, item.status, item.progress, item.note) == (
        "عدّله المطوّر",
        "done",
        90,
        "يدويّ",
    )


def test_sch22_note_once_pr_added_state_untouched():
    _seed()
    assert _sync69.sync_notes(RoadmapItem) == ["SCH-22"]
    assert _sync69.sync_notes(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="SCH-22")
    assert (item.status, item.progress) == ("doing", 40)
    assert item.pr == "#901 #902 #904 #914" and item.note.startswith("قديم") and "#914" in item.note


def test_pr_field_is_left_alone_when_it_would_exceed_the_limit():
    RoadmapItem.objects.create(
        code="SCH-22", lane="x", title="t", status="doing", progress=1, note="", pr="#" + "9" * 62
    )
    _sync69.sync_notes(RoadmapItem)
    assert RoadmapItem.objects.get(code="SCH-22").pr == "#" + "9" * 62


def test_sync_notes_creates_nothing_and_skips_missing_codes():
    assert _sync69.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 0


def test_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    _sync69.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync69.forwards(_Apps, None)
    first = list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note", "pr"))
    _sync69.forwards(_Apps, None)
    assert (
        list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note", "pr"))
        == first
    )
    assert RoadmapItem.objects.filter(code__in=NEW).count() == 4


def test_depends_on_0068():
    assert _sync69.Migration.dependencies == [("roadmap", "0068_sync_items_2026_10_09")]


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
