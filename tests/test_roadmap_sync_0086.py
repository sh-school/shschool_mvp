"""[ROADMAP] هجرةُ المزامنة 0086 حارسة: بندُ هويّة «الشحانية» v5 يُنشأ مرّةً واحدة ولا يُعاد كتابتُه."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync86 = importlib.import_module("roadmap.migrations.0086_sync_items_2026_11_16")

NEW_CODES = ["VI-60"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="VI-59", lane="frontend", title="بندٌ قائم", status="todo", progress=0, note="قديم"
    )


def test_new_item_created_once_and_never_rewritten():
    assert _sync86.add_new_items(RoadmapItem) == NEW_CODES
    item = RoadmapItem.objects.get(code="VI-60")
    assert (item.status, item.progress, item.src) == ("done", 100, "VI")
    RoadmapItem.objects.filter(code="VI-60").update(status="doing", progress=50)
    assert _sync86.add_new_items(RoadmapItem) == []
    item.refresh_from_db()
    assert (item.status, item.progress) == ("doing", 50)


def test_fields_fit_and_codes_unique():
    codes = [row[0] for row in _sync86.NEW_ITEMS]
    assert codes == NEW_CODES and len(set(codes)) == len(codes)
    assert all(len(row[10]) <= 64 for row in _sync86.NEW_ITEMS)
    assert all(len(row[9]) <= 120 for row in _sync86.NEW_ITEMS)
    assert all(row[5] in {"done", "doing"} and 0 <= row[6] <= 100 for row in _sync86.NEW_ITEMS)


def test_note_states_what_was_and_was_not_measured():
    assert all("المقيس" in row[12] and "لم يُقَس" in row[12] for row in _sync86.NEW_ITEMS)


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync86.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync86.forwards(_Apps, None)
    _sync86.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__in=NEW_CODES).count() == 1
    old = RoadmapItem.objects.get(code="VI-59")
    assert (old.status, old.progress, old.note) == ("todo", 0, "قديم")


def test_depends_on_0085():
    assert _sync86.Migration.dependencies == [("roadmap", "0085_sync_items_2026_10_26")]
