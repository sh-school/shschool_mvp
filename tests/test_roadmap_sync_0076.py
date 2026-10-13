"""[ROADMAP] هجرةُ 0076 حارسة: تسعةُ بنودِ P0 لقرارات D-424م، كلُّها todo بتقدّمٍ 0، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import importlib.util

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0076_behavior_flow_items_2026_10_12"
_sync76 = importlib.import_module(_MOD)
_CODES = [f"N-{n}" for n in range(126, 135)]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def test_creates_nine_items_once():
    assert _sync76.add_new_items(RoadmapItem) == _CODES
    assert _sync76.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 9


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-130", lane="x", title="عدّله المطوّر", status="doing", note="يدوي"
    )
    assert "N-130" not in _sync76.add_new_items(RoadmapItem)
    item = RoadmapItem.objects.get(code="N-130")
    assert (item.title, item.status, item.note) == ("عدّله المطوّر", "doing", "يدوي")


def test_all_items_are_unstarted_p0_without_cards():
    _sync76.add_new_items(RoadmapItem)
    for item in RoadmapItem.objects.all():
        assert (item.status, item.progress) == ("todo", 0)
        assert "P0" in item.note and "D-424م" in item.ref
        assert "W-2026" not in item.ref


def test_notification_item_is_marked_blocked():
    _sync76.add_new_items(RoadmapItem)
    assert "محجوب" in RoadmapItem.objects.get(code="N-130").note


def test_forwards_noop_on_empty_db():
    _sync76.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_forwards_idempotent_when_seeded():
    RoadmapItem.objects.create(code="N-001", lane="x", title="t")
    _sync76.forwards(_Apps, None)
    _sync76.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__in=_CODES).count() == 9


def test_depends_on_0075():
    assert _sync76.Migration.dependencies == [("roadmap", "0075_sync_items_2026_10_12")]


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
    assert [t for t in banned if t in body] == []
