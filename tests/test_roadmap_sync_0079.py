"""[ROADMAP] هجرةُ 0079 حارسة: بندان جديدان N-148 وN-149 بلا إعادة كتابة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_m = importlib.import_module("roadmap.migrations.0079_sync_items_2026_10_15")


def test_creates_two_items_once():
    assert _m.add_new_items(RoadmapItem) == ["N-148", "N-149"]
    assert _m.add_new_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-149")
    assert (item.status, item.pr) == ("done", "#1086")


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(code="N-148", lane="x", title="عدّله المطوّر", status="doing")
    assert _m.add_new_items(RoadmapItem) == ["N-149"]
    assert RoadmapItem.objects.get(code="N-148").title == "عدّله المطوّر"


def test_forwards_noop_on_empty_db():
    _m.forwards(type("A", (), {"get_model": staticmethod(lambda *_: RoadmapItem)}), None)
    assert RoadmapItem.objects.count() == 0
