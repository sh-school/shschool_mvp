"""[ROADMAP] هجرةُ المزامنة 0072 حارسة: أربعةُ بنودٍ جديدة مرّةً واحدة، بلا لمسِ بندٍ قائم، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import importlib.util
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0072_sync_items_2026_10_10b"
_sync72 = importlib.import_module(_MOD)
_CODES = ["N-109", "N-110", "N-111", "N-112"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(code="SCH-22", lane="x", title="V2", status="doing", progress=40)


def test_creates_four_items_once():
    assert _sync72.add_new_items(RoadmapItem) == _CODES
    assert _sync72.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 4


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-110", lane="x", title="عدّله المطوّر", status="todo", note="يدوي"
    )
    assert _sync72.add_new_items(RoadmapItem) == ["N-109", "N-111", "N-112"]
    item = RoadmapItem.objects.get(code="N-110")
    assert (item.title, item.status, item.note) == ("عدّله المطوّر", "todo", "يدوي")


def test_only_docs_item_closed_and_source_item_stays_open():
    _sync72.add_new_items(RoadmapItem)
    status = {i.code: (i.status, i.progress) for i in RoadmapItem.objects.all()}
    assert status["N-111"] == ("done", 100)
    assert status["N-112"][0] == "doing" and status["N-112"][1] < 100  # موضعٌ سادسٌ متبقٍّ
    assert status["N-109"][0] == status["N-110"][0] == "doing"


def test_measurements_are_scoped_and_not_claimed_from_production():
    notes = {i[0]: i[15] for i in _sync72.NEW_ITEMS}
    assert "محلّياً" in notes["N-110"] and "لم يُقَس** على الإنتاج" in notes["N-110"]
    assert "لم يُقَس" in notes["N-109"] and "مؤشّر مقيساً" in notes["N-111"]
    assert "W-20261010-011" in notes["N-112"]


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync72.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync72.forwards(_Apps, None)
    _sync72.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__in=_CODES).count() == 4


def test_pr_field_within_limit():
    _sync72.add_new_items(RoadmapItem)
    assert all(len(i.pr) <= 64 for i in RoadmapItem.objects.all())


def test_depends_on_0071():
    assert _sync72.Migration.dependencies == [("roadmap", "0071_sync_items_2026_10_10")]


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
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
