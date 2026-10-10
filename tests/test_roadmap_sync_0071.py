"""[ROADMAP] هجرةُ المزامنة 0071 حارسة: ملاحظةُ #920 على SCH-22 مرّةً واحدة بلا لمس الحالة ولا ادّعاءِ نشرٍ، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0071_sync_items_2026_10_10"
_sync71 = importlib.import_module(_MOD)


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="SCH-22", lane="x", title="V2", status="doing", progress=40, note="قديم", pr="#914"
    )


def test_note_once_pr_added_state_untouched():
    _seed()
    assert _sync71.sync_notes(RoadmapItem) == ["SCH-22"]
    item = RoadmapItem.objects.get(code="SCH-22")
    assert (item.status, item.progress, item.pr) == ("doing", 40, "#914 #920")
    assert "قديم" in item.note and "#920" in item.note
    first = item.note
    assert _sync71.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-22").note == first


def test_note_says_draft_unpublished_and_unmeasured_by_the_tool():
    line = _sync71.NOTES[0][2]
    assert "مسوّدةٌ غيرُ منشورة" in line and "ولم يقسها" in line
    assert "لا يُقال «منشور» أو «معتمد»" in line and "لا تغيّرَ في الحالة" in line


def test_missing_code_creates_nothing():
    assert _sync71.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 0


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync71.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync71.forwards(_Apps, None)
    first = RoadmapItem.objects.get(code="SCH-22").note
    _sync71.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="SCH-22").note == first


def test_depends_on_0070():
    assert _sync71.Migration.dependencies == [("roadmap", "0070_sync_items_2026_10_09c")]


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
