"""[ROADMAP] هجرةُ المزامنة 0068 حارسة: بندان جديدان N-103 وN-104 وملاحظاتُ تقدّمٍ على بنودٍ قائمةٍ بلا لمس حالتها، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0068_sync_items_2026_10_09"
_sync68 = importlib.import_module(_MOD)
CODES = ["VI-13", "N-097", "N-098", "N-099", "SCH-22"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    for code in CODES:
        RoadmapItem.objects.create(
            code=code, lane="x", title=code, status="doing", progress=40, note="قديم", pr="#1"
        )


def test_appends_one_note_per_existing_item_once_and_never_touches_state():
    _seed()
    assert _sync68.sync_notes(RoadmapItem) == CODES
    assert _sync68.sync_notes(RoadmapItem) == []
    for item in RoadmapItem.objects.filter(code__in=CODES):
        assert (item.status, item.progress) == ("doing", 40)
        assert item.note.startswith("قديم") and "[2026-10-09]" in item.note


def test_records_the_merged_pr_tokens_without_duplicates():
    _seed()
    _sync68.sync_notes(RoadmapItem)
    by = {i.code: i.pr for i in RoadmapItem.objects.filter(code__in=CODES)}
    assert by["VI-13"] == "#1 #896" and by["N-098"] == "#1 #898"
    assert by["N-099"] == "#1 #900" and by["SCH-22"] == "#1 #901 #902 #904"


def test_pr_field_is_left_alone_when_it_would_exceed_the_limit():
    RoadmapItem.objects.create(
        code="SCH-22", lane="x", title="t", status="doing", progress=1, note="", pr="#" + "9" * 60
    )
    _sync68.sync_notes(RoadmapItem)
    assert RoadmapItem.objects.get(code="SCH-22").pr == "#" + "9" * 60


def test_sync_notes_creates_no_item_and_skips_missing_codes():
    assert _sync68.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 0


def test_creates_n103_once_with_pr_and_honest_state():
    assert _sync68.add_new_items(RoadmapItem) == ["N-103", "N-104"]
    assert _sync68.add_new_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-103")
    assert item.pr == "#895" and (item.status, item.progress) == ("doing", 50)
    assert "لم يُقَس" in item.note and item.sort_order == 831
    leave = RoadmapItem.objects.get(code="N-104")
    assert leave.pr == "#905" and (leave.status, leave.progress) == ("doing", 50)
    assert "لم يُقَس" in leave.note and leave.sort_order == 832


def test_an_existing_n103_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-103", lane="x", title="عدّله المطوّر", status="done", progress=90, note="يدويّ"
    )
    assert _sync68.add_new_items(RoadmapItem) == ["N-104"]
    item = RoadmapItem.objects.get(code="N-103")
    assert (item.title, item.status, item.progress, item.note) == (
        "عدّله المطوّر",
        "done",
        90,
        "يدويّ",
    )


def test_notes_do_not_claim_what_was_not_measured_or_merged():
    notes = {code: line for code, _pr, line in _sync68.NOTES}
    assert "لم يُغلق" in notes["VI-13"] and "لم يُقَس" in notes["N-098"]
    assert "غيرَ مفعَّلٍ" in notes["N-099"] and "لم يُدمج" in notes["SCH-22"]
    assert "#905" not in "".join(notes.values())  # #905 بندٌ جديدٌ لا ملاحظة


def test_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    _sync68.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync68.forwards(_Apps, None)
    first = list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note", "pr"))
    _sync68.forwards(_Apps, None)
    assert (
        list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note", "pr"))
        == first
    )


def test_depends_on_0067():
    assert _sync68.Migration.dependencies == [("roadmap", "0067_sync_items_2026_10_08")]


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
