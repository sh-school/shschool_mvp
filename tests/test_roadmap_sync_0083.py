"""[ROADMAP] هجرةُ المزامنة 0083 حارسة: N-153 وN-154 جديدان مرّةً واحدة، وملاحظةُ #1222 على N-108 بلا لمس الحالة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync83 = importlib.import_module("roadmap.migrations.0083_sync_items_2026_10_22")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-108", lane="x", title="الجدول", status="doing", progress=60, note="قديم", pr="#881"
    )


def test_new_item_created_once_and_never_rewritten():
    assert _sync83.add_new_items(RoadmapItem) == ["N-153", "N-154"]
    item = RoadmapItem.objects.get(code="N-153")
    assert (item.status, item.progress, item.pr) == ("done", 100, "#1212")
    assert _sync83.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-154").pr == "#1219"


def test_note_added_once_state_untouched():
    _seed()
    assert _sync83.sync_notes(RoadmapItem) == ["N-108"]
    item = RoadmapItem.objects.get(code="N-108")
    assert (item.status, item.progress) == ("doing", 60)
    assert item.pr == "#881 #1222" and "قديم" in item.note
    first = item.note
    assert _sync83.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-108").note == first


def test_notes_claim_no_measured_impact():
    assert "لم يُقَس" in _sync83.NOTES[0][2]
    assert "لم يُقَس" in _sync83.NEW_ITEMS[0][15]


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync83.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync83.forwards(_Apps, None)
    first = RoadmapItem.objects.get(code="N-108").note
    _sync83.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="N-108").note == first
    assert RoadmapItem.objects.filter(code__in=["N-153", "N-154"]).count() == 2


def test_depends_on_0082():
    assert _sync83.Migration.dependencies == [("roadmap", "0082_sync_items_2026_10_21")]
