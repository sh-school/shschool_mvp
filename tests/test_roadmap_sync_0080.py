"""[ROADMAP] هجرةُ 0080 حارسة: بندان جديدان N-150 وN-151 بلا إعادة كتابة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_m = importlib.import_module("roadmap.migrations.0080_sync_items_2026_10_17")


def test_creates_two_items_once():
    assert _m.add_new_items(RoadmapItem) == ["N-150", "N-151"]
    assert _m.add_new_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-151")
    assert (item.status, item.pr) == ("done", "#1129")


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(code="N-150", lane="x", title="عدّله المطوّر", status="doing")
    assert _m.add_new_items(RoadmapItem) == ["N-151"]
    assert RoadmapItem.objects.get(code="N-150").title == "عدّله المطوّر"


def test_forwards_noop_on_empty_db():
    _m.forwards(type("A", (), {"get_model": staticmethod(lambda *_: RoadmapItem)}), None)
    assert RoadmapItem.objects.count() == 0
