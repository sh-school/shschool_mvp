"""[ROADMAP] هجرةُ المزامنة 0088 حارسة: بندُ #1484 يُنشأ مرّةً واحدةً برمز N- شاغرٍ ولا يُعاد كتابتُه."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync88 = importlib.import_module("roadmap.migrations.0088_sync_items_2026_11_20")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="WNG-04", lane="ops", title="بندٌ قائم", status="todo", progress=0, note="قديم"
    )


def test_item_created_once_and_never_rewritten():
    assert _sync88.add_new_items(RoadmapItem) == ["N-169"]
    item = RoadmapItem.objects.get(code="N-169")
    assert (item.status, item.progress, item.src, item.lane, item.pr) == (
        "done",
        100,
        "N",
        "security",
        "#1484",
    )
    RoadmapItem.objects.filter(code="N-169").update(status="doing", progress=50)
    assert _sync88.add_new_items(RoadmapItem) == []
    item.refresh_from_db()
    assert (item.status, item.progress) == ("doing", 50)


def test_a_code_taken_by_the_page_is_skipped_to_the_next_free_one():
    RoadmapItem.objects.create(
        code="N-169", lane="ops", title="من الصفحة", status="todo", progress=0
    )
    RoadmapItem.objects.create(
        code="N-170", lane="ops", title="من الصفحة", status="todo", progress=0
    )
    assert _sync88.add_new_items(RoadmapItem) == ["N-171"]
    assert RoadmapItem.objects.get(code="N-169").title == "من الصفحة"


def test_an_item_already_carrying_the_pr_is_not_duplicated():
    RoadmapItem.objects.create(
        code="N-200", lane="security", title="أُضيف يدويّاً", status="done", progress=100, pr="#1484"
    )
    assert _sync88.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.filter(pr__contains="#1484").count() == 1


def test_fields_fit():
    row = _sync88.NEW_ITEM
    assert len(row[9]) <= 64 and len(row[8]) <= 120 and len(row[1]) <= 32
    assert (row[4], row[5]) == ("done", 100)


def test_note_states_what_was_and_was_not_measured():
    assert "المقيس" in _sync88.NEW_ITEM[11] and "لم يُقَس" in _sync88.NEW_ITEM[11]


def test_public_text_has_no_local_paths_or_hosts():
    text = " ".join(str(v) for v in _sync88.NEW_ITEM) + (_sync88.__doc__ or "")
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@", "8011"):
        assert bad not in text


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync88.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync88.forwards(_Apps, None)
    _sync88.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(pr="#1484").count() == 1
    old = RoadmapItem.objects.get(code="WNG-04")
    assert (old.status, old.progress, old.note) == ("todo", 0, "قديم")


def test_depends_on_0087():
    assert _sync88.Migration.dependencies == [("roadmap", "0087_sync_items_2026_11_19")]
