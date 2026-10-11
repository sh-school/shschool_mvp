"""[ROADMAP] هجرةُ المزامنة 0074 حارسة: ثمانيةُ بنودٍ جديدة مرّةً واحدة، وملاحظاتٌ بلا لمس الحالة، ونصٌّ محايد لمستودعٍ عامّ."""

import importlib
import importlib.util

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_MOD = "roadmap.migrations.0074_sync_items_2026_10_11"
_sync74 = importlib.import_module(_MOD)
_CODES = ["N-113", "N-114", "N-115", "N-116", "N-117", "N-118", "N-119", "N-120"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    for code, status, progress in (
        ("SCH-22", "doing", 40),
        ("N-108", "doing", 55),
        ("N-106", "doing", 70),
    ):
        RoadmapItem.objects.create(code=code, lane="x", title="t", status=status, progress=progress)


def test_creates_eight_items_once():
    assert _sync74.add_new_items(RoadmapItem) == _CODES
    assert _sync74.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 8


def test_existing_item_is_never_rewritten():
    RoadmapItem.objects.create(
        code="N-115", lane="x", title="عدّله المطوّر", status="todo", note="يدوي"
    )
    assert "N-115" not in _sync74.add_new_items(RoadmapItem)
    item = RoadmapItem.objects.get(code="N-115")
    assert (item.title, item.status, item.note) == ("عدّله المطوّر", "todo", "يدوي")


def test_only_finished_work_is_closed_and_unstarted_stays_todo():
    _sync74.add_new_items(RoadmapItem)
    status = {i.code: (i.status, i.progress) for i in RoadmapItem.objects.all()}
    assert status["N-113"] == status["N-116"] == status["N-117"] == ("done", 100)
    assert status["N-118"] == status["N-119"] == ("todo", 0)
    assert status["N-114"][0] == status["N-115"][0] == status["N-120"][0] == "doing"
    assert status["N-115"][1] < 100


def test_notes_never_touch_status_or_progress_and_are_idempotent():
    _seed()
    _sync74.forwards(_Apps, None)
    _sync74.forwards(_Apps, None)
    for code, st, pr in (("SCH-22", "doing", 40), ("N-108", "doing", 55), ("N-106", "doing", 70)):
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress) == (st, pr)
        assert item.note.count("[2026-10-11]") == 1


def test_measurements_are_attributed_not_claimed_from_production():
    notes = {i[0]: i[15] for i in _sync74.NEW_ITEMS}
    assert "لم يُقَس أثرٌ على الإنتاج" in notes["N-113"]
    assert "المقيسُ محلّياً" in notes["N-114"]
    assert "غيرُ مقيس حيّاً" in notes["N-115"]
    assert "غيرُ متحقَّقة" in notes["N-120"] and "لا على بياناتٍ حيّة" in notes["N-120"]
    assert "لم يبدأ" in notes["N-118"] and "لم يبدأ" in notes["N-119"]


def test_forwards_noop_on_empty_db():
    _sync74.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_pr_field_within_limit():
    _sync74.add_new_items(RoadmapItem)
    assert all(len(i.pr) <= 64 for i in RoadmapItem.objects.all())


def test_depends_on_0073():
    assert _sync74.Migration.dependencies == [("roadmap", "0073_continuous_status")]


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
