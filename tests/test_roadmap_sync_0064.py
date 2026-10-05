"""[ROADMAP] هجرةُ المزامنة 0064 حارسةٌ: بندان جديدان فقط، بلا لمس القائم، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync64 = importlib.import_module("roadmap.migrations.0064_sync_items_2026_10_05")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-091", lane="backend", title="قائم", status="done", progress=100
    )


def test_creates_n092_done_and_n093_doing_with_their_pr_tokens():
    assert _sync64.add_new_items(RoadmapItem) == ["N-092", "N-093"]
    assert _sync64.add_new_items(RoadmapItem) == []
    n92 = RoadmapItem.objects.get(code="N-092")
    n93 = RoadmapItem.objects.get(code="N-093")
    assert (n92.status, n92.progress, n92.pr) == ("done", 100, "#855")
    assert (n93.status, n93.progress, n93.pr) == ("doing", 83, "#862")
    assert "لم يُقَس" in n92.note and "لم يُقَس" in n93.note


def test_n093_keeps_the_blocked_remainder_explicit_and_attributes_the_local_count():
    _sync64.add_new_items(RoadmapItem)
    note = RoadmapItem.objects.get(code="N-093").note
    assert "محجوب" in note and "W-20261005-002" in note
    assert "11570" in note and "ليس قياسي" not in note and "لا قياسي" in note


def test_an_existing_code_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-092", lane="x", title="عدّله المطوّر", status="doing", progress=10, note="يدويّ"
    )
    assert _sync64.add_new_items(RoadmapItem) == ["N-093"]
    item = RoadmapItem.objects.get(code="N-092")
    assert (item.title, item.status, item.progress, item.note) == (
        "عدّله المطوّر",
        "doing",
        10,
        "يدويّ",
    )


def test_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    _sync64.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync64.forwards(_Apps, None)
    first = list(
        RoadmapItem.objects.order_by("code").values_list("code", "status", "progress", "note")
    )
    _sync64.forwards(_Apps, None)
    assert (
        list(RoadmapItem.objects.order_by("code").values_list("code", "status", "progress", "note"))
        == first
    )
    assert RoadmapItem.objects.filter(code__in=["N-092", "N-093"]).count() == 2


def test_orders_new_items_after_n091s_slot():
    assert [row[-1] for row in _sync64.NEW_ITEMS] == [820, 821]


def test_publishes_nothing_a_public_repo_must_not_say():
    origin = importlib.util.find_spec("roadmap.migrations.0064_sync_items_2026_10_05").origin
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
