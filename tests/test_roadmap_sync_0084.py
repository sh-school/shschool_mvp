"""[ROADMAP] هجرةُ المزامنة 0084 حارسة: اثنا عشر بنداً جديداً مرّةً واحدة، وملاحظاتُ العيادة بلا لمس الحالة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync84 = importlib.import_module("roadmap.migrations.0084_sync_items_2026_10_25")

NEW_CODES = [f"N-{n}" for n in range(155, 167)]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="CLN-07",
        lane="frontend",
        title="الإدخال السريع",
        status="todo",
        progress=0,
        note="قديم",
        pr="",
    )


def test_new_items_created_once_and_never_rewritten():
    assert _sync84.add_new_items(RoadmapItem) == NEW_CODES
    item = RoadmapItem.objects.get(code="N-155")
    assert (item.status, item.progress) == ("done", 100)
    assert _sync84.add_new_items(RoadmapItem) == []


def test_pr_field_fits_and_codes_unique():
    codes = [row[0] for row in _sync84.NEW_ITEMS]
    assert codes == NEW_CODES and len(set(codes)) == len(codes)
    assert all(len(row[9]) <= 64 for row in _sync84.NEW_ITEMS)
    assert all(row[4] in {"done", "doing"} and 0 <= row[5] <= 100 for row in _sync84.NEW_ITEMS)


def test_note_added_once_state_untouched():
    _seed()
    changed = _sync84.sync_notes(RoadmapItem)
    assert changed == ["CLN-07"]
    item = RoadmapItem.objects.get(code="CLN-07")
    assert (item.status, item.progress) == ("todo", 0)
    assert item.pr == "#1265" and "قديم" in item.note
    first = item.note
    assert _sync84.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="CLN-07").note == first


def test_notes_claim_no_measured_impact():
    assert all("لم يُقَس" in line for _c, _p, line in _sync84.NOTES)
    assert all("لم يُقَس" in row[11] for row in _sync84.NEW_ITEMS)


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync84.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync84.forwards(_Apps, None)
    first = RoadmapItem.objects.get(code="CLN-07").note
    _sync84.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="CLN-07").note == first
    assert RoadmapItem.objects.filter(code__in=NEW_CODES).count() == 12


def test_depends_on_0083():
    assert _sync84.Migration.dependencies == [("roadmap", "0083_sync_items_2026_10_22")]
