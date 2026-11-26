"""[ROADMAP] هجرةُ المزامنة 0093 حارسة: ما فات من قائمة المعلَّق يُسجَّل مرّةً واحدة بلا لمس الحالة."""

import importlib
import re

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync93 = importlib.import_module("roadmap.migrations.0093_sync_backlog_2026_11_26")

# أرقامُ «غير مذكورة (61)» من فرز قائمة المعلَّق
_BACKLOG = (
    "1405 1416 1418 1419 1420 1421 1423 1424 1425 1426 1427 1428 1429 1430 1431 1432 1434 1435 1436 "
    "1437 1438 1439 1440 1441 1442 1443 1444 1445 1446 1450 1452 1453 1454 1455 1456 1457 1458 1459 "
    "1460 1462 1467 1468 1471 1472 1473 1474 1476 1483 1485 1486 1488 1489 1490 1511 1512 1513 1514 "
    "1515 1516 1517 1522"
).split()

# (الرمز، رقمُ الطلب المميِّز) للبنود القائمة التي تُلحق بها الملاحظات
_EXISTING = [
    ("N-162", "#1253"),
    ("N-155", "#1236"),
    ("N-150", "#1125"),
    ("WNG-01", "#1463"),
    ("WNG-02", "#1464"),
    ("N-170", "#1509 #1510"),
    ("CLN-07", "#1265"),
    ("CLN-09", "#1269"),
    ("VI-60", "#1447"),
    ("N-164", "#1273"),
]


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem}[name]


def _seed(code, pr="", status="blocked", progress=30):
    RoadmapItem.objects.create(
        code=code,
        lane="product",
        title="بندٌ قائم",
        status=status,
        progress=progress,
        pr=pr,
        note="ملاحظةُ المطوّر",
    )


def _seed_existing():
    for code, pr in _EXISTING:
        _seed(code, pr)


def _run():
    _sync93.forwards(_Apps, None)


def test_apply_adds_notes_and_new_items():
    _seed_existing()
    _run()
    for code, _pr in _EXISTING:
        item = RoadmapItem.objects.get(code=code)
        assert _sync93.STAMP in item.note, code
        assert len(item.pr) <= 64
    new = RoadmapItem.objects.filter(code__in=[f"N-{n}" for n in range(175, 180)])
    assert new.count() == len(_sync93.NEW_ITEMS)
    assert all(len(i.date_basis) <= 120 and len(i.pr) <= 64 for i in new)
    asc = new.get(code="N-175")
    assert (asc.status, asc.progress, asc.end_date) == ("doing", 0, None)


def test_every_backlog_number_is_mentioned_or_excluded_with_a_reason():
    _seed_existing()
    _run()
    written = " ".join(RoadmapItem.objects.values_list("note", flat=True))
    mentioned = set(re.findall(r"#(\d{4})", written))
    excluded = {key.lstrip("#") for key, reason in _sync93.EXCLUDED.items() if reason.strip()}
    assert len(_BACKLOG) == len(set(_BACKLOG)) == 61
    assert not [n for n in _BACKLOG if n not in mentioned | excluded]
    assert not mentioned & excluded
    assert excluded <= set(_BACKLOG)


def test_second_run_changes_nothing():
    _seed_existing()
    _run()
    before = list(RoadmapItem.objects.order_by("code").values_list("code", "note", "pr"))
    _run()
    assert list(RoadmapItem.objects.order_by("code").values_list("code", "note", "pr")) == before


def test_developer_edits_are_kept():
    _seed_existing()
    _run()
    RoadmapItem.objects.filter(code="N-175").update(
        status="done", progress=100, title="عنوانُ المطوّر"
    )
    _run()
    for code, _pr in _EXISTING:
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress, item.title) == ("blocked", 30, "بندٌ قائم")
        assert item.note.startswith("ملاحظةُ المطوّر")
    edited = RoadmapItem.objects.get(code="N-175")
    assert (edited.status, edited.title) == ("done", "عنوانُ المطوّر")


def test_a_reused_n_code_is_not_annotated_and_taken_codes_are_skipped():
    # رمزٌ ولّدته الصفحةُ لعملٍ آخر: لا يحمل رقمَ الطلب المميِّز فلا يُلمس
    _seed("N-162")
    _seed("N-175")
    _run()
    assert RoadmapItem.objects.get(code="N-162").note == "ملاحظةُ المطوّر"
    assert RoadmapItem.objects.get(code="N-175").title == "بندٌ قائم"
    assert RoadmapItem.objects.filter(code="N-176").exists()


def test_empty_db_is_left_alone():
    _run()
    assert RoadmapItem.objects.count() == 0


def test_public_text_is_neutral_and_depends_on_0092():
    text = f"{_sync93.__doc__} {_sync93.NOTES} {_sync93.NEW_ITEMS} {_sync93.EXCLUDED}"
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@", "8011"):
        assert bad not in text
    assert not re.search(r"\d{11}|\b[0-9a-f]{40}\b", text)
    assert _sync93.Migration.dependencies == [("roadmap", "0092_sync_items_2026_11_26")]
