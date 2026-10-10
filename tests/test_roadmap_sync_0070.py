"""[ROADMAP] هجرةُ المزامنة 0070 حارسة: ملاحظةُ #913 على N-098 مرّةً واحدة بلا لمس الحالة، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0070_sync_items_2026_10_09c"
_sync70 = importlib.import_module(_MOD)


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="N-098", lane="x", title="الجدول", status="doing", progress=60, note="قديم", pr="#881"
    )


def test_note_added_once_pr_added_state_untouched():
    _seed()
    assert _sync70.sync_notes(RoadmapItem) == ["N-098"]
    item = RoadmapItem.objects.get(code="N-098")
    assert (item.status, item.progress) == ("doing", 60)
    assert item.pr == "#881 #913" and "قديم" in item.note and "#913" in item.note
    first = item.note
    assert _sync70.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-098").note == first


def test_note_claims_no_measured_impact_and_keeps_open_work():
    line = _sync70.NOTES[0][2]
    assert "لم يُقَس" in line and "W-20261009-018" in line and "لا تغيّرَ في الحالة" in line


def test_missing_code_creates_nothing():
    assert _sync70.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 0


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync70.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync70.forwards(_Apps, None)
    first = RoadmapItem.objects.get(code="N-098").note
    _sync70.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="N-098").note == first


def test_depends_on_0069():
    assert _sync70.Migration.dependencies == [("roadmap", "0069_sync_items_2026_10_09b")]


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
