"""[ROADMAP] هجرةُ 0077 حارسة: ثلاثةَ عشر بنداً جديداً N-135..N-147 وإغلاقُ N-118 فقط إن كان todo، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import importlib.util

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0077_sync_items_2026_10_14"
_sync77 = importlib.import_module(_MOD)
_CODES = [f"N-{n}" for n in range(135, 148)]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def test_creates_thirteen_items_once():
    assert _sync77.add_new_items(RoadmapItem) == _CODES
    assert _sync77.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 13


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-140", lane="x", title="عدّله المطوّر", status="doing", note="يدوي"
    )
    assert "N-140" not in _sync77.add_new_items(RoadmapItem)
    item = RoadmapItem.objects.get(code="N-140")
    assert (item.title, item.status, item.note) == ("عدّله المطوّر", "doing", "يدوي")


def test_items_with_open_remainder_are_not_marked_done():
    _sync77.add_new_items(RoadmapItem)
    for code in ("N-135", "N-138", "N-141", "N-143", "N-145"):
        assert RoadmapItem.objects.get(code=code).status == "doing"


def test_closes_n118_only_while_todo():
    RoadmapItem.objects.create(code="N-118", lane="x", title="t", status="todo")
    assert _sync77.close_items(RoadmapItem) == ["N-118"]
    item = RoadmapItem.objects.get(code="N-118")
    assert (item.status, item.progress) == ("done", 100)
    assert "#1067" in item.pr
    assert _sync77.close_items(RoadmapItem) == []


def test_does_not_touch_n118_if_developer_changed_it():
    RoadmapItem.objects.create(code="N-118", lane="x", title="t", status="doing", progress=40)
    assert _sync77.close_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-118")
    assert (item.status, item.progress) == ("doing", 40)


def test_forwards_noop_on_empty_db():
    _sync77.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_forwards_idempotent_when_seeded():
    RoadmapItem.objects.create(code="N-001", lane="x", title="t")
    _sync77.forwards(_Apps, None)
    _sync77.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__in=_CODES).count() == 13


def test_depends_on_0076():
    assert _sync77.Migration.dependencies == [("roadmap", "0076_behavior_flow_items_2026_10_12")]


def test_publishes_nothing_a_public_repo_must_not_say():
    origin = importlib.util.find_spec(_MOD).origin
    with open(origin, encoding="utf-8") as f:
        body = f.read()
    banned = (
        "FERNET",
        "IDOR",
        "كلمة المرور",
        "كلمة مرور",
        "C:/",
        "localhost",
        "up.railway.app",
        "railway ssh",
        "Temp@",
    )
    assert [t for t in banned if t in body] == []
