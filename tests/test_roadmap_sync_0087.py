"""[ROADMAP] هجرةُ المزامنة 0087 حارسة: بنودُ إدارة الأجنحة الأربعة تُنشأ مرّةً واحدة ولا يُعاد كتابتُها."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync87 = importlib.import_module("roadmap.migrations.0087_sync_items_2026_11_19")

NEW_CODES = ["WNG-01", "WNG-02", "WNG-03", "WNG-04"]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed():
    RoadmapItem.objects.create(
        code="VI-60", lane="frontend", title="بندٌ قائم", status="todo", progress=0, note="قديم"
    )


def test_new_items_created_once_and_never_rewritten():
    assert _sync87.add_new_items(RoadmapItem) == NEW_CODES
    item = RoadmapItem.objects.get(code="WNG-04")
    assert (item.status, item.progress, item.src, item.pr) == ("done", 100, "WNG", "#1469")
    RoadmapItem.objects.filter(code="WNG-04").update(status="doing", progress=50)
    assert _sync87.add_new_items(RoadmapItem) == []
    item.refresh_from_db()
    assert (item.status, item.progress) == ("doing", 50)


def test_existing_code_is_skipped_not_overwritten():
    RoadmapItem.objects.create(code="WNG-02", lane="ops", title="سابق", status="todo", progress=0)
    assert _sync87.add_new_items(RoadmapItem) == ["WNG-01", "WNG-03", "WNG-04"]
    assert RoadmapItem.objects.get(code="WNG-02").title == "سابق"


def test_fields_fit_and_codes_unique():
    codes = [row[0] for row in _sync87.NEW_ITEMS]
    assert codes == NEW_CODES and len(set(codes)) == len(codes)
    assert all(len(row[10]) <= 64 for row in _sync87.NEW_ITEMS)
    assert all(len(row[9]) <= 120 for row in _sync87.NEW_ITEMS)
    assert all(row[5] == "done" and row[6] == 100 for row in _sync87.NEW_ITEMS)
    assert all(row[11].startswith("W-20261119-") for row in _sync87.NEW_ITEMS)


def test_note_states_what_was_and_was_not_measured():
    assert all("المقيس" in row[12] and "لم يُقَس" in row[12] for row in _sync87.NEW_ITEMS)


def test_public_text_has_no_local_paths_or_hosts():
    text = " ".join(str(v) for row in _sync87.NEW_ITEMS for v in row) + (_sync87.__doc__ or "")
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@"):
        assert bad not in text


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync87.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync87.forwards(_Apps, None)
    _sync87.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__in=NEW_CODES).count() == 4
    old = RoadmapItem.objects.get(code="VI-60")
    assert (old.status, old.progress, old.note) == ("todo", 0, "قديم")


def test_depends_on_0086():
    assert _sync87.Migration.dependencies == [("roadmap", "0086_sync_items_2026_11_16")]
