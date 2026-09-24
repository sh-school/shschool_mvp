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


# ── 0007: نظام أنماط التخطيط المركزيّة (LAY-01..07، LK1..5، D-16) ──

_sync7 = importlib.import_module("roadmap.migrations.0007_layout_system_items")


def test_0007_adds_lay_items_once_after_existing_order():
    _item("U-33", "todo", 0, sort_order=500)
    assert _sync7.add_items(RoadmapItem) == [f"LAY-0{n}" for n in range(1, 8)]
    assert _sync7.add_items(RoadmapItem) == []
    first = RoadmapItem.objects.get(code="LAY-01")
    assert (first.status, first.gate, first.sort_order) == ("todo", "owner", 501)
    assert first.date_basis.startswith("مقترَح")
    assert RoadmapItem.objects.get(code="LAY-07").lane == "desktop"


def test_0007_adds_kpis_and_open_decision_once():
    from roadmap.models import RoadmapDecision, RoadmapKpi

    assert _sync7.add_kpis(RoadmapKpi) == ["LK1", "LK2", "LK3", "LK4", "LK5"]
    assert _sync7.add_kpis(RoadmapKpi) == []
    lk3 = RoadmapKpi.objects.get(code="LK3")
    assert (lk3.baseline, lk3.target, lk3.direction) == (24.3, 100, "up")
    assert _sync7.add_decision(RoadmapDecision) == ["D-16"]
    assert _sync7.add_decision(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="D-16").status == "open"


def test_0007_annotates_once_without_touching_dates_or_status():
    from datetime import date

    _item("VI-24", "todo", 0, start_date=date(2026, 11, 2), end_date=date(2026, 12, 17))
    _item("U-33", "doing", 30, note="قديمة")
    assert _sync7.annotate(RoadmapItem) == ["U-33", "VI-24"]
    vi24 = RoadmapItem.objects.get(code="VI-24")
    assert (str(vi24.start_date), str(vi24.end_date)) == ("2026-11-02", "2026-12-17")
    assert "LAY-05" in vi24.note
    u33 = RoadmapItem.objects.get(code="U-33")
    assert (u33.status, u33.progress) == ("doing", 30)
    assert u33.note.startswith("قديمة\n[2026-09-23]")
    assert _sync7.annotate(RoadmapItem) == []


# ── 0008: Q-01/Q-02 وH-01 وحسمُ D-16 ودَينُ حجم CSS ──

_sync8 = importlib.import_module("roadmap.migrations.0008_sync_items_2026_09_24")


def test_0008_closes_the_merged_items_once():
    for code, status, progress in (
        ("Q-01", "doing", 60),
        ("H-01", "todo", 0),
        ("LAY-02", "todo", 0),
    ):
        _item(code, status, progress)
    assert _sync8.sync(RoadmapItem) == ["Q-01", "H-01", "LAY-02"]
    assert _sync8.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="H-01").pr == "#513"
    lay2 = RoadmapItem.objects.get(code="LAY-02")
    assert (lay2.status, lay2.progress, lay2.pr) == ("doing", 60, "")


def test_0008_does_not_close_lay01_before_its_pr_merges():
    assert "LAY-01" not in {u[0] for u in _sync8.UPDATES}


def test_0008_decides_d16_on_the_owners_date():
    from roadmap.models import RoadmapDecision

    RoadmapDecision.objects.create(code="D-16", title="أنماط التخطيط", status="open")
    assert _sync8.decide(RoadmapDecision) == ["D-16"]
    assert str(RoadmapDecision.objects.get(code="D-16").decision_date) == "2026-09-23"
    assert _sync8.decide(RoadmapDecision) == []


def test_0008_adds_the_css_debt_open_and_the_merged_work_closed():
    assert _sync8.add_missing(RoadmapItem) == ["DBT-36", "N-022", "N-023", "N-024", "N-025"]
    debt = RoadmapItem.objects.get(code="DBT-36")
    assert (debt.status, debt.end_date, debt.lane) == ("todo", None, "debt")
    assert RoadmapItem.objects.get(code="N-025").pr == "#512 #516"
    assert _sync8.add_missing(RoadmapItem) == []
