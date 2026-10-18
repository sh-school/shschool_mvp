"""[ROADMAP] هجرةُ 0078 حارسة: تصحيحُ N-117 وإكمالُ مرجع DBT-40/42 وملاحظاتُ التحفّظ بلا تغيير حالةٍ ولا تكرار."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_m = importlib.import_module("roadmap.migrations.0078_closed_items_verification_2026_10_15")


def _mk(code, **kw):
    kw.setdefault("lane", "x")
    kw.setdefault("title", "t")
    kw.setdefault("status", "done")
    return RoadmapItem.objects.create(code=code, **kw)


def test_n117_title_fixed_only_if_unchanged():
    _mk("N-117", title=_m.N117_OLD, criterion="قديم")
    assert _m.fix_n117(RoadmapItem) == ["N-117"]
    item = RoadmapItem.objects.get(code="N-117")
    assert (item.title, item.status) == (_m.N117_TITLE, "done")
    assert _m.fix_n117(RoadmapItem) == []


def test_n117_developer_edit_is_kept():
    _mk("N-117", title="عنوانٌ عدّله المطوّر")
    assert _m.fix_n117(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-117").title == "عنوانٌ عدّله المطوّر"


def test_references_completed_once_without_status_change():
    _mk("DBT-40", status="done")
    _mk("DBT-42", status="done")
    assert _m.complete_references(RoadmapItem) == ["DBT-40", "DBT-42"]
    item = RoadmapItem.objects.get(code="DBT-40")
    assert "#560" in item.pr and "DOCUMENTS_ONLY" in item.ref and item.status == "done"
    assert _m.complete_references(RoadmapItem) == []


def test_existing_reference_is_not_overwritten():
    _mk("DBT-42", ref="مرجعُ المطوّر")
    _m.complete_references(RoadmapItem)
    assert RoadmapItem.objects.get(code="DBT-42").ref == "مرجعُ المطوّر"


def test_reservations_are_notes_only_and_idempotent():
    for code in ("OWN-15", "OWN-21", "VI-25", "DBT-14"):
        _mk(code, status="done", progress=100)
    assert _m.add_reservations(RoadmapItem) == ["OWN-15", "OWN-21", "VI-25", "DBT-14"]
    assert _m.add_reservations(RoadmapItem) == []
    assert {i.status for i in RoadmapItem.objects.all()} == {"done"}


def test_forwards_noop_on_empty_db():
    _m.forwards(type("A", (), {"get_model": staticmethod(lambda *_: RoadmapItem)}), None)
    assert RoadmapItem.objects.count() == 0
