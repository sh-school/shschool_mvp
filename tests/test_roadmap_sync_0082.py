"""[ROADMAP] هجرةُ المزامنة 0082 حارسة: N-152 جديدٌ مرّةً واحدة، وملاحظةُ #1211 على N-098 بلا لمس الحالة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync82 = importlib.import_module("roadmap.migrations.0082_sync_items_2026_10_21")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-098", lane="x", title="الجدول", status="doing", progress=60, note="قديم", pr="#881"
    )


def test_new_item_created_once_and_never_rewritten():
    assert _sync82.add_new_items(RoadmapItem) == ["N-152"]
    item = RoadmapItem.objects.get(code="N-152")
    assert (item.status, item.progress, item.pr) == ("done", 100, "#1178")
    assert _sync82.add_new_items(RoadmapItem) == []


def test_note_added_once_state_untouched():
    _seed()
    assert _sync82.sync_notes(RoadmapItem) == ["N-098"]
    item = RoadmapItem.objects.get(code="N-098")
    assert (item.status, item.progress) == ("doing", 60)
    assert item.pr == "#881 #1211" and "قديم" in item.note
    first = item.note
    assert _sync82.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-098").note == first


def test_notes_claim_no_measured_impact():
    assert "لم يُقَس" in _sync82.NOTES[0][2]
    assert "لم يُقَس" in _sync82.NEW_ITEMS[0][15]


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync82.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync82.forwards(_Apps, None)
    first = RoadmapItem.objects.get(code="N-098").note
    _sync82.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="N-098").note == first
    assert RoadmapItem.objects.filter(code="N-152").count() == 1


def test_depends_on_0081():
    assert _sync82.Migration.dependencies == [("roadmap", "0081_clinic_family_2026_10_20")]
