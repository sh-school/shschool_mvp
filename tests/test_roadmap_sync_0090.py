"""[ROADMAP] هجرةُ 0090 حارسة: ملاحظةُ #1487 على N-169 تُلحق مرّةً واحدةً ولا تلمس الحالة."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_m = importlib.import_module("roadmap.migrations.0090_sync_notes_2026_11_20")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _n169(pr="#1484", status="done"):
    return RoadmapItem.objects.create(
        code="N-169", lane="sec", title="بند", status=status, progress=100, pr=pr, note="قديم"
    )


def test_note_and_pr_added_once_without_touching_status():
    _n169(status="doing")
    _m.forwards(_Apps, None)
    _m.forwards(_Apps, None)
    item = RoadmapItem.objects.get(code="N-169")
    assert item.pr == "#1484 #1487"
    assert item.note.startswith("قديم\n[2026-11-20] اندمج #1487")
    assert item.note.count("اندمج #1487") == 1
    assert (item.status, item.progress, item.lane) == ("doing", 100, "sec")


def test_pr_field_left_alone_when_it_would_overflow():
    full = "#" + "9" * 62
    _n169(pr=full)
    _m.sync_notes(RoadmapItem)
    assert RoadmapItem.objects.get(code="N-169").pr == full


def test_missing_item_is_skipped():
    RoadmapItem.objects.create(code="X-1", lane="ops", title="آخر", status="todo", progress=0)
    assert _m.sync_notes(RoadmapItem) == []


def test_noop_on_empty_db():
    _m.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_note_states_what_was_measured():
    assert "المقيس" in _m.NOTES[0][2]


def test_public_text_has_no_local_paths_or_hosts():
    text = (_m.__doc__ or "") + " ".join(" ".join(row) for row in _m.NOTES)
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@", "8011"):
        assert bad not in text


def test_depends_on_0089():
    assert _m.Migration.dependencies == [("roadmap", "0089_fix_item_lanes_2026_11_20")]
