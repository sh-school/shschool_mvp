"""[ROADMAP] هجرةُ 0081 حارسة: عائلةُ العيادة الصحية CLN-00..CLN-19 بلا إعادة كتابة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_m = importlib.import_module("roadmap.migrations.0081_clinic_family_2026_10_20")


def test_creates_family_once_with_one_item_per_card():
    codes = _m.add_new_items(RoadmapItem)
    assert codes[0] == "CLN-00" and len(codes) == 20
    assert _m.add_new_items(RoadmapItem) == []
    cards = sorted(i.ref for i in RoadmapItem.objects.filter(src="CLN").exclude(code="CLN-00"))
    assert cards == [f"W-20261020-{n:03d}" for n in range(24, 43)]


def test_every_dependency_points_to_a_family_item():
    _m.add_new_items(RoadmapItem)
    known = set(RoadmapItem.objects.values_list("code", flat=True))
    for item in RoadmapItem.objects.filter(src="CLN"):
        for dep in filter(None, (d.strip() for d in item.deps.replace("،", ",").split(","))):
            assert dep in known, (item.code, dep)


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(code="CLN-06", lane="x", title="عدّله المطوّر", status="doing")
    assert "CLN-06" not in _m.add_new_items(RoadmapItem)
    assert RoadmapItem.objects.get(code="CLN-06").title == "عدّله المطوّر"


def test_forwards_noop_on_empty_db():
    _m.forwards(type("A", (), {"get_model": staticmethod(lambda *_: RoadmapItem)}), None)
    assert RoadmapItem.objects.count() == 0
