"""[ROADMAP] هجرةُ المزامنة 0092 حارسة: بندُ استمارة 19 يُنشأ مرّةً واحدة ولا يُعاد كتابتُه."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync92 = importlib.import_module("roadmap.migrations.0092_sync_items_2026_11_26")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed(code="WNG-01", pr="#1463"):
    RoadmapItem.objects.create(
        code=code, lane="product", title="بندٌ قائم", status="doing", progress=50, pr=pr
    )


def test_item_created_once_as_done_and_never_rewritten():
    assert _sync92.add_item(RoadmapItem) == "N-174"
    item = RoadmapItem.objects.get(code="N-174")
    assert (item.status, item.progress, item.pr) == ("done", 100, "#1520 #1521")
    assert str(item.end_date) == "2026-11-26" and "استمارة 19" in item.title
    RoadmapItem.objects.filter(code="N-174").update(status="doing", progress=50)
    assert _sync92.add_item(RoadmapItem) is None
    item.refresh_from_db()
    assert (item.status, item.progress) == ("doing", 50)


def test_a_taken_code_is_skipped():
    _seed(code="N-174")
    assert _sync92.add_item(RoadmapItem) == "N-175"
    assert RoadmapItem.objects.get(code="N-174").title == "بندٌ قائم"


@pytest.mark.parametrize("token", ["#1520", "#1521"])
def test_an_item_already_carrying_either_pr_is_not_duplicated(token):
    _seed(pr=token)
    assert _sync92.add_item(RoadmapItem) is None
    assert RoadmapItem.objects.count() == 1


def test_forwards_noop_on_empty_db_and_idempotent_after():
    _sync92.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0
    _seed()
    _sync92.forwards(_Apps, None)
    _sync92.forwards(_Apps, None)
    assert RoadmapItem.objects.filter(code__startswith="N-").count() == 1
    seeded = RoadmapItem.objects.get(code="WNG-01")
    assert (seeded.status, seeded.progress, seeded.note) == ("doing", 50, "")


def test_public_text_is_neutral_and_depends_on_0091():
    text = f"{_sync92.TITLE} {_sync92.CRITERION} {_sync92.NOTE} {_sync92.__doc__}"
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@", "8011"):
        assert bad not in text
    assert _sync92.Migration.dependencies == [("roadmap", "0091_sync_items_2026_11_24")]
