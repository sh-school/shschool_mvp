"""[ROADMAP] هجرةُ المزامنة 0075 حارسة: أربعةُ بنودٍ جديدة مرّةً واحدة، وملاحظاتٌ بلا لمس الحالة، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import importlib.util

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0075_sync_items_2026_10_12"
_sync75 = importlib.import_module(_MOD)
_CODES = ["N-122", "N-123", "N-124", "N-125"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    for code, status, progress in (("N-094", "doing", 60),):
        RoadmapItem.objects.create(code=code, lane="x", title="t", status=status, progress=progress)


def test_creates_four_items_once():
    assert _sync75.add_new_items(RoadmapItem) == _CODES
    assert _sync75.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 4


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-124", lane="x", title="عدّله المطوّر", status="todo", note="يدوي"
    )
    assert "N-124" not in _sync75.add_new_items(RoadmapItem)
    item = RoadmapItem.objects.get(code="N-124")
    assert (item.title, item.status, item.note) == ("عدّله المطوّر", "todo", "يدوي")


def test_only_finished_work_is_closed_and_gaps_stay_open():
    _sync75.add_new_items(RoadmapItem)
    status = {i.code: (i.status, i.progress) for i in RoadmapItem.objects.all()}
    assert status["N-123"] == status["N-125"] == ("done", 100)
    assert status["N-122"][0] == status["N-124"][0] == "doing"
    assert status["N-122"][1] < 100 and status["N-124"][1] < 100


def test_notes_never_touch_status_or_progress_and_are_idempotent():
    _seed()
    _sync75.forwards(_Apps, None)
    _sync75.forwards(_Apps, None)
    for code, st, pr in (("N-094", "doing", 60),):
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress) == (st, pr)
        assert item.note.count("[2026-10-12]") == 1


def test_measurements_are_attributed_not_claimed_from_production():
    notes = {i[0]: i[15] for i in _sync75.NEW_ITEMS}
    assert "لم يُقَس أثرٌ على الإنتاج" in notes["N-122"]
    assert "لا أثرَ مقيساً حيّاً" in notes["N-123"]
    assert "باقٍ لقرار المالك" in notes["N-124"]
    assert "لم يُقَس أثرٌ على الإنتاج" in notes["N-125"]


def test_forwards_noop_on_empty_db():
    _sync75.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_pr_field_within_limit():
    _sync75.add_new_items(RoadmapItem)
    assert all(len(i.pr) <= 64 for i in RoadmapItem.objects.all())


def test_depends_on_0073():
    assert _sync75.Migration.dependencies == [("roadmap", "0074_sync_items_2026_10_11")]


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
