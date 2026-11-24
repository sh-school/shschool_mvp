"""[ROADMAP] هجرةُ المزامنة 0091 حارسة: البنود تُنشأ مرّةً واحدة والملاحظةُ لا تتكرّر ولا حالةَ تُلمس."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync91 = importlib.import_module("roadmap.migrations.0091_sync_items_2026_11_24")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed_wng():
    RoadmapItem.objects.create(
        code="WNG-01",
        lane="product",
        title="بندٌ قائم",
        status="done",
        progress=100,
        pr="#1463",
        note="قديم",
    )


def test_items_created_once_with_free_codes_and_never_rewritten():
    assert _sync91.add_new_items(RoadmapItem) == ["N-170", "N-171", "N-172", "N-173"]
    RoadmapItem.objects.filter(code="N-170").update(status="doing", progress=50)
    assert _sync91.add_new_items(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="N-170")
    assert (item.status, item.progress) == ("doing", 50)


def test_a_code_taken_by_the_page_is_skipped_to_the_next_free_one():
    RoadmapItem.objects.create(
        code="N-170", lane="ops", title="من الصفحة", status="todo", progress=0
    )
    assert _sync91.add_new_items(RoadmapItem)[0] == "N-171"
    assert RoadmapItem.objects.get(code="N-170").title == "من الصفحة"


def test_an_item_already_carrying_the_pr_is_not_duplicated():
    RoadmapItem.objects.create(
        code="N-200", lane="ops", title="يدويّ", status="done", progress=100, pr="#1505"
    )
    created = _sync91.add_new_items(RoadmapItem)
    assert len(created) == 3
    assert RoadmapItem.objects.filter(pr__contains="#1505").count() == 1


def test_note_added_once_and_status_untouched():
    _seed_wng()
    assert _sync91.sync_notes(RoadmapItem) == ["WNG-01"]
    assert _sync91.sync_notes(RoadmapItem) == []
    item = RoadmapItem.objects.get(code="WNG-01")
    assert item.note.count("#1508") == 1 and item.note.startswith("قديم")
    assert (item.status, item.progress) == ("done", 100)
    assert item.pr == "#1463 #1499 #1508"


def test_add_pr_respects_the_field_limit_and_dedupes():
    assert _sync91._add_pr("#1 #2", "#2 #3") == "#1 #2 #3"
    long_pr = " ".join(f"#{1000 + i}" for i in range(12))
    assert _sync91._add_pr(long_pr, "#9999") == long_pr


def test_every_requested_pr_is_registered_and_fields_fit():
    tokens = {t for row in _sync91.NEW_ITEMS for t in row[3].split()}
    tokens |= {t for _c, pr, _n in _sync91.NOTES for t in pr.split()}
    wanted = {"#1509", "#1510", "#1499", "#1508", "#1496", "#1497", "#1491", "#1495", "#1505"}
    assert wanted <= tokens
    for lane, _title, _crit, prs, note, _order in _sync91.NEW_ITEMS:
        assert len(prs) <= 64 and len(lane) <= 32
        assert "المقيس" in note and "لم يُقَس" in note


def test_public_text_has_no_local_paths_hosts_or_names():
    text = (
        " ".join(str(v) for v in _sync91.NEW_ITEMS)
        + " ".join(str(v) for v in _sync91.NOTES)
        + (_sync91.__doc__ or "")
    )
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@", "8011"):
        assert bad not in text


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync91.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed_wng()
    _sync91.forwards(_Apps, None)
    _sync91.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__startswith="N-").count() == 4
    assert RoadmapItem.objects.get(code="WNG-01").note.count("[2026-11-24]") == 1


def test_depends_on_0090():
    assert _sync91.Migration.dependencies == [("roadmap", "0090_sync_notes_2026_11_20")]
