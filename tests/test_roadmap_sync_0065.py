"""[ROADMAP] هجرةُ المزامنة 0065 حارسةٌ: بندان جديدان فقط، بلا لمس القائم، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0065_sync_items_2026_10_05b"
_sync65 = importlib.import_module(_MOD)


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-091", lane="backend", title="قائم", status="done", progress=100
    )


def test_creates_n094_doing_and_n095_blocked_idempotently():
    assert _sync65.add_new_items(RoadmapItem) == ["N-094", "N-095"]
    assert _sync65.add_new_items(RoadmapItem) == []
    n94 = RoadmapItem.objects.get(code="N-094")
    n95 = RoadmapItem.objects.get(code="N-095")
    assert (n94.status, n94.progress, n94.pr) == ("doing", 50, "#861")
    assert (n95.status, n95.progress, n95.pr) == ("blocked", 0, "")
    assert "لم يُقَس" in n94.note and "محجوب" in n95.note


def test_an_existing_code_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-094", lane="x", title="عدّله المطوّر", status="done", progress=90, note="يدويّ"
    )
    assert _sync65.add_new_items(RoadmapItem) == ["N-095"]
    item = RoadmapItem.objects.get(code="N-094")
    assert (item.title, item.status, item.progress, item.note) == (
        "عدّله المطوّر",
        "done",
        90,
        "يدويّ",
    )


def test_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    _sync65.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync65.forwards(_Apps, None)
    _sync65.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__in=["N-094", "N-095"]).count() == 2


def test_orders_new_items_after_0064():
    assert [row[-1] for row in _sync65.NEW_ITEMS] == [822, 823]


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
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
