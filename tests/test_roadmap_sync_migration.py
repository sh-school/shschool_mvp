"""[ROADMAP] هجرةُ المزامنة 0002 حارسةٌ: تُحدِّث ما لم يُمسّ وتترك ما عدّله المطوّر."""

import importlib

import pytest

from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

_sync = importlib.import_module("roadmap.migrations.0002_sync_items_with_merged_work")


def _item(code, status, progress, **kw):
    return RoadmapItem.objects.create(
        code=code, lane="x", title=kw.pop("title", "عنوان"), status=status, progress=progress, **kw
    )


def test_updates_untouched_item_and_appends_note():
    _item("U-07", "doing", 50, note="قديمة")
    assert _sync.sync(RoadmapItem) == ["U-07"]
    item = RoadmapItem.objects.get(code="U-07")
    assert (item.status, item.progress) == ("done", 100)
    assert item.note.startswith("قديمة\n") and "#445" in item.note


def test_developer_edit_is_preserved():
    _item("U-07", "doing", 70)
    assert _sync.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="U-07").progress == 70


def test_idempotent_and_noop_when_absent():
    assert _sync.sync(RoadmapItem) == []
    _item("VI-26", "doing", 50)
    _sync.sync(RoadmapItem)
    assert _sync.sync(RoadmapItem) == []


def test_title_swap_only_for_stale_text():
    _item(
        "DBT-06",
        "todo",
        0,
        title="اعتماديات: (أ) axes (#430 يفشل: جدول axes_accessattemptexpiration غير مصنَّف)",
    )
    _sync.sync(RoadmapItem)
    assert "#461" in RoadmapItem.objects.get(code="DBT-06").title


# ── 0003: مزامنة 2026-09-22 + بنودُ العمل المدموج بلا بند ──

_sync3 = importlib.import_module("roadmap.migrations.0003_sync_items_2026_09_22")


def test_0003_closes_untouched_item_with_pr():
    _item("H-02", "doing", 60, note="قديمة")
    assert _sync3.sync(RoadmapItem) == ["H-02"]
    item = RoadmapItem.objects.get(code="H-02")
    assert (item.status, item.progress, item.pr) == ("done", 100, "#423 #450")
    assert item.note.startswith("قديمة\n[2026-09-22]")


def test_0003_note_only_update_keeps_status_and_pr():
    _item("U-02", "doing", 50, pr="")
    _sync3.sync(RoadmapItem)
    item = RoadmapItem.objects.get(code="U-02")
    assert (item.status, item.progress, item.pr) == ("doing", 50, "")
    assert "#408 مدموج" in item.note


def test_0003_developer_edit_is_preserved():
    _item("DBT-19", "doing", 40)
    assert _sync3.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="DBT-19").progress == 40


def test_0003_adds_missing_items_once():
    _item("N-008", "doing", 10, title="أُنشئ يدوياً")
    created = _sync3.add_missing(RoadmapItem)
    assert "N-008" not in created and "N-012" in created
    assert RoadmapItem.objects.get(code="N-008").title == "أُنشئ يدوياً"
    new = RoadmapItem.objects.get(code="N-012")
    assert (new.status, new.progress, new.pr) == ("done", 100, "#481")
    assert _sync3.add_missing(RoadmapItem) == []


def test_0003_does_not_decide_d12():
    """الحسمُ للمالك: لا تحديثَ لـU-30 في الهجرة."""
    assert "U-30" not in {u[0] for u in _sync3.UPDATES}


def test_0003_note_only_update_is_idempotent():
    _item("U-02", "doing", 50)
    assert _sync3.sync(RoadmapItem) == ["U-02"]
    assert _sync3.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="U-02").note.count("#408") == 1


# ── 0004: مزامنة 2026-09-23 + حسمُ D-12 ──

_sync4 = importlib.import_module("roadmap.migrations.0004_sync_items_2026_09_23")


def test_0004_closes_u30_once():
    _item("U-30", "doing", 80)
    assert _sync4.sync(RoadmapItem) == ["U-30"]
    assert _sync4.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="U-30").status == "done"


def test_0004_decides_only_an_open_decision():
    from roadmap.models import RoadmapDecision

    RoadmapDecision.objects.create(code="D-12", title="قرارات المظهر", status="open")
    assert _sync4.decide(RoadmapDecision) == ["D-12"]
    d12 = RoadmapDecision.objects.get(code="D-12")
    assert (d12.status, str(d12.decision_date)) == ("decided", "2026-09-23")
    assert _sync4.decide(RoadmapDecision) == []


def test_0004_adds_n013():
    assert _sync4.add_missing(RoadmapItem) == ["N-013"]
    assert RoadmapItem.objects.get(code="N-013").pr == "#489"


# ── 0005: DBT-22 وN-014 ──

_sync5 = importlib.import_module("roadmap.migrations.0005_sync_items_2026_09_23b")


def test_0005_closes_dbt22_once_and_adds_n014():
    _item("DBT-22", "todo", 0)
    assert _sync5.sync(RoadmapItem) == ["DBT-22"]
    assert _sync5.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="DBT-22").pr == "#492"
    assert _sync5.add_missing(RoadmapItem) == ["N-014"]


# ── 0006: حزمةُ القياس والديونُ المحجوبة ──

_sync6 = importlib.import_module("roadmap.migrations.0006_sync_items_2026_09_23c")


def test_0006_closes_measurement_items_and_starts_the_half_done_ones():
    for code in ("M-00", "Q-03", "Q-01"):
        _item(code, "todo", 0)
    assert _sync6.sync(RoadmapItem) == ["M-00", "Q-03", "Q-01"]
    assert _sync6.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-00").status == "done"
    q1 = RoadmapItem.objects.get(code="Q-01")
    assert (q1.status, q1.progress) == ("doing", 60)


def test_0006_blocks_sentry_debts_instead_of_closing_them():
    _item("DBT-14", "todo", 0)
    _sync6.sync(RoadmapItem)
    item = RoadmapItem.objects.get(code="DBT-14")
    assert (item.status, item.pr) == ("blocked", "")
    assert "Sentry" in item.note


def test_0006_developer_edit_is_preserved():
    _item("DBT-13", "doing", 30)
    assert _sync6.sync(RoadmapItem) == []


def test_0006_adds_the_unrecorded_merged_work_once():
    created = _sync6.add_missing(RoadmapItem)
    assert created[0] == "N-015" and created[-1] == "N-021" and len(created) == 7
    assert _sync6.add_missing(RoadmapItem) == []


def test_0006_links_admin_work_to_the_owner_items():
    _sync6.add_missing(RoadmapItem)
    assert "OWN-27" in RoadmapItem.objects.get(code="N-019").note
    assert "OWN-22" in RoadmapItem.objects.get(code="N-021").note
