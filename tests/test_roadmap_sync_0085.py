"""[ROADMAP] هجرةُ المزامنة 0085 حارسة: بندان جديدان مرّةً واحدة، وملاحظةُ N-164 بلا لمس الحالة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync85 = importlib.import_module("roadmap.migrations.0085_sync_items_2026_10_26")

NEW_CODES = ["N-167", "N-168"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-164",
        lane="operations",
        title="بيئةُ المطوّر",
        status="doing",
        progress=80,
        note="قديم",
        pr="#1273 #1274",
    )


def test_new_items_created_once_and_never_rewritten():
    assert _sync85.add_new_items(RoadmapItem) == NEW_CODES
    item = RoadmapItem.objects.get(code="N-167")
    assert (item.status, item.progress) == ("doing", 70)
    assert _sync85.add_new_items(RoadmapItem) == []


def test_pr_field_fits_and_codes_unique():
    codes = [row[0] for row in _sync85.NEW_ITEMS]
    assert codes == NEW_CODES and len(set(codes)) == len(codes)
    assert all(len(row[9]) <= 64 for row in _sync85.NEW_ITEMS)
    assert all(row[4] in {"done", "doing"} and 0 <= row[5] <= 100 for row in _sync85.NEW_ITEMS)


def test_note_added_once_state_untouched():
    _seed()
    assert _sync85.sync_notes(RoadmapItem) == ["N-164"]
    item = RoadmapItem.objects.get(code="N-164")
    assert (item.status, item.progress) == ("doing", 80)
    assert item.pr == "#1273 #1274 #1275" and "قديم" in item.note
    first = item.note
    assert _sync85.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-164").note == first


def test_notes_claim_no_measured_impact():
    assert all("لم يُقَس" in line for _c, _p, line in _sync85.NOTES)
    assert all("لم يُقَس" in row[11] for row in _sync85.NEW_ITEMS)


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync85.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync85.forwards(_Apps, None)
    first = RoadmapItem.objects.get(code="N-164").note
    _sync85.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="N-164").note == first
    assert RoadmapItem.objects.filter(code__in=NEW_CODES).count() == 2


def test_depends_on_0084():
    assert _sync85.Migration.dependencies == [("roadmap", "0084_sync_items_2026_10_25")]
