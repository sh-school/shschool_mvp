"""[ROADMAP] هجرةُ المزامنة 0066 حارسةٌ: بندان جديدان فقط، بلا لمس القائم، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0066_sync_items_2026_10_06"
_sync66 = importlib.import_module(_MOD)


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-091", lane="backend", title="قائم", status="done", progress=100
    )


def test_creates_n096_doing_with_its_pr_token_idempotently():
    assert _sync66.add_new_items(RoadmapItem) == ["N-096"]
    assert _sync66.add_new_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-096")
    assert (item.status, item.progress, item.pr) == ("doing", 70, "#874")
    assert "لم يُقَس" in item.note and "D-229م" in item.note


def test_an_existing_code_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-096", lane="x", title="عدّله المطوّر", status="done", progress=90, note="يدويّ"
    )
    assert _sync66.add_new_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-096")
    assert (item.title, item.status, item.progress, item.note) == (
        "عدّله المطوّر",
        "done",
        90,
        "يدويّ",
    )


def test_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    _sync66.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync66.forwards(_Apps, None)
    _sync66.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code="N-096").count() == 1


def test_orders_new_item_after_0065():
    assert [row[-1] for row in _sync66.NEW_ITEMS] == [824]


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
