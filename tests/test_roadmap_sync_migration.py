"""[ROADMAP] هجرةُ المزامنة 0002 حارسةٌ: تُحدِّث ما لم يُمسّ وتترك ما عدّله المطوّر."""

import importlib

import pytest

from roadmap.models import RoadmapDecision, RoadmapItem, RoadmapKpi, RoadmapMeta

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


# ── 0009: LAY-01/LAY-02 بـ#517، وH-03 جزئيّاً، وM-11 ──

_sync9 = importlib.import_module("roadmap.migrations.0009_sync_items_2026_09_24b")


def test_0009_closes_the_layout_items_and_keeps_h03_open():
    for code, status, progress in (
        ("LAY-01", "todo", 0),
        ("LAY-02", "doing", 60),
        ("H-03", "doing", 30),
    ):
        _item(code, status, progress)
    assert _sync9.sync(RoadmapItem) == ["LAY-01", "LAY-02", "H-03"]
    assert _sync9.sync(RoadmapItem) == []
    h03 = RoadmapItem.objects.get(code="H-03")
    assert (h03.status, h03.progress) == ("doing", 70)
    assert RoadmapItem.objects.get(code="LAY-01").pr == "#517"


def test_0009_adds_the_nightly_fix_once():
    assert _sync9.add_missing(RoadmapItem) == ["N-026", "N-027", "N-028"]
    assert "#422" in RoadmapItem.objects.get(code="N-026").note
    assert _sync9.add_missing(RoadmapItem) == []


# ── 0010: بنودُ المالك من لقطة claude.ai ──

_sync10 = importlib.import_module("roadmap.migrations.0010_owner_items_from_snapshot")


def test_0010_brings_the_23_snapshot_items_once():
    created = _sync10.add_missing(RoadmapItem)
    assert len(created) == 23 and created[0] == "OWN-09" and created[-1] == "DONE-26"
    assert _sync10.add_missing(RoadmapItem) == []


def test_0010_closes_the_items_that_waited_for_477():
    _sync10.add_missing(RoadmapItem)
    for code in ("OWN-26", "OWN-27", "OWN-28"):
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress, item.pr) == ("done", 100, "#477")


def test_0010_closes_own20_done_since_298():
    _sync10.add_missing(RoadmapItem)
    own20 = RoadmapItem.objects.get(code="OWN-20")
    assert (own20.status, own20.pr) == ("done", "#298")


def test_0010_keeps_an_item_the_developer_added_first():
    _item("OWN-20", "doing", 40, title="أضافه المطوّر")
    _sync10.add_missing(RoadmapItem)
    assert RoadmapItem.objects.get(code="OWN-20").title == "أضافه المطوّر"


def test_0010_publishes_no_personal_number_nor_the_temporary_password_scheme():
    import json
    import re

    blob = json.dumps(_sync10.ITEMS, ensure_ascii=False)
    assert not re.findall(r"\d{5,}", blob)
    assert "AUg" not in blob


# ── 0011: #519 و#508 و#526، وثلاثةُ أعمالٍ بلا بند، وأوّلُ مؤشّراتٍ تُحدَّث في هجرة ──

_sync11 = importlib.import_module("roadmap.migrations.0011_sync_items_2026_09_24c")


def test_0011_moves_the_items_and_leaves_lay03_alone():
    for code in ("VI-28", "H-06", "VI-29", "OWN-19", "OWN-21", "M-07", "DBT-36", "LAY-03"):
        _item(code, "todo", 0)
    assert _sync11.sync(RoadmapItem) == [
        "VI-28",
        "H-06",
        "H-06",
        "VI-29",
        "OWN-19",
        "OWN-21",
        "M-07",
        "DBT-36",
    ]
    assert _sync11.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="VI-28").pr == "#519"
    h06 = RoadmapItem.objects.get(code="H-06")
    assert (h06.status, h06.progress, h06.pr) == ("done", 100, "#519 #529")
    assert "#519:" in h06.note and "#529" in h06.note
    own19 = RoadmapItem.objects.get(code="OWN-19")
    assert (own19.status, own19.progress, own19.pr) == ("doing", 90, "#526")
    vi29 = RoadmapItem.objects.get(code="VI-29")
    assert (vi29.status, vi29.pr) == ("todo", "") and "card-flow" in vi29.note
    lay03 = RoadmapItem.objects.get(code="LAY-03")
    assert (lay03.status, lay03.note) == ("todo", "")


def test_0011_adds_the_merged_work_once():
    assert _sync11.add_missing(RoadmapItem) == ["N-029", "N-030", "N-031"]
    assert RoadmapItem.objects.get(code="N-031").pr == "#514"
    assert _sync11.add_missing(RoadmapItem) == []


def _kpi(code, current, measured_at, **kw):
    return RoadmapKpi.objects.create(
        code=code,
        lane="frontend",
        name="مؤشّر",
        baseline=current,
        current=current,
        measured_at=measured_at,
        **kw,
    )


def test_0011_updates_an_untouched_kpi_and_keeps_both_points():
    _kpi("LK5", 1088.0, _sync11.KPI_MEASURED, source="scripts/x")
    assert _sync11.sync_kpis(RoadmapKpi) == ["LK5"]
    kpi = RoadmapKpi.objects.get(code="LK5")
    assert (kpi.current, kpi.baseline, kpi.measured_at) == (998.0, 1088.0, _sync11.DAY)
    assert kpi.history == [{"d": "2026-09-23", "v": 1088.0}, {"d": "2026-09-24", "v": 998.0}]
    assert "917a5bab" in kpi.source
    assert _sync11.sync_kpis(RoadmapKpi) == []


def test_0011_leaves_a_kpi_the_developer_remeasured():
    _kpi("LK2", 12.0, _sync11.DAY)
    assert _sync11.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="LK2").current == 12.0


def test_0011_records_lk2_back_at_nine_after_529():
    _kpi("LK2", 9.0, _sync11.KPI_MEASURED)
    assert _sync11.sync_kpis(RoadmapKpi) == ["LK2"]
    kpi = RoadmapKpi.objects.get(code="LK2")
    assert (kpi.current, kpi.measured_at) == (9.0, _sync11.DAY)
    assert "410aa186" in kpi.source


# ── 0012: خطّةُ إصلاح توليد الجدول (SCH-01..16، OWN-31، D-17، SK1..5) ──

_sync12 = importlib.import_module("roadmap.migrations.0012_schedule_generation_plan")


def test_0012_adds_the_plan_items_and_the_owner_item_once():
    created = _sync12.add_items(RoadmapItem)
    assert created == [f"SCH-{n:02d}" for n in range(1, 17)] + ["OWN-31"]
    assert _sync12.add_items(RoadmapItem) == []
    first = RoadmapItem.objects.get(code="SCH-01")
    assert (first.status, first.progress, first.pr, first.src) == ("doing", 60, "", "SCH")
    gate = RoadmapItem.objects.get(code="SCH-05")
    assert gate.gate == "owner" and "D-17" in gate.deps
    assert "#531" in RoadmapItem.objects.get(code="SCH-08").deps
    assert RoadmapItem.objects.get(code="OWN-31").gate == "owner"


def test_0012_keeps_an_item_the_developer_added_first():
    _item("SCH-01", "done", 100, title="أُنشئ يدوياً")
    assert "SCH-01" not in _sync12.add_items(RoadmapItem)
    assert RoadmapItem.objects.get(code="SCH-01").title == "أُنشئ يدوياً"


def test_0012_opens_d17_without_deciding_it():
    from roadmap.models import RoadmapDecision

    assert _sync12.add_decision(RoadmapDecision) == ["D-17"]
    assert _sync12.add_decision(RoadmapDecision) == []
    d17 = RoadmapDecision.objects.get(code="D-17")
    assert (d17.status, d17.decision_date, d17.blocks) == ("open", None, "SCH-05")


def test_0012_adds_the_kpis_with_their_first_measurement():
    assert _sync12.add_kpis(RoadmapKpi) == ["SK1", "SK2", "SK3", "SK4", "SK5"]
    assert _sync12.add_kpis(RoadmapKpi) == []
    sk1 = RoadmapKpi.objects.get(code="SK1")
    assert (sk1.current, sk1.target, sk1.direction) == (12.0, 0.0, "down")
    assert sk1.history == [{"d": "2026-09-24", "v": 12.0}]


# ── 0013: حسمُ D-17 وأثرُه، وOWN-19/OWN-22، وN-032 ──

_sync13 = importlib.import_module("roadmap.migrations.0013_sync_items_2026_09_24d")


def test_0013_decides_d17_once_and_records_the_owner_ruling():
    from roadmap.models import RoadmapDecision

    RoadmapDecision.objects.create(
        code="D-17", title="HC6", status="open", recommendation="(أ) تبقى."
    )
    assert _sync13.decide(RoadmapDecision) == ["D-17"]
    assert _sync13.decide(RoadmapDecision) == []
    d17 = RoadmapDecision.objects.get(code="D-17")
    assert (d17.status, str(d17.decision_date)) == ("decided", "2026-09-24")
    assert (
        d17.recommendation.startswith("(أ) تبقى.\n") and _sync13.OWNER_RULING in d17.recommendation
    )


def test_0013_leaves_a_decision_the_owner_already_took():
    from roadmap.models import RoadmapDecision

    RoadmapDecision.objects.create(code="D-17", title="HC6", status="decided")
    assert _sync13.decide(RoadmapDecision) == []


def test_0013_closes_the_admin_items_and_unblocks_sch05():
    _item("OWN-19", "doing", 90, pr="#526")
    _item("OWN-22", "todo", 0)
    _item("SCH-03", "doing", 5)
    _item("SCH-05", "doing", 0, gate="owner")
    _item("Q-12", "todo", 0)
    _item("Q-08", "todo", 0)
    assert _sync13.sync(RoadmapItem) == ["OWN-19", "OWN-22", "SCH-03", "SCH-05", "Q-12", "Q-08"]
    assert _sync13.sync(RoadmapItem) == []
    own19 = RoadmapItem.objects.get(code="OWN-19")
    assert (own19.status, own19.pr) == ("done", "#526 #533")
    sch05 = RoadmapItem.objects.get(code="SCH-05")
    assert (sch05.status, sch05.gate) == ("doing", "") and "D-17" in sch05.note
    sch03 = RoadmapItem.objects.get(code="SCH-03")
    assert (sch03.status, sch03.progress, sch03.gate) == ("doing", 5, "")
    q08 = RoadmapItem.objects.get(code="Q-08")
    assert (q08.status, q08.progress, q08.pr) == ("doing", 60, "#537")


def test_0013_adds_n032_closed_and_sch17_open():
    assert _sync13.add_missing(RoadmapItem) == ["N-032", "SCH-17", "SCH-18"]
    assert _sync13.add_missing(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-032").pr == "#531"
    sch17 = RoadmapItem.objects.get(code="SCH-17")
    assert (sch17.status, sch17.pr, str(sch17.end_date), sch17.src) == (
        "todo",
        "",
        "2026-09-26",
        "SCH",
    )
    assert (sch17.effort, sch17.deps) == (0.5, "D-17") and "break_at=never" in sch17.criterion


def test_0013_annotates_md9_only_when_already_decided():
    from roadmap.models import RoadmapDecision

    RoadmapDecision.objects.create(
        code="MD9", title="PWA", status="decided", recommendation="(ب) standalone."
    )
    assert _sync13.annotate_decisions(RoadmapDecision) == ["MD9"]
    assert _sync13.annotate_decisions(RoadmapDecision) == []
    assert "#537" in RoadmapDecision.objects.get(code="MD9").recommendation
    RoadmapDecision.objects.filter(code="MD9").update(status="open", recommendation="")
    assert _sync13.annotate_decisions(RoadmapDecision) == []


def test_0013_records_d18_decided_once_and_its_item():
    from roadmap.models import RoadmapDecision

    assert _sync13.add_decisions(RoadmapDecision) == ["D-18"]
    assert _sync13.add_decisions(RoadmapDecision) == []
    d18 = RoadmapDecision.objects.get(code="D-18")
    assert (d18.status, str(d18.decision_date)) == ("decided", "2026-09-24")
    assert _sync13.ADJACENCY_RULING in d18.recommendation
    _sync13.add_missing(RoadmapItem)
    sch18 = RoadmapItem.objects.get(code="SCH-18")
    assert (sch18.status, sch18.deps, sch18.sort_order) == ("todo", "D-18", 618)


def test_0013_leaves_a_d18_the_developer_wrote_first():
    from roadmap.models import RoadmapDecision

    RoadmapDecision.objects.create(code="D-18", title="كتبه المطوّر", status="open")
    assert _sync13.add_decisions(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="D-18").title == "كتبه المطوّر"


# ── 0014: ما دُمج بعد 0011، وقياساتُ المؤشّرات على main@be8be7cc ──

_sync14 = importlib.import_module("roadmap.migrations.0014_sync_items_2026_09_24e")


def test_0014_moves_the_merged_items_once():
    starts = {
        "LAY-03": ("todo", 0),
        "M-01": ("todo", 0),
        "H-04": ("todo", 0),
        "H-05": ("todo", 0),
        "M-03": ("todo", 0),
        "M-04": ("todo", 0),
        "OWN-24": ("todo", 0),
        "OWN-21": ("doing", 50),
        "OWN-19": ("done", 100),
        "DBT-36": ("todo", 0),
    }
    for code, (status, progress) in starts.items():
        _item(code, status, progress)
    assert _sync14.sync(RoadmapItem) == list(starts)
    assert _sync14.sync(RoadmapItem) == []
    got = {c: RoadmapItem.objects.get(code=c) for c in starts}
    assert (got["LAY-03"].status, got["LAY-03"].progress, got["LAY-03"].pr) == (
        "doing",
        50,
        "#532 #539 #543",
    )
    assert (got["LAY-03"].start_date, got["LAY-03"].gate) == (None, "")
    for code in ("M-01", "H-04", "H-05", "M-03", "OWN-24"):
        assert (got[code].status, got[code].progress) == ("done", 100), code
    assert got["H-05"].pr == got["H-04"].pr == got["M-03"].pr == "#549"
    assert (got["M-04"].status, got["M-04"].progress) == ("doing", 40)
    assert (got["OWN-21"].progress, got["OWN-21"].pr) == (60, "#508 #541")
    assert got["OWN-19"].pr == "#526 #533 #541" and "filter_horizontal" in got["OWN-19"].note
    assert "470KB" in got["DBT-36"].note


def test_0014_leaves_an_item_the_developer_moved():
    _item("M-04", "doing", 70)
    _item("OWN-21", "doing", 75)
    assert _sync14.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-04").progress == 70


def test_0014_adds_n033_closed_once():
    assert _sync14.add_missing(RoadmapItem) == ["N-033"]
    assert _sync14.add_missing(RoadmapItem) == []
    n033 = RoadmapItem.objects.get(code="N-033")
    assert (n033.status, n033.pr, n033.src) == ("done", "#546", "NEW")
    assert "D-19" in n033.note


def test_0014_replaces_todays_point_instead_of_adding_a_second_one():
    RoadmapKpi.objects.create(
        code="LK2",
        lane="frontend",
        name="حدود",
        baseline=9.0,
        current=9.0,
        measured_at=_sync14.DAY,
        history=[{"d": "2026-09-23", "v": 9.0}, {"d": "2026-09-24", "v": 9.0}],
    )
    RoadmapKpi.objects.create(
        code="LK1",
        lane="frontend",
        name="أنماط",
        baseline=0.0,
        current=0.0,
        measured_at=_sync14.DAY,
    )
    assert _sync14.sync_kpis(RoadmapKpi) == ["LK1", "LK2"]
    assert _sync14.sync_kpis(RoadmapKpi) == []
    lk2 = RoadmapKpi.objects.get(code="LK2")
    assert (lk2.current, lk2.baseline) == (5.0, 9.0)
    assert lk2.history == [{"d": "2026-09-23", "v": 9.0}, {"d": "2026-09-24", "v": 5.0}]
    assert "be8be7cc" in lk2.source


def test_0014_leaves_a_kpi_the_developer_remeasured():
    RoadmapKpi.objects.create(
        code="LK5",
        lane="frontend",
        name="أسطر",
        baseline=1088.0,
        current=970.0,
        measured_at=_sync14.DAY,
    )
    assert _sync14.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="LK5").current == 970.0


def test_0014_fills_the_text_mode_mobile_kpis_only_when_never_measured():
    for code in ("MK1", "MK2", "MK7", "MK18"):
        RoadmapKpi.objects.create(
            code=code, lane="mobile", name=code, text_mode=True, baseline_text="نصّ"
        )
    RoadmapKpi.objects.filter(code="MK2").update(current=3.0, measured_at=_sync14.DAY)
    assert _sync14.first_readings(RoadmapKpi) == ["MK1", "MK7", "MK18"]
    assert _sync14.first_readings(RoadmapKpi) == []
    mk1 = RoadmapKpi.objects.get(code="MK1")
    assert (mk1.current, mk1.unit, mk1.history) == (0.2, "pct", [{"d": "2026-09-24", "v": 0.2}])
    assert RoadmapKpi.objects.get(code="MK2").current == 3.0


def test_0014_opens_the_three_verified_debts_undated_and_without_a_pr():
    assert _sync14.add_open_debts(RoadmapItem) == ["DBT-37", "DBT-38", "DBT-39"]
    assert _sync14.add_open_debts(RoadmapItem) == []
    privacy = RoadmapItem.objects.get(code="DBT-37")
    assert (privacy.status, privacy.pr, privacy.start_date, privacy.lane) == (
        "todo",
        "",
        None,
        "sec",
    )
    assert "clean_photo" in privacy.criterion and "PDPPL" in privacy.title
    assert RoadmapItem.objects.get(code="DBT-39").sort_order == 468


def test_0014_leaves_a_debt_the_developer_wrote_first():
    _item("DBT-37", "doing", 30, title="كتبه المطوّر")
    assert _sync14.add_open_debts(RoadmapItem) == ["DBT-38", "DBT-39"]
    assert RoadmapItem.objects.get(code="DBT-37").title == "كتبه المطوّر"


def test_0014_records_d19_decided_once_and_leaves_a_developer_d19():
    from roadmap.models import RoadmapDecision

    assert _sync14.add_decisions(RoadmapDecision) == ["D-19"]
    assert _sync14.add_decisions(RoadmapDecision) == []
    d19 = RoadmapDecision.objects.get(code="D-19")
    assert (d19.status, str(d19.decision_date), d19.blocks) == ("decided", "2026-09-24", "N-033")
    RoadmapDecision.objects.filter(code="D-19").delete()
    RoadmapDecision.objects.create(code="D-19", title="كتبه المطوّر", status="open")
    assert _sync14.add_decisions(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="D-19").title == "كتبه المطوّر"


# ── 0015: خطّةُ الجدول بعد #548، وما دُمج بعد 0014 ──

_sync15 = importlib.import_module("roadmap.migrations.0015_sync_items_2026_09_24f")


def test_0015_closes_the_finished_plan_items_defers_sch06_and_keeps_sch08_open():
    starts = {
        "SCH-01": ("doing", 60),
        "SCH-02": ("doing", 10),
        "SCH-03": ("doing", 5),
        "SCH-04": ("doing", 0),
        "SCH-05": ("doing", 0),
        "SCH-06": ("todo", 0),
        "SCH-07": ("todo", 0),
        "SCH-08": ("todo", 0),
        "SCH-17": ("todo", 0),
        "SCH-18": ("todo", 0),
    }
    for code, (status, progress) in starts.items():
        _item(code, status, progress)
    assert _sync15.sync(RoadmapItem) == list(starts)
    assert _sync15.sync(RoadmapItem) == []
    got = {c: RoadmapItem.objects.get(code=c) for c in starts}
    for code in ("SCH-01", "SCH-02", "SCH-03", "SCH-04", "SCH-05", "SCH-07", "SCH-17", "SCH-18"):
        assert (got[code].status, got[code].progress, got[code].pr) == ("done", 100, "#548"), code
    assert (got["SCH-06"].status, got["SCH-06"].progress) == ("deferred", 80)
    assert "D-20" in got["SCH-06"].note and "D-17" in got["SCH-06"].note
    assert (got["SCH-08"].status, got["SCH-08"].progress) == ("doing", 90)
    assert "لا يُغلق" in got["SCH-08"].note


def test_0015_leaves_a_plan_item_the_owner_session_moved():
    _item("SCH-06", "doing", 95)
    _item("SCH-08", "done", 100)
    assert _sync15.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-06").progress == 95


def test_0015_closes_own21_and_stacks_two_notes_on_own19():
    _item("OWN-21", "doing", 60, pr="#508 #541")
    _item("OWN-19", "done", 100, pr="#526 #533 #541")
    assert _sync15.sync(RoadmapItem) == ["OWN-21", "OWN-19", "OWN-19"]
    assert _sync15.sync(RoadmapItem) == []
    own21 = RoadmapItem.objects.get(code="OWN-21")
    assert (own21.status, own21.progress, own21.pr) == ("done", 100, "#508 #541 #551")
    assert "ستّ صفحات" in own21.note
    own19 = RoadmapItem.objects.get(code="OWN-19")
    assert own19.pr == "#526 #533 #541 #545 #552"
    assert "permission_names" in own19.note and "كلمة المرور" in own19.note


def test_0015_adds_n034_closed_once():
    assert _sync15.add_missing(RoadmapItem) == ["N-034"]
    assert _sync15.add_missing(RoadmapItem) == []
    n034 = RoadmapItem.objects.get(code="N-034")
    assert (n034.status, n034.pr, n034.sort_order) == ("done", "#548", 469)


def test_0015_records_d20_decided_once_and_leaves_a_developer_d20():
    from roadmap.models import RoadmapDecision

    assert _sync15.add_decisions(RoadmapDecision) == ["D-20"]
    assert _sync15.add_decisions(RoadmapDecision) == []
    d20 = RoadmapDecision.objects.get(code="D-20")
    assert (d20.status, str(d20.decision_date), d20.blocks) == (
        "decided",
        "2026-09-24",
        "SCH-06، SCH-08",
    )
    RoadmapDecision.objects.filter(code="D-20").delete()
    RoadmapDecision.objects.create(code="D-20", title="كتبه المطوّر", status="open")
    assert _sync15.add_decisions(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="D-20").title == "كتبه المطوّر"


def test_0015_closes_dbt05_by_an_operation_not_a_pr():
    _item("DBT-05", "todo", 0)
    assert _sync15.sync(RoadmapItem) == ["DBT-05"]
    assert _sync15.sync(RoadmapItem) == []
    dbt05 = RoadmapItem.objects.get(code="DBT-05")
    assert (dbt05.status, dbt05.progress, dbt05.pr) == ("done", 100, "")
    assert "archive/wave3-f-2026-09-24" in dbt05.note


# ── 0016: اعتمادُ الجدول الجديد وقياسُه، و#555 و#563، وأربعةَ عشرَ ديناً ──

_sync16 = importlib.import_module("roadmap.migrations.0016_sync_items_2026_09_24g")


def test_0016_adds_notes_and_closes_dbt39_and_dbt37():
    starts = {
        "SCH-08": ("doing", 90),
        "DBT-39": ("todo", 0),
        "DBT-37": ("todo", 0),
        "OWN-09": ("done", 100),
        "OWN-22": ("done", 100),
        "SCH-11": ("todo", 0),
        "DBT-36": ("todo", 0),
        "Q-11": ("todo", 0),
        "VI-13": ("todo", 0),
    }
    for code, (status, progress) in starts.items():
        _item(code, status, progress)
    assert _sync16.sync(RoadmapItem) == list(starts)
    assert _sync16.sync(RoadmapItem) == []
    for code, (status, progress) in starts.items():
        item = RoadmapItem.objects.get(code=code)
        want = ("done", 100) if code in ("DBT-39", "DBT-37") else (status, progress)
        assert (item.status, item.progress) == want, code
    assert RoadmapItem.objects.get(code="DBT-39").pr == "#559"
    assert RoadmapItem.objects.get(code="DBT-37").pr == "#560"
    assert "c2dba53a" in RoadmapItem.objects.get(code="SCH-08").note
    assert "22.8%" in RoadmapItem.objects.get(code="SCH-11").note


def test_0016_adds_vi34_n036_n037_n038_closed_once():
    assert _sync16.add_missing(RoadmapItem) == ["VI-34", "N-036", "N-037", "N-038"]
    assert _sync16.add_missing(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-036").pr == "#563"
    assert RoadmapItem.objects.get(code="N-037").pr == "#547"
    n038 = RoadmapItem.objects.get(code="N-038")
    assert (n038.status, n038.pr, n038.lane) == ("done", "#562", "desktop")
    assert "لا يُوسَم منجزاً بصريّاً" in n038.note
    vi34 = RoadmapItem.objects.get(code="VI-34")
    assert (vi34.status, vi34.pr, vi34.lane, vi34.src) == ("done", "#555", "frontend", "VI")
    assert "js_icon_problems" in vi34.note


def test_0016_registers_the_fourteen_debts_two_closed_as_no_debt_and_one_by_565():
    assert _sync16.add_open_debts(RoadmapItem) == [f"DBT-{n}" for n in range(40, 54)]
    assert _sync16.add_open_debts(RoadmapItem) == []
    assert not RoadmapItem.objects.filter(code="DBT-37").exists()
    closed = {"DBT-40", "DBT-42", "DBT-41"}
    for i in RoadmapItem.objects.filter(code__in=[f"DBT-{n}" for n in range(40, 54)]):
        want = ("done", 100) if i.code in closed else ("todo", 0)
        pr = "#565" if i.code == "DBT-41" else ""
        assert (i.status, i.progress, i.pr, i.src) == (*want, pr, "DBT"), i.code
    assert RoadmapItem.objects.get(code="DBT-40").start_date == _sync16.DAY
    assert RoadmapItem.objects.get(code="DBT-44").start_date is None
    assert "DOCUMENTS_ONLY" in RoadmapItem.objects.get(code="DBT-40").note
    assert "أُغلق بـ#565" in RoadmapItem.objects.get(code="DBT-41").note
    assert "KNOWN_UNCLEANED" in RoadmapItem.objects.get(code="DBT-43").note


def test_0016_keeps_a_debt_the_developer_wrote_first():
    _item("DBT-44", "doing", 20, title="كتبه المطوّر")
    assert "DBT-44" not in _sync16.add_open_debts(RoadmapItem)
    assert RoadmapItem.objects.get(code="DBT-44").title == "كتبه المطوّر"


def test_0016_records_the_production_measurement_and_keeps_the_baseline():
    values = {"SK1": 12.0, "SK2": 98.2, "SK3": 17.9, "SK4": 26.0, "SK5": 0.0}
    for code, value in values.items():
        RoadmapKpi.objects.create(
            code=code,
            lane="backend",
            name=code,
            baseline=value,
            current=value,
            measured_at=_sync16.DAY,
            history=[{"d": "2026-09-24", "v": value}],
        )
    assert _sync16.sync_kpis(RoadmapKpi) == ["SK1", "SK2", "SK3", "SK4", "SK5"]
    assert _sync16.sync_kpis(RoadmapKpi) == []
    sk1 = RoadmapKpi.objects.get(code="SK1")
    assert (sk1.baseline, sk1.current) == (12.0, 7.0)
    assert sk1.history == [{"d": "2026-09-24", "v": 7.0}]
    assert RoadmapKpi.objects.get(code="SK3").current == 6.1
    assert RoadmapKpi.objects.get(code="SK5").current == 2.0


def test_0016_leaves_a_kpi_the_developer_remeasured():
    RoadmapKpi.objects.create(
        code="SK1", lane="backend", name="SK1", baseline=12.0, current=5.0, measured_at=_sync16.DAY
    )
    assert _sync16.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="SK1").current == 5.0


# ── 0017: خطّةُ إصلاح الهويّة (VI-35..53، VD1..8، V-K26..39، PK29) ──

_sync17 = importlib.import_module("roadmap.migrations.0017_identity_remediation_plan")


def test_0017_adds_the_nineteen_items_once_with_owner_gates_and_2027_dates():
    created = _sync17.add_items(RoadmapItem)
    assert created == [f"VI-{n}" for n in range(35, 54)]
    assert _sync17.add_items(RoadmapItem) == []
    vi36 = RoadmapItem.objects.get(code="VI-36")
    assert (vi36.status, vi36.gate, vi36.src) == ("todo", "owner", "VI")
    assert vi36.date_basis.startswith("مقترَح") and "VD1" in vi36.deps
    assert str(RoadmapItem.objects.get(code="VI-48").end_date) == "2027-01-28"
    assert RoadmapItem.objects.get(code="VI-49").lane == "quality"
    assert RoadmapItem.objects.get(code="VI-53").lane == "product"
    assert not RoadmapItem.objects.filter(code="VI-34").exists()


def test_0017_keeps_an_item_the_developer_wrote_first():
    _item("VI-40", "doing", 30, title="كتبه المطوّر")
    assert "VI-40" not in _sync17.add_items(RoadmapItem)
    assert RoadmapItem.objects.get(code="VI-40").title == "كتبه المطوّر"


def test_0017_opens_the_eight_decisions_without_deciding_any():
    from roadmap.models import RoadmapDecision

    assert _sync17.add_decisions(RoadmapDecision) == [f"VD{n}" for n in range(1, 9)]
    assert _sync17.add_decisions(RoadmapDecision) == []
    decisions = list(RoadmapDecision.objects.filter(code__startswith="VD"))
    assert all(
        (d.status, d.decision_date, d.decider) == ("open", None, "المالك") for d in decisions
    )
    assert RoadmapDecision.objects.get(code="VD1").blocks == "VI-36"
    assert RoadmapDecision.objects.get(code="VD2").due == "2026-11-05"


def test_0017_renumbers_the_kpis_and_records_the_two_measured_today():
    assert _sync17.add_kpis(RoadmapKpi) == [
        "V-K26", "V-K27", "V-K28", "V-K29", "V-K30", "V-K31", "V-K32", "V-K33", "V-K34", "V-K35",
        "V-K36", "V-K37", "V-K38", "V-K39", "PK29",
    ]  # fmt: skip
    assert _sync17.add_kpis(RoadmapKpi) == []
    k26 = RoadmapKpi.objects.get(code="V-K26")
    assert (k26.baseline, k26.current, k26.extra["plan_code"]) == (3.0, 0.0, "V-K24")
    assert k26.history == [{"d": "2026-09-24", "v": 0.0}]
    assert RoadmapKpi.objects.get(code="V-K28").measured_at is None
    assert RoadmapKpi.objects.get(code="V-K33").text_mode is True
    assert RoadmapKpi.objects.get(code="V-K39").extra["plan_code"] == "V-K38"
    pk29 = RoadmapKpi.objects.get(code="PK29")
    assert (pk29.baseline, pk29.target, pk29.extra["plan_code"]) == (7.1, 8.2, "PK1b")


def test_0017_does_not_create_the_kpi_that_already_exists_as_vk25():
    RoadmapKpi.objects.create(
        code="V-K25", lane="quality", name="لقطات", baseline=0.0, current=0.0, target=5.0
    )
    RoadmapKpi.objects.create(code="V-K26", lane="frontend", name="كتبه المطوّر", current=9.0)
    assert "V-K26" not in _sync17.add_kpis(RoadmapKpi)
    assert RoadmapKpi.objects.get(code="V-K26").name == "كتبه المطوّر"
    assert _sync17.sync_kpi_notes(RoadmapKpi) == ["V-K25"]
    assert _sync17.sync_kpi_notes(RoadmapKpi) == []
    assert "12 صفحةً" in RoadmapKpi.objects.get(code="V-K25").source


def test_0017_adds_notes_only_without_touching_status_or_dates():
    from datetime import date

    _item("LAY-05", "todo", 0, start_date=date(2026, 11, 16), end_date=date(2026, 11, 30))
    _item("VI-13", "todo", 0)
    _item("VI-25", "doing", 30)
    assert _sync17.sync_notes(RoadmapItem) == ["VI-13", "LAY-05"]
    assert _sync17.sync_notes(RoadmapItem) == []
    lay05 = RoadmapItem.objects.get(code="LAY-05")
    assert (lay05.status, str(lay05.start_date), str(lay05.end_date)) == (
        "todo",
        "2026-11-16",
        "2026-11-30",
    )
    assert "لم يُغيَّر موعدُه" in lay05.note
    assert RoadmapItem.objects.get(code="VI-25").note == ""


def test_0017_notes_that_562_already_did_part_of_vi36():
    _item("VI-36", "todo", 0)
    assert _sync17.sync_notes(RoadmapItem) == ["VI-36"]
    vi36 = RoadmapItem.objects.get(code="VI-36")
    assert (vi36.status, vi36.progress) == ("todo", 0)
    assert "#562" in vi36.note and "VD1" in vi36.note


# ── 0018: ما دُمج بعد دفع 0016 (#564 #566 #568 #569 #570 #553 #556 #573 #575 #576) ──

_sync18 = importlib.import_module("roadmap.migrations.0018_sync_items_2026_09_25")


def _seed18():
    """البنودُ كما تتركها 0016 و0017 على الإنتاج: حالتُها وطلباتُها."""
    for code, status, progress, pr in (
        ("SCH-14", "todo", 0, ""),
        ("SCH-15", "todo", 0, ""),
        ("SCH-11", "todo", 0, ""),
        ("DBT-43", "todo", 0, ""),
        ("DBT-44", "todo", 0, ""),
        ("DBT-50", "todo", 0, ""),
        ("DBT-51", "todo", 0, ""),
        ("DBT-36", "todo", 0, ""),
        ("VI-34", "done", 100, "#555"),
        ("N-033", "done", 100, "#546"),
        ("OWN-21", "done", 100, "#508 #541 #551"),
        ("OWN-19", "done", 100, "#526 #533 #541 #545 #552"),
    ):
        _item(code, status, progress, pr=pr)


def test_0018_closes_the_merged_plan_items_and_keeps_sch11_in_progress():
    _seed18()
    assert _sync18.sync(RoadmapItem) == [
        "SCH-14",
        "SCH-15",
        "SCH-11",
        "DBT-43",
        "DBT-44",
        "DBT-50",
        "DBT-51",
        "VI-34",
        "N-033",
        "OWN-21",
        "OWN-19",
        "OWN-19",
        "DBT-36",
    ]
    assert _sync18.sync(RoadmapItem) == []
    for code, pr in (
        ("SCH-14", "#564"),
        ("SCH-15", "#564"),
        ("DBT-43", "#575"),
        ("DBT-44", "#576"),
        ("DBT-50", "#566"),
        ("DBT-51", "#566"),
    ):
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress, item.pr) == ("done", 100, pr), code
    sch11 = RoadmapItem.objects.get(code="SCH-11")
    assert (sch11.status, sch11.progress, sch11.pr) == ("doing", 15, "#564")
    # نسبةُ 15% تقديرُ جلسة الجدولة لا قياس، والهدفُ لم يُبلَغ، والقياسُ ببذرةٍ واحدة.
    assert "تقديرُ جلسة الجدولة" in sch11.note and "لم يبلغه الوزنُ وحده" in sch11.note
    assert "ببذرةٍ واحدة" in sch11.note and "21.1%" in sch11.note
    assert "13 من 869" in RoadmapItem.objects.get(code="SCH-14").note
    assert "KNOWN_UNCLEANED" in RoadmapItem.objects.get(code="DBT-43").note


def test_0018_appends_pr_tokens_to_the_existing_field_not_over_it():
    _seed18()
    _sync18.sync(RoadmapItem)
    assert RoadmapItem.objects.get(code="VI-34").pr == "#555 #566"
    assert RoadmapItem.objects.get(code="N-033").pr == "#546 #568"
    assert RoadmapItem.objects.get(code="OWN-21").pr == "#508 #541 #551 #570"
    # OWN-19 يتلقّى ملاحظتين متتاليتين فتتراكم رموزُ طلباتهما بلا تكرار.
    assert RoadmapItem.objects.get(code="OWN-19").pr == "#526 #533 #541 #545 #552 #553 #556"
    assert _sync18._add_pr("#1 #2", "#2 #3") == "#1 #2 #3"


def test_0018_keeps_dbt36_open_and_states_only_the_measured_margin():
    _seed18()
    _sync18.sync(RoadmapItem)
    dbt36 = RoadmapItem.objects.get(code="DBT-36")
    assert (dbt36.status, dbt36.progress, dbt36.pr) == ("todo", 0, "")
    assert "468.85KB" in dbt36.note and "1.15KB" in dbt36.note


def test_0018_leaves_an_item_the_developer_moved():
    _item("SCH-14", "doing", 40)
    assert "SCH-14" not in _sync18.sync(RoadmapItem)
    assert (
        RoadmapItem.objects.get(code="SCH-14").status,
        RoadmapItem.objects.get(code="SCH-14").progress,
    ) == (
        "doing",
        40,
    )


def test_0018_does_not_touch_the_items_that_wait_for_their_own_pr():
    # DBT-53 ينتظر #572، وSCH-08 ينتظر تحقّقَ الأحد — فلا يُلمسان هنا.
    _item("DBT-53", "todo", 0)
    _item("SCH-08", "doing", 90)
    assert _sync18.sync(RoadmapItem) == []
    assert _sync18.add_debts(RoadmapItem) == ["DBT-54", "DBT-55"]
    assert (
        RoadmapItem.objects.get(code="DBT-53").status,
        RoadmapItem.objects.get(code="SCH-08").progress,
    ) == (
        "todo",
        90,
    )


def test_0018_adds_n039_and_n040_closed_once_and_keeps_a_developer_item():
    assert _sync18.add_missing(RoadmapItem) == ["N-039", "N-040"]
    assert _sync18.add_missing(RoadmapItem) == []
    n039 = RoadmapItem.objects.get(code="N-039")
    assert (n039.status, n039.progress, n039.pr, n039.lane, n039.src) == (
        "done",
        100,
        "#568",
        "backend",
        "NEW",
    )
    # القياسُ بالاختبارات لا بفحصٍ إنتاجيّ، وما بقي مفتوحاً مذكور.
    assert "لا بفحصٍ إنتاجيّ حيّ" in n039.note and "expire_overdue" in n039.note
    n040 = RoadmapItem.objects.get(code="N-040")
    assert (n040.status, n040.pr, n040.lane) == ("done", "#569", "sec")
    assert "لم يُفحص" in n040.note
    RoadmapItem.objects.all().delete()
    _item("N-039", "doing", 30, title="كتبه المطوّر")
    assert "N-039" not in _sync18.add_missing(RoadmapItem)
    assert RoadmapItem.objects.get(code="N-039").title == "كتبه المطوّر"


def test_0018_registers_dbt54_closed_by_573_and_dbt55_open_behind_the_owner_gate():
    assert _sync18.add_debts(RoadmapItem) == ["DBT-54", "DBT-55"]
    assert _sync18.add_debts(RoadmapItem) == []
    dbt54 = RoadmapItem.objects.get(code="DBT-54")
    assert (dbt54.status, dbt54.progress, dbt54.pr, dbt54.src) == ("done", 100, "#573", "DBT")
    assert dbt54.start_date == _sync18.DAY and "ast.dump" in dbt54.note
    dbt55 = RoadmapItem.objects.get(code="DBT-55")
    assert (dbt55.status, dbt55.progress, dbt55.pr, dbt55.gate) == ("todo", 0, "", "owner")
    assert dbt55.start_date is None and dbt55.date_basis == "غير مجدول"
    # الرقمُ 2px تقديرٌ لا قياس، والفارقُ الثامنُ غيرُ محسوم — يُقالان صراحةً.
    assert "تقديرٌ لا قياس" in dbt55.note and "غيرُ محسوم" in dbt55.note
    assert (
        RoadmapItem.objects.get(code="DBT-54").sort_order
        < RoadmapItem.objects.get(code="DBT-55").sort_order
    )


def test_0018_keeps_a_debt_the_developer_wrote_first():
    _item("DBT-55", "doing", 20, title="كتبه المطوّر")
    assert "DBT-55" not in _sync18.add_debts(RoadmapItem)
    assert RoadmapItem.objects.get(code="DBT-55").title == "كتبه المطوّر"


def test_0018_opens_d21_for_discussion_and_never_decides_it():
    assert _sync18.add_decisions(RoadmapDecision) == ["D-21"]
    assert _sync18.add_decisions(RoadmapDecision) == []
    d21 = RoadmapDecision.objects.get(code="D-21")
    assert (d21.status, d21.decider, d21.decision_date, d21.src) == ("open", "المالك", None, "OWN")
    # موافقةُ المالك منقولةٌ من جلسةٍ أخرى لا مؤكَّدةٌ هنا: يُقال ذلك، ويُنسب العملُ لصاحبته 8061 لا 8033.
    assert "مفتوحاً للنقاش" in d21.recommendation and "8061" in d21.recommendation
    assert "نفت" in d21.recommendation and "2026-09-27" in d21.recommendation
    assert d21.sort_order == _sync18.DECISIONS_FIRST_ORDER == 127


def test_0018_keeps_a_d21_the_owner_already_decided():
    RoadmapDecision.objects.create(code="D-21", title="حسمه المالك", status="decided")
    assert _sync18.add_decisions(RoadmapDecision) == []
    d21 = RoadmapDecision.objects.get(code="D-21")
    assert (d21.status, d21.title) == ("decided", "حسمه المالك")


def test_0018_registers_no_item_for_the_weekly_schedule_prs_before_they_merge():
    prs = [row[4] for row in _sync18.UPDATES] + [row[3] for row in _sync18.NEW_ITEMS]
    assert not any("#577" in pr for pr in prs)
    assert "#577" not in _sync18.CLOSED_BY_PR.values()


def test_0018_does_nothing_on_an_empty_database():
    class _Apps:
        @staticmethod
        def get_model(_app, name):
            return RoadmapDecision if name == "RoadmapDecision" else RoadmapItem

    _sync18.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_0018_forwards_is_idempotent_on_a_seeded_database():
    class _Apps:
        @staticmethod
        def get_model(_app, name):
            return RoadmapDecision if name == "RoadmapDecision" else RoadmapItem

    _seed18()
    _sync18.forwards(_Apps, None)
    snapshot = list(
        RoadmapItem.objects.order_by("code").values_list("code", "status", "progress", "pr", "note")
    )
    _sync18.forwards(_Apps, None)
    assert (
        list(
            RoadmapItem.objects.order_by("code").values_list(
                "code", "status", "progress", "pr", "note"
            )
        )
        == snapshot
    )
    assert {"N-039", "N-040", "DBT-54", "DBT-55"} <= {code for code, *_ in snapshot}


def test_0018_publishes_no_personal_number_nor_the_temporary_password_scheme():
    text = importlib.util.find_spec("roadmap.migrations.0018_sync_items_2026_09_25").origin
    body = open(text, encoding="utf-8").read()
    # المستودعُ عامّ: لا رقمَ شخصيٍّ ولا نمطَ كلمةِ مرورٍ مؤقّتة في هجرةٍ متتبَّعة.
    assert not __import__("re").search(r"\b\d{11}\b", body)
    assert "كلمة المرور المؤقتة" not in body and "Temp@" not in body


# ── 0019: قراراتُ المالك على VD1..VD8 (2026-09-25) وVI-54 و#571 وN-041 ──

_sync19 = importlib.import_module("roadmap.migrations.0019_owner_decisions_vd_2026_09_25")


class _Apps19:
    @staticmethod
    def get_model(_app, name):
        return RoadmapDecision if name == "RoadmapDecision" else RoadmapItem


def _open_vd(*codes):
    for code in codes or [f"VD{n}" for n in range(1, 9)]:
        RoadmapDecision.objects.create(
            code=code, title=f"قرار {code}", status="open", recommendation="توصية"
        )


def test_0019_decides_all_eight_vd_decisions_including_vd3_and_the_modified_vd4():
    _open_vd()
    assert _sync19.decide(RoadmapDecision) == [f"VD{n}" for n in range(1, 9)]
    assert _sync19.decide(RoadmapDecision) == []
    for code in (f"VD{n}" for n in range(1, 9)):
        d = RoadmapDecision.objects.get(code=code)
        assert (d.status, d.decision_date) == ("decided", _sync19.DAY), code


def test_0019_states_that_a_decision_is_not_an_implementation():
    _open_vd()
    _sync19.decide(RoadmapDecision)
    for code in ("VD1", "VD5", "VD6", "VD7", "VD8"):
        rec = RoadmapDecision.objects.get(code=code).recommendation
        assert "محسومة قرارا ولكن يجب العمل عليها" in rec and "قرارٌ لا تنفيذ" in rec, code
    vd2 = RoadmapDecision.objects.get(code="VD2").recommendation
    assert "أكّده لجلسة الخارطة مباشرةً" in vd2 and "الشطرُ الثاني من VI-37" in vd2
    vd3 = RoadmapDecision.objects.get(code="VD3").recommendation
    assert "لا مراسلةَ لـGCO ولا للوزارة ولا لأحد" in vd3 and "اتّساقٌ لا التزام" in vd3
    # VD4 يحلّ نطاقُه المعدَّل محلَّ توصيته السابقة، وهو قرارٌ لا تنفيذ (VI-11 يبقى مفتوحاً).
    vd4 = RoadmapDecision.objects.get(code="VD4").recommendation
    assert "يحلّ محلّ التوصية السابقة" in vd4 and "بلا فلتر تبييض" in vd4 and "قرارٌ لا تنفيذ" in vd4


def test_0019_keeps_a_decision_the_owner_already_took_or_deferred():
    RoadmapDecision.objects.create(
        code="VD1", title="x", status="decided", recommendation="حسمه المالك"
    )
    RoadmapDecision.objects.create(code="VD5", title="x", status="deferred", recommendation="أجّله")
    assert _sync19.decide(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="VD1").recommendation == "حسمه المالك"
    assert RoadmapDecision.objects.get(code="VD5").status == "deferred"


def test_0019_adds_notes_without_touching_status_or_dates():
    from datetime import date

    _item("LAY-05", "todo", 0, start_date=date(2026, 11, 16), end_date=date(2026, 11, 30))
    for code in ("VI-36", "VI-37", "VI-11", "VI-38", "VI-39", "VI-53", "DBT-36"):
        _item(code, "todo", 0)
    assert _sync19.sync_notes(RoadmapItem) == [
        "VI-36",
        "VI-37",
        "VI-11",
        "VI-38",
        "VI-39",
        "VI-53",
        "LAY-05",
        "DBT-36",
    ]
    assert _sync19.sync_notes(RoadmapItem) == []
    lay05 = RoadmapItem.objects.get(code="LAY-05")
    assert (lay05.status, str(lay05.start_date), str(lay05.end_date)) == (
        "todo",
        "2026-11-16",
        "2026-11-30",
    )
    assert "لم يُغيَّر موعدُه" in lay05.note
    assert "الشطرُ الثاني" in RoadmapItem.objects.get(code="VI-37").note
    # VI-11: VD4 محسومٌ قراراً لا تنفيذاً، وما تحقّقتُ منه في المستودع يُميَّز عمّا نُقل ولم يُقَس.
    vi11 = RoadmapItem.objects.get(code="VI-11")
    assert (
        "logoMaroon.png" in vi11.note
        and "بنقل 8104 ولم أقِسه" in vi11.note
        and "قرارٌ لا تنفيذ" in vi11.note
    )
    assert vi11.status == "todo"


def test_0019_leaves_an_item_the_developer_moved():
    _item("VI-36", "doing", 30)
    assert "VI-36" not in _sync19.sync_notes(RoadmapItem)
    assert RoadmapItem.objects.get(code="VI-36").note == ""


def test_0019_notes_571_on_own19_as_published_and_applied_with_the_measured_numbers():
    _item("OWN-19", "done", 100, pr="#526 #533 #541 #545 #552 #553 #556")
    assert _sync19.sync(RoadmapItem) == ["OWN-19"]
    assert _sync19.sync(RoadmapItem) == []
    own19 = RoadmapItem.objects.get(code="OWN-19")
    assert (own19.status, own19.progress) == ("done", 100)
    assert own19.pr == "#526 #533 #541 #545 #552 #553 #556 #571"
    # نُشر وطُبّق بتأكيد المالك المباشر: القياسُ الفعليّ بعد النشر لا التقدير، والهجرةُ لا رجوعَ لها.
    assert "لا رجوع لها" in own19.note and "منشورٌ ومطبَّق على الإنتاج" in own19.note
    assert (
        "600 ← 592" in own19.note
        and "16 لحسابَي مستخدمَين" in own19.note
        and "0 للمجموعات" in own19.note
    )
    assert "بتأكيد المالك المباشر" in own19.note
    # لا يبقى في الملاحظة أنّه «لا منشور» ولا أنّه ينتظر تأكيداً.
    assert "مدموجٌ لا منشور" not in own19.note and "لا يُنشر إلا" not in own19.note


def test_0019_leaves_own19_the_developer_moved():
    _item("OWN-19", "doing", 70)
    assert _sync19.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="OWN-19").note == ""


def test_0019_registers_the_weekly_schedule_as_in_progress_one_of_three_never_closed():
    assert _sync19.add_in_progress(RoadmapItem) == ["N-041"]
    assert _sync19.add_in_progress(RoadmapItem) == []
    n041 = RoadmapItem.objects.get(code="N-041")
    assert (n041.status, n041.progress, n041.pr, n041.lane, n041.src) == (
        "doing",
        33,
        "#577",
        "backend",
        "NEW",
    )
    assert n041.start_date == _sync19.DAY and n041.end_date is None
    # عدُّ طلباتٍ لا جهد، ولا واجهةَ فيه، وقيدُ النشر قبل تحقّق الأحد، وD-21 مفتوح.
    assert "1/3" in n041.note and "لا يُغلق" in n041.note and "لا واجهةَ فيه" in n041.note
    # نُشر بلا أثرٍ مرئيّ، وتحقّقُه بالاختبارات لا بفحصٍ إنتاجيٍّ حيّ.
    assert "دُمج ونُشر على الإنتاج" in n041.note and "لم يُؤكَّد بعد" not in n041.note
    assert "2026-09-27" in n041.criterion and "D-21 مفتوحٌ للنقاش" in n041.note


def test_0019_keeps_an_n041_the_developer_wrote_first():
    _item("N-041", "todo", 0, title="كتبه المطوّر")
    assert _sync19.add_in_progress(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-041").title == "كتبه المطوّر"


def test_0019_registers_vi54_proposed_open_undated_and_gated():
    assert _sync19.add_items(RoadmapItem) == ["VI-54"]
    assert _sync19.add_items(RoadmapItem) == []
    vi54 = RoadmapItem.objects.get(code="VI-54")
    assert (vi54.status, vi54.progress, vi54.gate, vi54.src, vi54.lane) == (
        "todo",
        0,
        "owner",
        "VI",
        "frontend",
    )
    assert vi54.start_date is None and vi54.end_date is None and vi54.effort == 0.5
    assert (
        vi54.deps == "VD2" and "بنداً مقترَحاً مفتوحاً" in vi54.note and "إذنَه قبل التنفيذ" in vi54.note
    )


def test_0019_keeps_a_vi54_the_developer_wrote_first():
    _item("VI-54", "doing", 20, title="كتبه المطوّر")
    assert _sync19.add_items(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="VI-54").title == "كتبه المطوّر"


def test_0019_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync19.forwards(_Apps19, None)
    assert RoadmapItem.objects.count() == 0 and RoadmapDecision.objects.count() == 0
    _open_vd()
    _item("VI-37", "todo", 0)
    _sync19.forwards(_Apps19, None)
    rows = list(
        RoadmapDecision.objects.order_by("code").values_list("code", "status", "recommendation")
    )
    items = list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note"))
    _sync19.forwards(_Apps19, None)
    assert (
        list(
            RoadmapDecision.objects.order_by("code").values_list("code", "status", "recommendation")
        )
        == rows
    )
    assert list(RoadmapItem.objects.order_by("code").values_list("code", "status", "note")) == items
    assert {code for code, *_ in items} == {"VI-37", "N-041", "VI-54"}


def test_0019_publishes_no_personal_number_nor_the_temporary_password_scheme():
    import re

    origin = importlib.util.find_spec(
        "roadmap.migrations.0019_owner_decisions_vd_2026_09_25"
    ).origin
    body = open(origin, encoding="utf-8").read()
    # المستودعُ عامّ: لا رقمَ شخصيٍّ ولا نمطَ كلمةِ مرورٍ مؤقّتة في هجرةٍ متتبَّعة.
    assert not re.search(r"\b\d{11}\b", body)
    assert "كلمة المرور المؤقتة" not in body and "Temp@" not in body


# ── 0020: عائلةُ REP — خطّةُ إصلاح Git والمستودع (2026-09-25) ──

_sync20 = importlib.import_module("roadmap.migrations.0020_git_repo_remediation_plan")


class _Apps20:
    @staticmethod
    def get_model(_app, name):
        from roadmap.models import RoadmapRisk

        return {
            "RoadmapDecision": RoadmapDecision,
            "RoadmapKpi": RoadmapKpi,
            "RoadmapRisk": RoadmapRisk,
        }.get(name, RoadmapItem)


def test_0020_adds_the_23_rep_items_proposed_todo_and_never_closed():
    assert _sync20.add_items(RoadmapItem) == [f"REP-{n:02d}" for n in range(1, 24)]
    assert _sync20.add_items(RoadmapItem) == []
    items = list(RoadmapItem.objects.filter(src="REP").order_by("sort_order"))
    assert len(items) == 23
    assert all((i.status, i.progress, i.src) == ("todo", 0, "REP") for i in items)
    assert all(
        "لم يعتمده المالك" in i.date_basis and i.ref.startswith("shschool-docs") for i in items
    )
    assert all(i.start_date is not None and i.end_date >= i.start_date for i in items)
    assert [i.sort_order for i in items] == list(range(701, 724))
    # بوّابةُ المالك على ما يتوقّف على إذنه أو قراره أو إعدادات حسابه.
    gated = {i.code for i in items if i.gate == "owner"}
    assert {"REP-02", "REP-03", "REP-05", "REP-12", "REP-13", "REP-15", "REP-16"} <= gated
    assert "REP-01" not in gated and "REP-07" not in gated


def test_0020_keeps_a_rep_item_the_developer_wrote_first():
    _item("REP-01", "doing", 40, title="كتبه المطوّر")
    assert "REP-01" not in _sync20.add_items(RoadmapItem)
    assert RoadmapItem.objects.get(code="REP-01").title == "كتبه المطوّر"


def test_0020_adds_the_eleven_kpis_with_a_measured_baseline_only_where_one_exists():
    assert _sync20.add_kpis(RoadmapKpi) == [f"RK{n}" for n in range(1, 12)]
    assert _sync20.add_kpis(RoadmapKpi) == []
    rk1 = RoadmapKpi.objects.get(code="RK1")
    assert (rk1.baseline, rk1.current, rk1.target, rk1.direction) == (287.0, 287.0, 40.0, "down")
    assert rk1.history == [{"d": "2026-09-25", "v": 287.0}] and rk1.measured_at == _sync20.DAY
    # RK4 وRK5 بلا أساسٍ رقميٍّ إلى أن تُبنى أداتاهما: لا قياسَ مختلَق.
    for code in ("RK4", "RK5"):
        k = RoadmapKpi.objects.get(code=code)
        assert (k.baseline, k.current, k.measured_at, k.history) == (None, None, None, [])
        assert k.baseline_text
    assert RoadmapKpi.objects.get(code="RK9").direction == "up"
    assert RoadmapKpi.objects.get(code="RK11").baseline == 4.0
    orders = [
        k.sort_order
        for k in RoadmapKpi.objects.filter(code__startswith="RK").order_by("sort_order")
    ]
    assert orders == list(range(432, 443))


def test_0020_opens_the_eight_decisions_without_deciding_any():
    assert _sync20.add_decisions(RoadmapDecision) == [f"RD{n}" for n in range(1, 9)]
    assert _sync20.add_decisions(RoadmapDecision) == []
    decisions = list(RoadmapDecision.objects.filter(src="REP"))
    assert len(decisions) == 8
    assert all(
        (d.status, d.decision_date, d.decider) == ("open", None, "المالك") for d in decisions
    )
    assert min(d.sort_order for d in decisions) == 128


def test_0020_keeps_a_decision_the_owner_already_took():
    RoadmapDecision.objects.create(
        code="RD3", title="x", status="decided", recommendation="حسمه المالك"
    )
    assert "RD3" not in _sync20.add_decisions(RoadmapDecision)
    assert RoadmapDecision.objects.get(code="RD3").recommendation == "حسمه المالك"


def test_0020_adds_the_eight_risks_once():
    from roadmap.models import RoadmapRisk

    assert _sync20.add_risks(RoadmapRisk) == [f"RR{n}" for n in range(1, 9)]
    assert _sync20.add_risks(RoadmapRisk) == []
    assert min(r.sort_order for r in RoadmapRisk.objects.filter(code__startswith="RR")) == 19


def test_0020_adds_notes_only_and_never_touches_u02_u03_or_dates():
    from datetime import date

    for code, status, progress in (
        ("U-01", "todo", 0),
        ("U-17", "todo", 0),
        ("U-19", "todo", 0),
        ("U-34", "todo", 0),
        ("VI-52", "todo", 0),
        ("U-02", "doing", 50),
        ("U-03", "todo", 0),
    ):
        _item(code, status, progress, start_date=date(2026, 9, 21), end_date=date(2026, 9, 25))
    assert _sync20.sync_notes(RoadmapItem) == ["U-01", "U-17", "U-19", "U-34", "VI-52"]
    assert _sync20.sync_notes(RoadmapItem) == []
    for code in ("U-02", "U-03"):
        # تعديلُهما ينتظر قرارَ المالك RD3 المباشر: لا ملاحظةَ ولا حالةَ ولا تاريخ.
        item = RoadmapItem.objects.get(code=code)
        assert (
            item.note == ""
            and str(item.start_date) == "2026-09-21"
            and str(item.end_date) == "2026-09-25"
        )
    for code in ("U-01", "U-17", "U-19", "U-34", "VI-52"):
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress) == ("todo", 0) and str(
            item.end_date
        ) == "2026-09-25", code
    assert "railway-predeploy.sh" in RoadmapItem.objects.get(code="U-19").note


def test_0020_leaves_an_item_the_developer_moved():
    _item("U-01", "doing", 30)
    assert "U-01" not in _sync20.sync_notes(RoadmapItem)
    assert RoadmapItem.objects.get(code="U-01").note == ""


def test_0020_annotates_uk7_once_within_the_field_limit_and_keeps_its_baseline():
    RoadmapKpi.objects.create(
        code="UK7",
        lane="sec",
        name="سجلّ",
        baseline=None,
        current=None,
        source="الخطّة الموحّدة K7",
        text_mode=True,
    )
    assert _sync20.sync_kpi_notes(RoadmapKpi) == ["UK7"]
    assert _sync20.sync_kpi_notes(RoadmapKpi) == []
    uk7 = RoadmapKpi.objects.get(code="UK7")
    assert "RK4" in uk7.source and len(uk7.source) <= 255
    assert (uk7.baseline, uk7.current, uk7.text_mode) == (None, None, True)


def test_0020_skips_a_kpi_note_that_would_overflow_the_field():
    RoadmapKpi.objects.create(code="UK7", lane="sec", name="سجلّ", source="ك" * 250)
    assert _sync20.sync_kpi_notes(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="UK7").source == "ك" * 250


def test_0020_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync20.forwards(_Apps20, None)
    assert RoadmapItem.objects.count() == 0 and RoadmapKpi.objects.count() == 0
    _item("U-01", "todo", 0)
    _sync20.forwards(_Apps20, None)

    def snapshot():
        return (
            RoadmapItem.objects.count(),
            RoadmapKpi.objects.count(),
            RoadmapDecision.objects.count(),
            list(RoadmapItem.objects.filter(code="U-01").values_list("note", flat=True)),
        )

    first = snapshot()
    _sync20.forwards(_Apps20, None)
    assert snapshot() == first
    assert first[:3] == (24, 11, 8)


def test_0020_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0020_git_repo_remediation_plan").origin
    body = open(origin, encoding="utf-8").read()
    # المستودعُ عامّ: لا وصفَ لما تعرّض ولا أين ولا كم، ولا ثغرةً حيّةً بمقياسها، ولا رقماً شخصيّاً ولا بصمةً.
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "#382",
        "غيرُ صفر",
        "كم شخصاً",
        "التاريخ العامّ",
        "بصمات",
        "العروض المخزَّنة",
        "الحادثة",
        "الاثنين 09-28",
        "72 ساعة",
        "كلمةٌ افتراضيّةٌ",
        "رقمٌ حقيقيّ",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
    assert not re.search(r"\bR2\b", body)
    assert "كلمة المرور المؤقتة" not in body and "Temp@" not in body


# ── 0021: ما اندمج ونُشر بعد #577 و#571 — #572 وM-05 (#579) وDBT-55 (#581) ──

_sync21 = importlib.import_module("roadmap.migrations.0021_sync_items_2026_09_25b")


class _Apps21:
    @staticmethod
    def get_model(_app, name):
        return RoadmapKpi if name == "RoadmapKpi" else RoadmapItem


def _seed21():
    _item("DBT-53", "todo", 0)
    _item("DBT-55", "todo", 0, gate="owner")
    _item("M-05", "todo", 0)
    _item("DBT-36", "todo", 0)


def test_0021_closes_the_three_published_items_and_only_notes_dbt36():
    _seed21()
    assert _sync21.sync(RoadmapItem) == ["DBT-53", "DBT-55", "M-05", "DBT-36"]
    assert _sync21.sync(RoadmapItem) == []
    for code, pr in (("DBT-53", "#572"), ("DBT-55", "#581"), ("M-05", "#579")):
        item = RoadmapItem.objects.get(code=code)
        assert (item.status, item.progress, item.pr) == ("done", 100, pr), code
        assert "منشورٌ على الإنتاج" in item.note and "main@38181bc" in item.note, code
    dbt36 = RoadmapItem.objects.get(code="DBT-36")
    assert (dbt36.status, dbt36.progress, dbt36.pr) == ("todo", 0, "")
    assert "468.94KB" in dbt36.note and "ولم يُقَس المجموعُ" in dbt36.note


def test_0021_corrects_the_dbt55_estimate_and_lifts_the_owner_gate_only_there():
    _seed21()
    RoadmapItem.objects.filter(code="M-05").update(gate="owner")
    _sync21.sync(RoadmapItem)
    dbt55 = RoadmapItem.objects.get(code="DBT-55")
    assert dbt55.gate == ""
    # التقديرُ «+2px» لم يقع: يُقال ذلك بالقياس، والأرقامُ الرسميّة من CI تُذكر.
    assert "لم يقع" in dbt55.note and "64.8px" in dbt55.note and "2 (0.41%)" in dbt55.note
    assert "كانت بوّابةُ «المالك»" in dbt55.note
    # ولا يُرفع حاجزُ غيره.
    assert RoadmapItem.objects.get(code="M-05").gate == "owner"


def test_0021_states_what_m05_did_not_verify_and_the_real_count():
    _seed21()
    _sync21.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="M-05").note
    assert "9 مواضع فعليّة" in note and "لم يُتحقَّق منه" in note and "+218 بايتاً" in note
    dbt53 = RoadmapItem.objects.get(code="DBT-53").note
    assert "25 نموذجاً" in dbt53 and "4140" in dbt53 and "2243" in dbt53 and "857" in dbt53


def test_0021_leaves_an_item_the_developer_moved():
    _item("M-05", "doing", 40)
    assert "M-05" not in _sync21.sync(RoadmapItem)
    m05 = RoadmapItem.objects.get(code="M-05")
    assert (m05.status, m05.progress, m05.note) == ("doing", 40, "")


def test_0021_fills_mk9_once_with_a_history_point_and_keeps_a_measured_kpi():
    RoadmapKpi.objects.create(
        code="MK9",
        lane="mobile",
        name="مواضعُ 100vh بلا dvh",
        baseline_text="6–8",
        source="خطّة الجوال",
        text_mode=True,
    )
    RoadmapKpi.objects.create(
        code="MK1", lane="mobile", name="x", current=0.2, measured_at=_sync21.DAY, text_mode=True
    )
    assert _sync21.first_readings(RoadmapKpi) == ["MK9"]
    assert _sync21.first_readings(RoadmapKpi) == []
    mk9 = RoadmapKpi.objects.get(code="MK9")
    assert (mk9.current, mk9.measured_at) == (0.0, _sync21.DAY)
    assert mk9.history == [{"d": "2026-09-25", "v": 0.0}] and "test_dynamic_viewport" in mk9.source
    assert mk9.baseline_text == "6–8" and mk9.text_mode is True
    assert RoadmapKpi.objects.get(code="MK1").current == 0.2


def test_0021_never_overwrites_a_kpi_the_developer_already_measured():
    RoadmapKpi.objects.create(
        code="MK9",
        lane="mobile",
        name="x",
        current=3.0,
        measured_at=_sync21.DAY,
        source="ميدانيّ",
        text_mode=True,
    )
    assert _sync21.first_readings(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="MK9").current == 3.0


def test_0021_keeps_the_kpi_source_within_the_field_limit():
    RoadmapKpi.objects.create(code="MK9", lane="mobile", name="x", source="ك" * 250, text_mode=True)
    assert _sync21.first_readings(RoadmapKpi) == ["MK9"]
    mk9 = RoadmapKpi.objects.get(code="MK9")
    assert mk9.source == "ك" * 250 and mk9.current == 0.0


def test_0021_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync21.forwards(_Apps21, None)
    assert RoadmapItem.objects.count() == 0
    _seed21()
    RoadmapKpi.objects.create(code="MK9", lane="mobile", name="x", source="خطّة", text_mode=True)
    _sync21.forwards(_Apps21, None)

    def snapshot():
        return (
            list(
                RoadmapItem.objects.order_by("code").values_list(
                    "code", "status", "progress", "pr", "gate", "note"
                )
            ),
            list(RoadmapKpi.objects.values_list("code", "current", "history", "source")),
        )

    first = snapshot()
    _sync21.forwards(_Apps21, None)
    assert snapshot() == first


def test_0021_registers_m05b_as_a_proposed_open_item_without_dates():
    assert _sync21.add_proposed(RoadmapItem) == ["M-05b"]
    assert _sync21.add_proposed(RoadmapItem) == []
    m05b = RoadmapItem.objects.get(code="M-05b")
    assert (m05b.status, m05b.progress, m05b.lane, m05b.src, m05b.deps) == (
        "todo",
        0,
        "mobile",
        "M",
        "M-05",
    )
    assert m05b.start_date is None and m05b.end_date is None and m05b.gate == ""
    assert "مقترَحاً مفتوحاً" in m05b.note and "8 ← 0" in m05b.criterion and m05b.sort_order == 724


def test_0021_keeps_an_m05b_the_developer_wrote_first():
    _item("M-05b", "doing", 20, title="كتبه المطوّر")
    assert _sync21.add_proposed(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-05b").title == "كتبه المطوّر"


def test_0021_publishes_no_personal_number_and_never_adds_rep01():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0021_sync_items_2026_09_25b").origin
    body = open(origin, encoding="utf-8").read()
    assert not re.search(r"\b\d{11}\b", body) and not re.search(r"\b[0-9a-f]{40}\b", body)
    # REP-01 ينتظر قياسَه الفعليّ من جلسة Git: لا يُغلق هنا.
    assert "REP-01" not in [row[0] for row in _sync21.UPDATES]


# ── 0022: #583 الشعار — تنفيذٌ جزئيٌّ لـVI-11 وقرارِ VD4 ──

_sync22 = importlib.import_module("roadmap.migrations.0022_sync_items_2026_09_25c")


class _Apps22:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapKpi": RoadmapKpi, "RoadmapDecision": RoadmapDecision}.get(name, RoadmapItem)


def test_0022_moves_vi11_to_doing_at_50_with_the_derivation_and_never_closes_it():
    from datetime import date

    _item("VI-11", "todo", 0, start_date=date(2026, 11, 2), end_date=date(2026, 11, 4))
    assert _sync22.sync(RoadmapItem) == ["VI-11"]
    assert _sync22.sync(RoadmapItem) == []
    vi11 = RoadmapItem.objects.get(code="VI-11")
    assert (vi11.status, vi11.progress, vi11.pr) == ("doing", 50, "#583")
    # الموعدُ لم يُغيَّر، والنسبةُ منسوبةٌ لحسابٍ صريح، والمعيارُ غيرُ المتحقّق لا يُحتسب تقدّماً.
    assert (str(vi11.start_date), str(vi11.end_date)) == ("2026-11-02", "2026-11-04")
    note = vi11.note
    assert "اشتقاقُ 8104 بحسابٍ صريح" in note and "0 من 4" in note
    assert "34,167" in note and "تقديرٌ لم يُقَس على الإنتاج" in note
    assert "منشورٌ على الإنتاج" in note and "main@6087da6" in note and "لم يُنشر بعدُ" not in note
    assert "لم يُعاين" in note and "الباقي" in note


def test_0022_leaves_vi11_the_developer_moved():
    _item("VI-11", "doing", 20)
    assert _sync22.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="VI-11").note == ""


def test_0022_fills_vk39_once_with_the_measured_zero_and_keeps_its_texts():
    RoadmapKpi.objects.create(
        code="V-K39",
        lane="frontend",
        name="نسخُ الشعار الرسميّة وفلاترُ التبييض",
        baseline_text="0 نسخة · 4 فلاتر",
        target_text="SVG + معكوس · 0 فلتر",
        direction="down",
        source="خطّةُ إصلاح الهويّة (جلسة 8104، 2026-09-24)",
        text_mode=True,
    )
    assert _sync22.first_readings(RoadmapKpi) == ["V-K39"]
    assert _sync22.first_readings(RoadmapKpi) == []
    k = RoadmapKpi.objects.get(code="V-K39")
    assert (k.current, k.measured_at, k.unit) == (0.0, _sync22.DAY, "count")
    assert k.history == [{"d": "2026-09-25", "v": 0.0}] and k.text_mode is True
    assert k.baseline_text == "0 نسخة · 4 فلاتر" and k.target_text == "SVG + معكوس · 0 فلتر"
    # ملاحظةُ المصدر تدخل كاملةً ضمن الحدّ 255 (لا تُسقَط بالتجاوز).
    assert (
        "فلاترُ التبييض 0 (كانت 4)" in k.source
        and "لا ملفّ رسميّ" in k.source
        and len(k.source) <= 255
    )


def test_0022_never_overwrites_a_measured_vk39():
    RoadmapKpi.objects.create(
        code="V-K39", lane="frontend", name="x", current=2.0, measured_at=_sync22.DAY
    )
    assert _sync22.first_readings(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="V-K39").current == 2.0


def test_0022_notes_vd4_as_partly_done_without_changing_its_status():
    RoadmapDecision.objects.create(
        code="VD4", title="x", status="decided", recommendation="حسمه المالك"
    )
    assert _sync22.annotate_decisions(RoadmapDecision) == ["VD4"]
    assert _sync22.annotate_decisions(RoadmapDecision) == []
    vd4 = RoadmapDecision.objects.get(code="VD4")
    assert vd4.status == "decided" and "نُفِّذ جزءٌ منه بـ#583" in vd4.recommendation
    assert vd4.recommendation.startswith("حسمه المالك")


def test_0022_does_not_touch_a_vd4_that_is_not_decided():
    RoadmapDecision.objects.create(code="VD4", title="x", status="open", recommendation="مفتوح")
    assert _sync22.annotate_decisions(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="VD4").recommendation == "مفتوح"


def test_0022_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync22.forwards(_Apps22, None)
    assert RoadmapItem.objects.count() == 0
    _item("VI-11", "todo", 0)
    RoadmapKpi.objects.create(code="V-K39", lane="frontend", name="x", source="خطّة", text_mode=True)
    RoadmapDecision.objects.create(code="VD4", title="x", status="decided", recommendation="حسمه")
    _sync22.forwards(_Apps22, None)

    def snapshot():
        return (
            list(RoadmapItem.objects.values_list("code", "status", "progress", "pr", "note")),
            list(RoadmapKpi.objects.values_list("code", "current", "history", "source")),
            list(RoadmapDecision.objects.values_list("code", "status", "recommendation")),
        )

    first = snapshot()
    _sync22.forwards(_Apps22, None)
    assert snapshot() == first


def test_0022_publishes_no_personal_number_and_no_school_name():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0022_sync_items_2026_09_25c").origin
    body = open(origin, encoding="utf-8").read()
    bs = chr(92)
    assert not re.search(bs + "b" + bs + "d{11}" + bs + "b", body)
    assert not re.search(bs + "b[0-9a-f]{40}" + bs + "b", body)
    # اسمُ المدرسة الفعليّ يرد في نصّ طلب #583 لا في هجرةٍ عامّة.
    assert "الشحانية" not in body


# ── 0023: REP-04 (#588) وREP-01 (بعمليّة) وRK6 = 0 والدَّين DBT-56 ──

_sync23 = importlib.import_module("roadmap.migrations.0023_sync_items_2026_09_25d")


class _Apps23:
    @staticmethod
    def get_model(_app, name):
        return RoadmapKpi if name == "RoadmapKpi" else RoadmapItem


def _seed23():
    _item("REP-04", "todo", 0)
    _item("REP-01", "todo", 0)
    _item("REP-03", "todo", 0, gate="owner")


def test_0023_closes_rep04_by_its_pr_and_rep01_by_an_operation():
    _seed23()
    assert _sync23.sync(RoadmapItem) == ["REP-04", "REP-01", "REP-03"]
    assert _sync23.sync(RoadmapItem) == []
    rep04 = RoadmapItem.objects.get(code="REP-04")
    assert (rep04.status, rep04.progress, rep04.pr) == ("done", 100, "#588")
    assert (
        "4 فاشلة و2 ناجحة" in rep04.note
        and "RK6 من 2 إلى 0" in rep04.note
        and "DBT-56" in rep04.note
    )
    # نُشر ضمن main@db33f87 بإخطار جلسة النشر: لا تبقى عبارةُ «يُنشر لاحقاً».
    assert "منشورٌ على الإنتاج" in rep04.note and "main@db33f87" in rep04.note
    assert "فيُنشر في دورةٍ لاحقة" not in rep04.note and "main@6087da6" not in rep04.note
    rep01 = RoadmapItem.objects.get(code="REP-01")
    assert (rep01.status, rep01.progress, rep01.pr) == ("done", 100, "")
    assert "بعمليّةٍ لا بطلب دمج" in rep01.note and "طابقت مراجعَ الحزمة كلَّها" in rep01.note
    assert "RK2 لا يتغيّر قبل REP-05" in rep01.note
    assert "آخر 14 نسخة" in rep01.note and "02:00" in rep01.note and "لم يصلني" not in rep01.note


def test_0023_moves_rep03_to_60_by_the_sessions_explicit_count_and_keeps_the_owner_gate():
    _seed23()
    _sync23.sync(RoadmapItem)
    rep03 = RoadmapItem.objects.get(code="REP-03")
    assert (rep03.status, rep03.progress, rep03.gate) == ("doing", 60, "owner")
    # النسبةُ منسوبةٌ لحسابٍ صريح (3 من 5 متساوية الوزن) وما بقي بيد المالك.
    assert "خمسُ خطواتٍ متساوية الوزن" in rep03.note and "منجزٌ منها ثلاث" in rep03.note
    assert (
        "0 من 3" in rep03.note
        and "ينفّذه المالكُ بنفسه" in rep03.note
        and "البوّابةُ «المالك» باقية" in rep03.note
    )


def test_0023_leaves_an_item_the_developer_moved():
    _item("REP-04", "doing", 30)
    assert "REP-04" not in _sync23.sync(RoadmapItem)
    assert RoadmapItem.objects.get(code="REP-04").note == ""


def test_0023_sets_rk6_to_zero_keeping_the_baseline_and_replacing_todays_point():
    RoadmapKpi.objects.create(
        code="RK6",
        lane="sec",
        name="x",
        baseline=2.0,
        current=2.0,
        target=0.0,
        measured_at=_sync23.DAY,
        history=[{"d": "2026-09-25", "v": 2.0}],
        source="مراجعةُ workflows",
    )
    assert _sync23.sync_kpis(RoadmapKpi) == ["RK6"]
    assert _sync23.sync_kpis(RoadmapKpi) == []
    rk6 = RoadmapKpi.objects.get(code="RK6")
    assert (rk6.baseline, rk6.current) == (2.0, 0.0)
    # قياسُ اليوم يستبدل نقطةَ اليوم لا يضيف نقطةً ثانيةً بالتاريخ نفسه.
    assert (
        rk6.history == [{"d": "2026-09-25", "v": 0.0}]
        and "#588" in rk6.source
        and len(rk6.source) <= 255
    )


def test_0023_leaves_an_rk6_the_developer_remeasured():
    RoadmapKpi.objects.create(
        code="RK6", lane="sec", name="x", baseline=2.0, current=1.0, measured_at=_sync23.DAY
    )
    assert _sync23.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="RK6").current == 1.0


def test_0023_registers_dbt56_open_undated_and_without_a_pr():
    assert _sync23.add_debts(RoadmapItem) == ["DBT-56"]
    assert _sync23.add_debts(RoadmapItem) == []
    dbt56 = RoadmapItem.objects.get(code="DBT-56")
    assert (dbt56.status, dbt56.progress, dbt56.pr, dbt56.src, dbt56.lane) == (
        "todo",
        0,
        "",
        "DBT",
        "backend",
    )
    assert dbt56.start_date is None and dbt56.end_date is None and dbt56.sort_order == 725
    assert "2 ← 0" in dbt56.criterion and "26 ← 0" in dbt56.criterion and "توثيقٍ" in dbt56.note


def test_0023_keeps_a_dbt56_the_developer_wrote_first():
    _item("DBT-56", "doing", 10, title="كتبه المطوّر")
    assert _sync23.add_debts(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="DBT-56").title == "كتبه المطوّر"


def test_0023_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync23.forwards(_Apps23, None)
    assert RoadmapItem.objects.count() == 0
    _seed23()
    RoadmapKpi.objects.create(
        code="RK6",
        lane="sec",
        name="x",
        baseline=2.0,
        current=2.0,
        measured_at=_sync23.DAY,
        source="مراجعة",
    )
    _sync23.forwards(_Apps23, None)

    def snapshot():
        return (
            list(
                RoadmapItem.objects.order_by("code").values_list(
                    "code", "status", "progress", "pr", "note"
                )
            ),
            list(RoadmapKpi.objects.values_list("code", "current", "history", "source")),
        )

    first = snapshot()
    _sync23.forwards(_Apps23, None)
    assert snapshot() == first
    assert RoadmapItem.objects.filter(code="DBT-56").exists()


def test_0023_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0023_sync_items_2026_09_25d").origin
    body = open(origin, encoding="utf-8").read()
    bs = chr(92)
    assert not re.search(bs + "b" + bs + "d{11}" + bs + "b", body)
    assert not re.search(bs + "b[0-9a-f]{40}" + bs + "b", body)
    # لا وصفَ لما كان يخفيه الفحصُ ولا لتاريخ ضعفه ولا أسماءَ خطواتٍ حسّاسة ولا بصمات.
    banned = (
        "Security Summary",
        "منذ 2026-09-1",
        "بصمات",
        "الحادثة",
        "FERNET",
        ".zip",
        "aaaa",
        "كم شخصاً",
        "27 issues",
    )
    assert [term for term in banned if term in body] == []


# ── 0024: #589 — SCH-10 مؤشّرُ تركّز الاستثناءات (50% لا منجَز) ──

_sync24 = importlib.import_module("roadmap.migrations.0024_sync_items_2026_09_25e")


class _Apps24:
    @staticmethod
    def get_model(_app, _name):
        return RoadmapItem


def test_0024_closes_sch10_at_100_once_both_criteria_are_met_keeping_the_50_history():
    from datetime import date

    _item("SCH-10", "todo", 0, start_date=date(2026, 9, 28), end_date=date(2026, 10, 2))
    assert _sync24.sync(RoadmapItem) == ["SCH-10"]
    assert _sync24.sync(RoadmapItem) == []
    sch10 = RoadmapItem.objects.get(code="SCH-10")
    assert (sch10.status, sch10.progress, sch10.pr) == ("done", 100, "#589")
    # الموعدُ لم يُغيَّر، والمعياران تحقّقا (الأساسُ حُفظ بإذن المالك)، وما كان 50% يُذكر تاريخاً.
    assert (str(sch10.start_date), str(sch10.end_date)) == ("2026-09-28", "2026-10-02")
    note = sch10.note
    assert "تحقّق معيارا الإغلاق" in note and "(100 + 0) / 2" in note and "كان البند 50%" in note
    assert "15007906" in note and "= **2**" in note and "الأسسُ 5 ← 6" in note
    # عرضٌ لا حكم: لا يدخل الدرجة، ولا تغيّرَ في SK*.
    assert "عرضٌ لا حكم" in note and "ولا تغيّرَ في SK*" in note


def test_0024_records_the_owner_pinning_of_the_new_baseline_as_done_not_as_pending():
    _item("SCH-10", "todo", 0)
    _sync24.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="SCH-10").note
    assert (
        "ثُبِّت الأساسُ الجديد بقرار المالك" in note
        and "ثبّت الأساس الجديد" in note
        and "d37abbc3" in note
    )
    assert "ويمكن إعادةُ تثبيته" in note
    assert "لم يُثبَّت الأساسُ الجديد" not in note and "ولم يُتَّخذ" not in note


def test_0024_states_it_was_published_on_production():
    _item("SCH-10", "todo", 0)
    _sync24.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="SCH-10").note
    assert (
        "منشورٌ على الإنتاج" in note and "main@db33f87" in note and "فيُنشر في دورةٍ لاحقة" not in note
    )


def test_0024_notes_the_current_approved_generation_on_sch08_without_moving_it():
    _item("SCH-08", "doing", 90)
    assert _sync24.sync(RoadmapItem) == ["SCH-08"]
    assert _sync24.sync(RoadmapItem) == []
    sch08 = RoadmapItem.objects.get(code="SCH-08")
    assert (sch08.status, sch08.progress) == ("doing", 90)
    assert "15007906" in sch08.note and "c2dba53a" in sch08.note and "2026-09-27" in sch08.note


def test_0024_leaves_sch10_the_developer_moved():
    _item("SCH-10", "doing", 20)
    assert _sync24.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-10").note == ""


def test_0024_registers_sch19_as_a_proposed_open_item_without_dates_after_the_owner_confirmed():
    assert _sync24.add_proposed(RoadmapItem) == ["SCH-19"]
    assert _sync24.add_proposed(RoadmapItem) == []
    sch19 = RoadmapItem.objects.get(code="SCH-19")
    assert (sch19.status, sch19.progress, sch19.lane, sch19.src, sch19.deps) == (
        "todo",
        0,
        "backend",
        "SCH",
        "SCH-08",
    )
    assert (
        sch19.start_date is None
        and sch19.end_date is None
        and sch19.gate == ""
        and sch19.sort_order == 619
    )
    # يغيّر التوليد فيُقاس على نسخة الإنتاج قبل الدمج، ولا يبدأ قبل تحقّق الأحد.
    assert (
        "يغيّر التوليد" in sch19.note and "2026-09-27" in sch19.note and "24 يومَ معلّمٍ" in sch19.note
    )
    assert "معاملةٌ تُتراجع" in sch19.criterion


def test_0024_keeps_a_sch19_the_developer_wrote_first():
    _item("SCH-19", "doing", 10, title="كتبه المطوّر")
    assert _sync24.add_proposed(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-19").title == "كتبه المطوّر"


def test_0024_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync24.forwards(_Apps24, None)
    assert RoadmapItem.objects.count() == 0
    _item("SCH-10", "todo", 0)
    _sync24.forwards(_Apps24, None)
    first = list(RoadmapItem.objects.values_list("code", "status", "progress", "pr", "note"))
    _sync24.forwards(_Apps24, None)
    assert (
        list(RoadmapItem.objects.values_list("code", "status", "progress", "pr", "note")) == first
    )


def test_0024_publishes_no_personal_number_and_no_hash():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0024_sync_items_2026_09_25e").origin
    body = open(origin, encoding="utf-8").read()
    bs = chr(92)
    assert not re.search(bs + "b" + bs + "d{11}" + bs + "b", body)
    assert not re.search(bs + "b[0-9a-f]{40}" + bs + "b", body)


# ── 0025: إعادةُ قياس SK1..SK5 على التوليد المعتمد الآن 15007906 ──

_sync25 = importlib.import_module("roadmap.migrations.0025_sync_kpis_2026_09_25")

_SK25 = {
    "SK1": (7.0, 12.0),
    "SK2": (99.3, 98.2),
    "SK3": (6.1, 17.9),
    "SK4": (22.8, 26.0),
    "SK5": (2.0, 0.0),
}


class _Apps25:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapKpi": RoadmapKpi, "RoadmapDecision": RoadmapDecision}.get(name, RoadmapItem)


def _seed_sk25():
    for code, (current, baseline) in _SK25.items():
        RoadmapKpi.objects.create(
            code=code,
            lane="backend",
            name=code,
            baseline=baseline,
            current=current,
            measured_at=_sync25.PREVIOUS,
            history=[{"d": "2026-09-24", "v": current}],
            source="تدقيقُ الجدول الحيّ 2026-09-24 (جلسة الجدولة) (الإنتاج بعد اعتماد c2dba53a)",
        )


def test_0025_records_the_remeasurement_keeping_the_baselines_and_appending_a_history_point():
    _seed_sk25()
    assert _sync25.sync_kpis(RoadmapKpi) == ["SK1", "SK2", "SK3", "SK4", "SK5"]
    assert _sync25.sync_kpis(RoadmapKpi) == []
    values = {k.code: k.current for k in RoadmapKpi.objects.all()}
    assert values == {"SK1": 7.0, "SK2": 99.3, "SK3": 6.9, "SK4": 23.6, "SK5": 2.0}
    for k in RoadmapKpi.objects.all():
        assert k.baseline == _SK25[k.code][1], k.code
        assert k.measured_at == _sync25.DAY, k.code
        # نقطةُ الأمس باقية ونقطةُ اليوم أُضيفت (حتى لو تساوت القيمتان).
        assert [p["d"] for p in k.history] == ["2026-09-24", "2026-09-25"], k.code
        assert "15007906" in k.source and len(k.source) <= 255, k.code


def test_0025_warns_that_the_sk3_rise_is_the_definition_flaw_not_a_real_regression():
    _seed_sk25()
    _sync25.sync_kpis(RoadmapKpi)
    sk3 = RoadmapKpi.objects.get(code="SK3")
    assert "SCH-19" in sk3.source and "≈1.7%" in sk3.source and "يعدّ المزدوجةَ تتابعاً" in sk3.source


def test_0025_attributes_the_sk4_cause_to_the_session_as_probable_not_proven():
    _seed_sk25()
    _sync25.sync_kpis(RoadmapKpi)
    sk4 = RoadmapKpi.objects.get(code="SK4")
    assert "سببٌ مرجَّحٌ لـ8033" in sk4.source and "#564" in sk4.source


def test_0025_leaves_a_kpi_the_developer_remeasured():
    _seed_sk25()
    RoadmapKpi.objects.filter(code="SK4").update(current=20.0)
    assert "SK4" not in _sync25.sync_kpis(RoadmapKpi)
    assert RoadmapKpi.objects.get(code="SK4").current == 20.0


def test_0025_never_writes_an_overflowing_source_but_still_records_the_value():
    RoadmapKpi.objects.create(
        code="SK3",
        lane="backend",
        name="x",
        baseline=17.9,
        current=6.1,
        measured_at=_sync25.PREVIOUS,
        source="ك" * 250,
    )
    assert _sync25.sync_kpis(RoadmapKpi) == ["SK3"]
    sk3 = RoadmapKpi.objects.get(code="SK3")
    assert sk3.source == "ك" * 250 and sk3.current == 6.9


def test_0025_notes_sch11_without_moving_it_and_leaves_the_decision_to_the_owner():
    _item("SCH-11", "doing", 15)
    assert _sync25.sync_notes(RoadmapItem) == ["SCH-11"]
    assert _sync25.sync_notes(RoadmapItem) == []
    sch11 = RoadmapItem.objects.get(code="SCH-11")
    assert (sch11.status, sch11.progress) == ("doing", 15)
    assert "23.6%" in sch11.note and "قرارُ مالكٍ" in sch11.note and "لا يُتَّخذ هنا" in sch11.note
    assert "مؤشِّرٌ لا إثبات" in sch11.note


def test_0025_closes_rep03_by_the_neutral_sentence_and_lifts_its_owner_gate():
    _item("REP-03", "doing", 60, gate="owner")
    assert _sync25.sync(RoadmapItem) == ["REP-03"]
    assert _sync25.sync(RoadmapItem) == []
    rep03 = RoadmapItem.objects.get(code="REP-03")
    assert (rep03.status, rep03.progress, rep03.gate) == ("done", 100, "")
    # الجملةُ المحايدة كما أرسلتها جلسةُ Git: بلا أسماء متغيّراتٍ ولا أعدادٍ ولا تفاصيل.
    assert "قورنت البصماتُ المسجَّلة بالإنتاج في الخدمات الثلاث؛ لا تطابق" in rep03.note
    assert "خمسُ خطواتٍ من خمس" in rep03.note and "شغّله المالكُ بنفسه" in rep03.note


def test_0025_adds_the_lay03_note_and_pr_tokens_without_moving_its_state_or_dates():
    from datetime import date

    _item(
        "LAY-03",
        "doing",
        50,
        pr="#532 #539 #543",
        start_date=date(2026, 10, 19),
        end_date=date(2026, 11, 6),
    )
    assert _sync25.sync(RoadmapItem) == ["LAY-03"]
    assert _sync25.sync(RoadmapItem) == []
    lay03 = RoadmapItem.objects.get(code="LAY-03")
    assert (lay03.status, lay03.progress, lay03.pr) == ("doing", 50, "#532 #539 #543 #567 #585")
    assert (str(lay03.start_date), str(lay03.end_date)) == ("2026-10-19", "2026-11-06")
    note = lay03.note
    assert "لا @container، ويبقى ADR-0005 D3" in note and "«مقترح» مقدَّمٌ لاعتماد المالك" in note
    # #585 منشورٌ بإخطار جلسة النشر، و#587 مدموجٌ غيرُ منشور، و#586 قيد الطابور لم يندمج.
    assert "منشورٌ على الإنتاج main@7f7241e" in note and "#586 قيد الطابور" in note
    assert "#587 مدموجٌ (b46534f6" in note and "غيرُ منشورٍ بعدُ" in note
    assert "لم يُنشر بعد" not in note
    assert "لم تُغيَّر حالةُ البند ولا تقدّمُه ولا موعدُه" in note


def test_0025_leaves_a_lay03_the_developer_moved():
    _item("LAY-03", "done", 100)
    assert _sync25.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="LAY-03").note == ""


def test_0025_closes_vi54_by_592_lifting_the_owner_gate_and_saying_it_is_unpublished():
    _item("VI-54", "todo", 0, gate="owner")
    assert _sync25.sync(RoadmapItem) == ["VI-54"]
    assert _sync25.sync(RoadmapItem) == []
    vi54 = RoadmapItem.objects.get(code="VI-54")
    assert (vi54.status, vi54.progress, vi54.pr, vi54.gate) == ("done", 100, "#592", "")
    note = vi54.note
    assert "منشورٌ على الإنتاج ضمن main@9acf2e1" in note and "غيرُ منشور" not in note
    # ما لم يُقَس يُقال، والحارسُ باسمه، ولا يُدَّعى فحصٌ على الجوّال.
    assert "لم يُقَس" in note and "الإدارةُ على الجوال" in note
    assert "test_the_admin_is_day_by_default_and_never_reads_the_system_theme" in note


def test_0025_leaves_a_vi54_the_developer_moved():
    _item("VI-54", "doing", 30, gate="owner")
    assert _sync25.sync(RoadmapItem) == []
    vi54 = RoadmapItem.objects.get(code="VI-54")
    assert (vi54.status, vi54.gate, vi54.note) == ("doing", "owner", "")


def test_0025_adds_the_591_progress_note_on_dbt44_keeping_it_closed_and_unpublished():
    _item("DBT-44", "done", 100, pr="#576")
    assert _sync25.sync(RoadmapItem) == ["DBT-44"]
    assert _sync25.sync(RoadmapItem) == []
    dbt44 = RoadmapItem.objects.get(code="DBT-44")
    assert (dbt44.status, dbt44.progress, dbt44.pr) == ("done", 100, "#576 #591")
    note = dbt44.note
    assert (
        "1 من 491 (0.2%)" in note
        and "منشورٌ على الإنتاج ضمن main@9acf2e1" in note
        and "DBT-45" in note
    )
    assert "غيرُ منشور" not in note


def test_0025_leaves_a_dbt44_the_developer_reopened():
    _item("DBT-44", "doing", 50)
    assert "DBT-44" not in _sync25.sync(RoadmapItem)
    assert RoadmapItem.objects.get(code="DBT-44").note == ""


def test_0025_registers_lay08_as_a_proposed_open_umbrella_without_dates_or_a_closed_state():
    assert _sync25.add_proposed(RoadmapItem) == ["LAY-08"]
    assert _sync25.add_proposed(RoadmapItem) == []
    lay08 = RoadmapItem.objects.get(code="LAY-08")
    assert (lay08.status, lay08.progress, lay08.lane, lay08.src, lay08.deps) == (
        "todo",
        0,
        "frontend",
        "LAY",
        "LAY-03",
    )
    assert (
        lay08.start_date is None
        and lay08.end_date is None
        and lay08.gate == ""
        and lay08.sort_order == 730
    )
    # القائمةُ الأحدَ عشرَ كلُّها في الملاحظة، ومنسوبةٌ لقياس 8101، وفيها القراران للمالك.
    note = lay08.note
    for marker in ("(1)", "(2)", "(3)", "(4)", "(5)", "(6)", "(7)", "(8)", "(9)", "(10)", "(11)"):
        assert marker in note, marker
    assert "8101" in note and "ولم تُصلَح" in note and "D-23" in note and "D-24" in note


def test_0025_keeps_a_lay08_the_developer_wrote_first():
    _item("LAY-08", "doing", 10, title="كتبه المطوّر")
    assert _sync25.add_proposed(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="LAY-08").title == "كتبه المطوّر"


def test_0025_opens_d22_d23_d24_for_the_owner_without_deciding_any():
    assert _sync25.add_decisions(RoadmapDecision) == ["D-22", "D-23", "D-24"]
    assert _sync25.add_decisions(RoadmapDecision) == []
    decisions = {d.code: d for d in RoadmapDecision.objects.all()}
    assert all(
        (d.status, d.decision_date, d.decider) == ("open", None, "المالك")
        for d in decisions.values()
    )
    assert [decisions[c].sort_order for c in ("D-22", "D-23", "D-24")] == [136, 137, 138]
    # D-22 يحجب M-04 ويخيّر بين البقاء والتبديل بعد رؤيته على آيفون؛ وD-23/D-24 يحجبان LAY-08.
    assert decisions["D-22"].blocks == "M-04" and "black-translucent" in decisions["D-22"].options
    assert decisions["D-23"].blocks == "LAY-08" and "2026-09-06" in decisions["D-23"].title
    assert decisions["D-24"].blocks == "LAY-08" and "fitNoscroll" in decisions["D-24"].options
    # لا توصيةَ تُخترع: النصُّ يقول ذلك صراحةً.
    assert all("لا توصيةَ" in d.recommendation for d in decisions.values())


def test_0025_keeps_a_decision_the_owner_already_took():
    RoadmapDecision.objects.create(
        code="D-22", title="x", status="decided", recommendation="حسمه المالك"
    )
    assert "D-22" not in _sync25.add_decisions(RoadmapDecision)
    assert RoadmapDecision.objects.get(code="D-22").recommendation == "حسمه المالك"


def test_0025_closes_m04_by_594_keeping_the_open_owner_decision_and_the_unverified_device():
    _item("M-04", "doing", 40, pr="#549")
    assert _sync25.sync(RoadmapItem) == ["M-04"]
    assert _sync25.sync(RoadmapItem) == []
    m04 = RoadmapItem.objects.get(code="M-04")
    assert (m04.status, m04.progress, m04.pr) == ("done", 100, "#549 #594")
    note = m04.note
    assert (
        "منشورٌ على الإنتاج ضمن main@9acf2e1" in note
        and "لم يُتحقَّق منه" in note
        and "جهازٌ حقيقيّ" in note
    )
    assert (
        "مراجعةُ جهازٍ حقيقيّ" in note and "بنداً معلَّقاً على المالك" in note and "غيرُ منشور" not in note
    )
    assert "قرارٌ مفتوحٌ للمالك" in note and "black-translucent" in note and "+703 بايتاً" in note


def test_0025_moves_own23_to_30_as_the_sessions_suggestion_not_a_measurement_and_keeps_the_gate():
    _item("OWN-23", "todo", 0, gate="owner")
    assert _sync25.sync(RoadmapItem) == ["OWN-23"]
    assert _sync25.sync(RoadmapItem) == []
    own23 = RoadmapItem.objects.get(code="OWN-23")
    assert (own23.status, own23.progress, own23.pr, own23.gate) == ("doing", 30, "#593", "owner")
    note = own23.note
    assert (
        "الشقُّ الأوّل فقط" in note
        and "لا يُغلق البند" in note
        and "اقتراحُ 8096" in note
        and "لا قياس" in note
    )
    assert "لا نصَّ ولا معرّفاً" in note and "منشورٌ على الإنتاج ضمن main@9acf2e1" in note
    assert (
        "لم يُعاين /admin/ مرسوماً" in note
        and "بناءَ بطاقة النسخ الاحتياطيّ" in note
        and "لم تُدفع" in note
    )
    assert "غيرُ منشور" not in note


def test_0025_records_mk8_yes_as_one_with_a_history_point_once():
    RoadmapKpi.objects.create(
        code="MK8",
        lane="mobile",
        name="viewport-fit=cover",
        baseline_text="لا",
        target_text="نعم (P0: نعم)",
        source="خطّة الجوال K8",
        text_mode=True,
    )
    assert _sync25.first_readings(RoadmapKpi) == ["MK8"]
    assert _sync25.first_readings(RoadmapKpi) == []
    mk8 = RoadmapKpi.objects.get(code="MK8")
    assert (mk8.current, mk8.measured_at) == (1.0, _sync25.DAY)
    assert (
        mk8.history == [{"d": "2026-09-25", "v": 1.0}]
        and "1 = نعم" in mk8.source
        and len(mk8.source) <= 255
    )
    assert (mk8.baseline_text, mk8.target_text) == ("لا", "نعم (P0: نعم)")


def test_0025_never_overwrites_a_measured_mk8():
    RoadmapKpi.objects.create(
        code="MK8", lane="mobile", name="x", current=0.0, measured_at=_sync25.DAY
    )
    assert _sync25.first_readings(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="MK8").current == 0.0


def test_0025_extends_the_dbt36_note_with_the_594_bytes():
    _item("DBT-36", "todo", 0)
    _sync25.sync_notes(RoadmapItem)
    note = RoadmapItem.objects.get(code="DBT-36").note
    assert "929 بايتاً" in note and "+703 بايتاً" in note and "ولم يُقَس المجموعُ" in note


def test_0025_moves_n041_to_67_as_published_but_not_visually_checked_and_never_closes_it():
    _item("N-041", "doing", 33, pr="#577")
    assert _sync25.sync(RoadmapItem) == ["N-041"]
    assert _sync25.sync(RoadmapItem) == []
    n041 = RoadmapItem.objects.get(code="N-041")
    assert (n041.status, n041.progress, n041.pr) == ("doing", 67, "#577 #584")
    note = n041.note
    # منشورٌ بقرار المالك بعد تحقّق 8033 المبكّر، وتحقّقُها النهائيّ باقٍ الأحد، ولا معاينةَ بصريّة، ولا يُغلق.
    assert (
        "منشورٌ على الإنتاج ضمن main@9acf2e1" in note
        and "869/869" in note
        and "أُلغي الـrevert" in note
    )
    assert "تحقّقُ 8033 النهائيّ يبقى صباحَ الأحد 2026-09-27" in note and "لم يُعاين بصريّاً" in note
    assert "عدُّ طلباتٍ لا جهد ولا يُغلق" in note and "#597" in note and "لم يدخل هذا النشر" in note
    assert "غيرُ منشور" not in note and "معلَّق" not in note


def test_0025_leaves_an_n041_the_developer_moved():
    _item("N-041", "done", 100)
    assert "N-041" not in _sync25.sync(RoadmapItem)
    assert RoadmapItem.objects.get(code="N-041").note == ""


def test_0025_moves_sch08_to_95_by_the_sessions_suggestion_never_to_100():
    _item("SCH-08", "doing", 90)
    assert _sync25.sync(RoadmapItem) == ["SCH-08"]
    assert _sync25.sync(RoadmapItem) == []
    sch08 = RoadmapItem.objects.get(code="SCH-08")
    assert (sch08.status, sch08.progress) == ("doing", 95)
    note = sch08.note
    # القياسُ الحقيقيّ 869/869، والثغرةُ وإصلاحُها (#596 قيد الفحوص) يُذكران، ولا 100% قبل النشر والقياس النهائيّ.
    assert "869 من 869" in note and "#596" in note and "قيد الفحوص" in note and "لا 100%" in note
    assert "2026-09-27" in note and "اقتراحُ 8033" in note and "أصلحها المالكُ بنفسه" in note


def test_0025_leaves_a_sch08_the_developer_moved():
    _item("SCH-08", "done", 100)
    assert "SCH-08" not in _sync25.sync(RoadmapItem)
    assert RoadmapItem.objects.get(code="SCH-08").note == ""


def test_0025_never_claims_a_publication_delay_reason_that_the_owner_decision_changed():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0025_sync_kpis_2026_09_25").origin
    body = open(origin, encoding="utf-8").read()
    assert not re.search("تعليق نشر|نشرُ main معلَّق|ينتظر تحقّق 8033|معلَّق النشر", body)
    assert "مدموجٌ غيرُ منشور" not in body


def test_0025_adds_a_dbt36_note_about_the_narrow_css_margin_without_moving_it():
    _item("DBT-36", "todo", 0)
    assert _sync25.sync_notes(RoadmapItem) == ["DBT-36"]
    assert _sync25.sync_notes(RoadmapItem) == []
    dbt36 = RoadmapItem.objects.get(code="DBT-36")
    assert (dbt36.status, dbt36.progress) == ("todo", 0)
    assert "929 بايتاً" in dbt36.note and "ولم يُقَس المجموعُ" in dbt36.note


def test_0025_leaves_a_rep03_the_developer_moved_or_a_rep03_still_at_todo():
    _item("REP-03", "todo", 0, gate="owner")
    assert _sync25.sync(RoadmapItem) == []
    rep03 = RoadmapItem.objects.get(code="REP-03")
    assert (rep03.status, rep03.progress, rep03.gate, rep03.note) == ("todo", 0, "owner", "")


def test_0025_adds_a_short_u03_note_without_touching_its_state_dates_or_dependencies():
    from datetime import date

    _item("U-03", "todo", 0, start_date=date(2026, 9, 21), end_date=date(2026, 9, 25), deps="U-01")
    assert _sync25.sync_notes(RoadmapItem) == ["U-03"]
    assert _sync25.sync_notes(RoadmapItem) == []
    u03 = RoadmapItem.objects.get(code="U-03")
    assert (u03.status, u03.progress, u03.deps) == ("todo", 0, "U-01")
    assert (str(u03.start_date), str(u03.end_date)) == ("2026-09-21", "2026-09-25")
    assert "لا تطابق" in u03.note and "لم يُغيَّر موعدُه ولا اعتماديّاتُه" in u03.note


def test_0025_widens_sch16_by_a_note_and_registers_no_doc_fix_debt_on_sch19():
    _item("SCH-16", "todo", 0)
    _item("SCH-19", "todo", 0)
    assert _sync25.sync_notes(RoadmapItem) == ["SCH-16"]
    assert _sync25.sync_notes(RoadmapItem) == []
    sch16 = RoadmapItem.objects.get(code="SCH-16")
    assert (sch16.status, sch16.progress) == ("todo", 0)
    assert (
        "998 من سقف 1000" in sch16.note
        and "يشمل المختبر" in sch16.note
        and "latest_baseline" in sch16.note
    )
    assert "لم يُغيَّر موعدُه ولا معيارُه" in sch16.note
    # تصحيحُ الترويسة أُصلح محلّياً عند 8033: لا دَينَ ولا ملاحظة على SCH-19.
    assert RoadmapItem.objects.get(code="SCH-19").note == ""


def test_0025_leaves_sch11_the_developer_moved():
    _item("SCH-11", "done", 100)
    assert _sync25.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-11").note == ""


def test_0025_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync25.forwards(_Apps25, None)
    assert RoadmapKpi.objects.count() == 0
    _seed_sk25()
    _item("SCH-11", "doing", 15)
    _sync25.forwards(_Apps25, None)

    def snapshot():
        return (
            list(
                RoadmapKpi.objects.order_by("code").values_list(
                    "code", "current", "history", "source"
                )
            ),
            list(RoadmapItem.objects.values_list("code", "status", "progress", "note")),
        )

    first = snapshot()
    _sync25.forwards(_Apps25, None)
    assert snapshot() == first


def test_0025_publishes_no_personal_number_and_no_hash():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0025_sync_kpis_2026_09_25").origin
    body = open(origin, encoding="utf-8").read()
    bs = chr(92)
    assert not re.search(bs + "b" + bs + "d{11}" + bs + "b", body)
    assert not re.search(bs + "b[0-9a-f]{40}" + bs + "b", body)


def test_0025_records_the_n041_reader_measurement_after_publication_as_a_read_not_a_visual_check():
    _item("N-041", "doing", 33, pr="#577")
    _sync25.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="N-041").note
    # قياسُ القارئ بعد النشر (869 خانةً، 0/0/0 فروقاً) قراءةٌ على الإنتاج لا معاينةٌ بصريّة للصفحة.
    assert "869 خانةً كلُّها source=actual" in note and "ناقص 0 وزائد 0 واختلاف 0" in note
    assert "قياسٌ للقارئ لا معاينةٌ بصريّةٌ للصفحة" in note and "source=plan" in note


def test_0025_records_the_591_production_check_and_that_dbt45_started_unpushed():
    _item("DBT-44", "done", 100, pr="#576")
    _sync25.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="DBT-44").note
    assert "تحقّقُ 8103 على الإنتاج" in note and "لم يُدفع" in note and "DBT-45" in note


# ── 0026: RD1 وRD3 (قراراتُ المالك) ومواعيدُ U-02/U-03 وميتا الخارطة وREP-02 وREP-05 و#596 وتصحيحُ توقيتَين ──

_sync26 = importlib.import_module("roadmap.migrations.0026_sync_items_2026_09_25f")


class _Apps26:
    @staticmethod
    def get_model(_app, name):
        return {
            "RoadmapKpi": RoadmapKpi,
            "RoadmapDecision": RoadmapDecision,
            "RoadmapMeta": RoadmapMeta,
        }.get(name, RoadmapItem)


_N041_OLD = (
    "قياسُ القارئ بعد النشر (8033، قراءةٌ على الإنتاج، الجمعة 2026-09-25 نحو 11:15 الدوحة): 869 خانة"
)
_SCH08_OLD = "**95% باقتراح 8033 (2026-09-25 نحو 10:50 الدوحة، قياسٌ قرائيٌّ على الإنتاج):** جلسات"


def _meta26(**over):
    data = {
        "windows": [
            "لا نشرَ الأحد–الخميس 07:00–14:00 بتوقيت الدوحة.",
            "نافذة الجمعة 2026-09-25 (عطلة المدرسة): U-01 ثم U-03 — نسخة مرآة لا على المجلّد مباشرة، وكلّ جلسات Claude مغلقة.",
            "نطاقُ التنظيف كما في الخطّة.",
        ],
        "rules": [
            "قاعدةٌ أخرى.",
            "نافذة الجمعة 2026-09-25 محجوزة لـU-01/U-03؛ لا عمل موازٍ فيها.",
        ],
        "milestones": [
            {
                "d": "2026-09-25",
                "name": "نافذة الجمعة: U-01 ثم U-03 (تدوير المفتاح وتنظيف التاريخ) — لا جلسات Claude",
            },
            {"d": "2026-10-08", "name": "موعد U-04"},
        ],
        "criticalPath": [
            "U-02 مصير الفروع المفتوحة (قبل 09-24) لأنّ إعادة كتابة التاريخ تكسر كلّ فرعٍ مفتوح.",
            "U-01 إصلاح الأعمدة المشفَّرة.",
            "U-03 تدوير المفتاح + تنظيف التاريخ في نافذةٍ واحدة معزولة بلا جلساتٍ متوازية.",
        ],
        "phases": [
            {
                "key": "P0",
                "goal": "خطوط أساس مسجَّلة، وU-01/U-02/U-03 في نافذة الجمعة 09-25 (كلّ جلسات Claude مغلقة)",
                "start": "2026-09-21",
                "end": "2026-09-27",
            }
        ],
    }
    data.update(over)
    return RoadmapMeta.objects.create(key="roadmap", data=data)


def _seed_rd26():
    from datetime import date

    for code in ("RD1", "RD3", "RD4"):
        RoadmapDecision.objects.create(
            code=code, title=f"قرار {code}", status="open", recommendation="توصية"
        )
    _item(
        "U-02",
        "doing",
        50,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 24),
        deps="—",
        criterion="قرار مسجّل لكل فرع",
    )
    _item(
        "U-03",
        "todo",
        0,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 25),
        deps="U-01، U-02، إغلاق كل جلسات Claude وقتها",
        criterion="K7=0 وعدّاد decrypt_field الفاشل = 0 بعد التدوير",
    )


def test_0026_corrects_the_two_estimated_times_once_and_only_where_the_old_text_survives():
    _item("N-041", "doing", 67, note=f"[2026-09-25] {_N041_OLD}")
    _item("SCH-08", "doing", 95, note=f"[2026-09-25] {_SCH08_OLD}")
    assert _sync26.correct(RoadmapItem) == ["N-041", "SCH-08"]
    assert _sync26.correct(RoadmapItem) == []
    n041 = RoadmapItem.objects.get(code="N-041").note
    sch08 = RoadmapItem.objects.get(code="SCH-08").note
    assert "نحو 10:00 الدوحة" in n041 and "11:15" not in n041
    assert "(صباحَ 2026-09-25، قياسٌ قرائيٌّ على الإنتاج)" in sch08 and "10:50" not in sch08
    # باقي النصّ سليم.
    assert n041.endswith("869 خانة") and sch08.endswith("جلسات")


def test_0026_leaves_a_note_the_developer_already_rewrote_without_the_estimated_time():
    _item("N-041", "doing", 67, note="كتب المطوّر ملاحظته بنفسه")
    assert _sync26.correct(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-041").note == "كتب المطوّر ملاحظته بنفسه"


def test_0026_records_596_merged_but_unpublished_and_keeps_sch08_at_95():
    _item("SCH-08", "doing", 95, pr="#548")
    assert _sync26.sync(RoadmapItem) == ["SCH-08"]
    assert _sync26.sync(RoadmapItem) == []
    sch08 = RoadmapItem.objects.get(code="SCH-08")
    assert (sch08.status, sch08.progress, sch08.pr) == ("doing", 95, "#548 #596")
    note = sch08.note
    assert "c7e97cc3" in note and "لم يُنشر بعدُ" in note and "تبقى النسبةُ 95%" in note
    assert "2026-09-27" in note and "06:47" in note and "اقتراحُ 8033" in note


def test_0026_leaves_an_sch08_the_developer_moved():
    _item("SCH-08", "done", 100)
    assert _sync26.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-08").note == ""


def test_0026_never_overflows_the_pr_field_limit():
    crowded = " ".join(f"#{n}" for n in range(500, 513))
    assert len(crowded) == 64
    _item("SCH-08", "doing", 95, pr=crowded)
    assert _sync26.sync(RoadmapItem) == ["SCH-08"]
    sch08 = RoadmapItem.objects.get(code="SCH-08")
    # الحقلُ لا يتجاوز 64 ويبقى كما هو، والملاحظةُ تُلحق.
    assert sch08.pr == crowded and "#596 اندمج" in sch08.note


def test_0026_moves_rep02_to_doing_25_with_a_neutral_sentence_and_keeps_its_gate():
    _item("REP-02", "todo", 0, gate="owner")
    assert _sync26.sync(RoadmapItem) == ["REP-02"]
    assert _sync26.sync(RoadmapItem) == []
    rep02 = RoadmapItem.objects.get(code="REP-02")
    assert (rep02.status, rep02.progress, rep02.gate) == ("doing", 25, "owner")
    note = rep02.note
    assert "سُجّلت المراجعةُ في وحدة /breach/ (2026-09-25)" in note
    assert "التقييمُ والقرارُ عند المسؤول (RD4 مفتوح)" in note
    # النسبةُ اقتراحٌ باشتقاقٍ صريح لا قياس، وقرارُ الحالة للمالك.
    assert "خطوةٌ من أربعٍ متساوية" in note and "اقتراحُ جلسة Git لا قياس" in note
    assert "قرارُ الحالة والنسبة للمالك" in note
    for term in ("الحادثة", "قيد التقييم", "تسرّب", "تسريب"):
        assert term not in note


def test_0026_leaves_a_rep02_the_owner_or_git_session_already_moved():
    _item("REP-02", "doing", 50, gate="owner")
    assert _sync26.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="REP-02").note == ""


def test_0026_closes_rep05_and_clears_its_gate_without_names_or_counts():
    _item("REP-05", "todo", 0, gate="owner")
    assert _sync26.sync(RoadmapItem) == ["REP-05"]
    assert _sync26.sync(RoadmapItem) == []
    rep05 = RoadmapItem.objects.get(code="REP-05")
    assert (rep05.status, rep05.progress, rep05.gate) == ("done", 100, "")
    assert "REP-05 منجز" in rep05.note and "RK2 = 0" in rep05.note and "REP-08" in rep05.note
    assert "قرارُ المالك ولا يمسّ هذا الإغلاق" in rep05.note
    assert "wave" not in rep05.note and "archive/" not in rep05.note


def test_0026_leaves_a_rep05_the_developer_moved():
    _item("REP-05", "doing", 40, gate="owner")
    assert _sync26.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="REP-05").gate == "owner"


def test_0026_records_rk2_at_zero_keeping_the_baseline_and_appending_a_history_point():
    _kpi(
        "RK2",
        5.0,
        _sync26.DAY,
        source="مقارنةُ الفروع بـmain",
        history=[{"d": "2026-09-25", "v": 5.0}],
    )
    assert _sync26.sync_kpis(RoadmapKpi) == ["RK2"]
    assert _sync26.sync_kpis(RoadmapKpi) == []
    kpi = RoadmapKpi.objects.get(code="RK2")
    assert (kpi.current, kpi.baseline, kpi.measured_at) == (0.0, 5.0, _sync26.DAY)
    assert kpi.history == [{"d": "2026-09-25", "v": 0.0}]
    assert "بعد REP-05" in kpi.source


def test_0026_leaves_an_rk2_that_was_remeasured():
    _kpi("RK2", 2.0, _sync26.DAY)
    assert _sync26.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="RK2").current == 2.0


def test_0026_adds_the_lay03_performance_budget_caution_as_a_note_only():
    _item("LAY-03", "doing", 50)
    assert _sync26.sync_notes(RoadmapItem) == ["LAY-03"]
    assert _sync26.sync_notes(RoadmapItem) == []
    lay03 = RoadmapItem.objects.get(code="LAY-03")
    assert (lay03.status, lay03.progress) == ("doing", 50)
    assert (
        "CLS 0.074" in lay03.note
        and "سقف 0.1" in lay03.note
        and "test_web_vitals_budget" in lay03.note
    )
    assert "لم تُغيَّر الحالةُ ولا التقدّمُ ولا الموعد" in lay03.note


def test_0026_decides_rd1_and_rd3_only_and_leaves_rd4_open():
    _seed_rd26()
    assert _sync26.decide(RoadmapDecision) == ["RD1", "RD3"]
    assert _sync26.decide(RoadmapDecision) == []
    for code in ("RD1", "RD3"):
        d = RoadmapDecision.objects.get(code=code)
        assert (d.status, d.decision_date) == ("decided", _sync26.DAY), code
        assert "أكّده لجلسة Git ثمّ لجلسة الخارطة مباشرةً" in d.recommendation, code
    assert "يبقى المستودعُ عامّاً حتى نافذة إعادة الكتابة" in (
        RoadmapDecision.objects.get(code="RD1").recommendation
    )
    rd3 = RoadmapDecision.objects.get(code="RD3").recommendation
    assert "الجمعة 2026-10-02" in rd3 and "10-01 بعد 14:00" in rd3 and "السبتَ 10-03" in rd3
    rd4 = RoadmapDecision.objects.get(code="RD4")
    assert (rd4.status, rd4.decision_date, rd4.recommendation) == ("open", None, "توصية")


def test_0026_keeps_a_decision_the_owner_already_took_differently():
    RoadmapDecision.objects.create(code="RD1", title="x", status="deferred", recommendation="أجّله")
    RoadmapDecision.objects.create(code="RD3", title="x", status="decided", recommendation="حسمه")
    assert _sync26.decide(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="RD1").status == "deferred"
    assert RoadmapDecision.objects.get(code="RD3").recommendation == "حسمه"


def test_0026_moves_u02_and_u03_by_rd3_without_touching_status_or_progress():
    _seed_rd26()
    assert _sync26.reschedule(RoadmapItem) == ["U-02", "U-03"]
    assert _sync26.reschedule(RoadmapItem) == []
    u02 = RoadmapItem.objects.get(code="U-02")
    assert (u02.status, u02.progress) == ("doing", 50)
    assert (str(u02.start_date), str(u02.end_date)) == ("2026-09-21", "2026-09-29")
    assert u02.deps == "REP-05" and u02.criterion == "قرار مسجّل لكل فرع"
    assert "قرارُ المالك RD3" in u02.date_basis and "2026-09-24" in u02.date_basis
    assert "يُغلق بإغلاق REP-05" in u02.note and "لم تُغيَّر حالتُه ولا تقدّمُه" in u02.note
    u03 = RoadmapItem.objects.get(code="U-03")
    assert (u03.status, u03.progress) == ("todo", 0)
    assert (str(u03.start_date), str(u03.end_date)) == ("2026-10-01", "2026-10-03")
    assert u03.deps == (
        "U-01، U-02، إغلاق كل جلسات Claude وقتها، REP-01، REP-03، REP-06، REP-07، REP-08، RD1، RD3، RD7"
    )
    assert u03.criterion == (
        "K7=0 وعدّاد decrypt_field الفاشل = 0 بعد التدوير؛ التحقّقُ يفتح الأرشيفات (RK4 = 0)"
    )
    assert "الجمعةَ 2026-10-02" in u03.note and "الخميسَ 10-01 بعد 14:00" in u03.note


def test_0026_does_not_duplicate_dependencies_already_present():
    _seed_rd26()
    u03 = RoadmapItem.objects.get(code="U-03")
    u03.deps = "U-01، REP-01، RD3"
    u03.save()
    _sync26.reschedule(RoadmapItem)
    deps = RoadmapItem.objects.get(code="U-03").deps
    assert deps.count("REP-01") == 1 and deps.count("RD3") == 1
    assert deps.startswith("U-01، REP-01، RD3، REP-03")


def test_0026_leaves_a_u03_or_u02_the_developer_moved():
    from datetime import date

    _seed_rd26()
    u03 = RoadmapItem.objects.get(code="U-03")
    u03.end_date = date(2026, 10, 9)
    u03.save()
    RoadmapItem.objects.filter(code="U-02").update(progress=70)
    assert _sync26.reschedule(RoadmapItem) == []
    assert str(RoadmapItem.objects.get(code="U-03").end_date) == "2026-10-09"
    assert RoadmapItem.objects.get(code="U-02").note == ""


def test_0026_edits_only_the_window_text_milestone_and_critical_path_in_the_meta():
    _meta26()
    assert sorted(_sync26.edit_meta(RoadmapMeta)) == [
        "criticalPath",
        "milestones",
        "rules",
        "windows",
    ]
    assert _sync26.edit_meta(RoadmapMeta) == []
    data = RoadmapMeta.objects.get(key="roadmap").data
    assert data["windows"][1].startswith(
        "نافذة الجمعة 2026-10-02 (عطلة المدرسة؛ تبدأ الخميس 10-01 بعد 14:00"
    )
    assert "U-03 بعد U-01 — نسخة مرآة" in data["windows"][1]
    assert data["windows"][0] == "لا نشرَ الأحد–الخميس 07:00–14:00 بتوقيت الدوحة."
    assert data["windows"][2] == "نطاقُ التنظيف كما في الخطّة."
    assert data["rules"][0] == "قاعدةٌ أخرى."
    assert data["rules"][1].startswith("نافذة U-03 الجمعة 2026-10-02") and "RD3" in data["rules"][1]
    assert data["milestones"][0]["d"] == "2026-10-02"
    assert data["milestones"][0]["name"].startswith("نافذة الجمعة: U-03 بعد U-01 (تدوير المفتاح")
    assert data["milestones"][0]["name"].endswith("— قرارُ المالك RD3 2026-09-25")
    assert data["milestones"][1] == {"d": "2026-10-08", "name": "موعد U-04"}
    assert "(قبل 09-29)" in data["criticalPath"][0] and "(قبل 09-24)" not in data["criticalPath"][0]
    assert data["criticalPath"][1] == "U-01 إصلاح الأعمدة المشفَّرة."
    assert data["criticalPath"][2].endswith(
        "نافذتُه الجمعة 2026-10-02 (قرارُ المالك RD3 2026-09-25)."
    )


def test_0026_leaves_the_phase_goal_and_the_u01_wording_untouched():
    _meta26()
    _sync26.edit_meta(RoadmapMeta)
    data = RoadmapMeta.objects.get(key="roadmap").data
    # وصفُ هدف المرحلة P0 بنيةُ المالك؛ يُبلَّغ تناقضُه مع RD3 ولا يُعدَّل هنا.
    assert data["phases"][0]["goal"].endswith("في نافذة الجمعة 09-25 (كلّ جلسات Claude مغلقة)")
    assert data["phases"][0]["end"] == "2026-09-27"
    assert data["criticalPath"][1].startswith("U-01 ")


def test_0026_leaves_a_meta_the_owner_already_edited_and_tolerates_a_missing_or_odd_meta():
    assert _sync26.edit_meta(RoadmapMeta) == []
    _meta26(
        windows=["نافذةٌ حرّرها المالك"],
        rules=["قاعدةٌ حرّرها المالك"],
        milestones=[{"d": "2026-10-02", "name": "حرّره المالك"}],
        criticalPath=["U-03 تدوير المفتاح، نافذتُه الجمعة 2026-10-02 (بتحرير المالك)"],
    )
    before = RoadmapMeta.objects.get(key="roadmap").data
    assert _sync26.edit_meta(RoadmapMeta) == []
    assert RoadmapMeta.objects.get(key="roadmap").data == before
    RoadmapMeta.objects.filter(key="roadmap").update(
        data={"windows": "ليست قائمة", "milestones": 3}
    )
    assert _sync26.edit_meta(RoadmapMeta) == []


def test_0026_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync26.forwards(_Apps26, None)
    assert RoadmapMeta.objects.count() == 0 and RoadmapDecision.objects.count() == 0
    _seed_rd26()
    _meta26()
    _kpi("RK2", 5.0, _sync26.DAY)
    _item("SCH-08", "doing", 95, pr="#548", note=f"[2026-09-25] {_SCH08_OLD}")
    _item("N-041", "doing", 67, note=f"[2026-09-25] {_N041_OLD}")
    for code, status, progress in (
        ("REP-02", "todo", 0),
        ("REP-05", "todo", 0),
        ("LAY-03", "doing", 50),
    ):
        _item(code, status, progress)
    _sync26.forwards(_Apps26, None)

    def snapshot():
        return (
            list(
                RoadmapItem.objects.order_by("code").values_list(
                    "code", "status", "progress", "deps", "note"
                )
            ),
            list(
                RoadmapDecision.objects.order_by("code").values_list(
                    "code", "status", "recommendation"
                )
            ),
            list(RoadmapKpi.objects.values_list("code", "current", "history", "source")),
            RoadmapMeta.objects.get(key="roadmap").data,
        )

    first = snapshot()
    _sync26.forwards(_Apps26, None)
    assert snapshot() == first


def test_0026_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0026_sync_items_2026_09_25f").origin
    body = open(origin, encoding="utf-8").read()
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "غيرُ صفر",
        "كم شخصاً",
        "التاريخ العامّ",
        "بصمات",
        "الحادثة",
        "قيد التقييم",
        "wave2",
        "archive/",
        "كلمةٌ افتراضيّةٌ",
        "رقمٌ حقيقيّ",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
    assert "تعليق نشر" not in body and "معلَّق النشر" not in body and "نشرُ main معلَّق" not in body


# ── 0027: ما نُشر بـmain@f42633b وما اندمج بعده (#586 و#597 و#601)، وتقدّمُ REP-06، وتصحيحُ «غيرُ منشور» ──

_sync27 = importlib.import_module("roadmap.migrations.0027_sync_items_2026_09_25g")


class _Apps27:
    @staticmethod
    def get_model(_app, name):
        return RoadmapKpi if name == "RoadmapKpi" else RoadmapItem


def test_0027_corrects_the_sch08_note_written_by_0026_to_published_and_keeps_it_at_95():
    _item("SCH-08", "doing", 95, pr="#548")
    assert _sync26.sync(RoadmapItem) == ["SCH-08"]
    assert "لم يُنشر بعدُ" in RoadmapItem.objects.get(code="SCH-08").note
    assert _sync27.correct(RoadmapItem) == ["SCH-08"]
    assert _sync27.correct(RoadmapItem) == []
    sch08 = RoadmapItem.objects.get(code="SCH-08")
    note = sch08.note
    assert (sch08.status, sch08.progress) == ("doing", 95)
    assert "منشورٌ على الإنتاج ضمن main@f42633b" in note and "869 من 869" in note
    assert "لم يُنشر بعدُ" not in note and "حتى يُنشر ويُقاس" not in note
    assert "حتى يُقاس نهائيّاً صباحَ الأحد 2026-09-27" in note and "تبقى النسبةُ 95%" in note


def test_0027_corrects_the_lay03_and_dbt36_phrases_written_by_0025():
    _item("LAY-03", "doing", 50, pr="#567 #585")
    _item("DBT-36", "todo", 0)
    assert _sync25.sync(RoadmapItem) == ["LAY-03"]
    assert _sync25.sync_notes(RoadmapItem) == ["DBT-36"]
    lay03_before = RoadmapItem.objects.get(code="LAY-03").note
    assert "غيرُ منشورٍ بعدُ" in lay03_before and "#586 قيد الطابور" in lay03_before
    assert _sync27.correct(RoadmapItem) == ["LAY-03", "DBT-36"]
    assert _sync27.correct(RoadmapItem) == []
    lay03 = RoadmapItem.objects.get(code="LAY-03").note
    assert "#587 مدموجٌ (b46534f6، 2026-09-25 06:57Z) ومنشورٌ ضمن main@f42633b:" in lay03
    assert "و#586 مدموجٌ (868e5f85، 07:43Z) ومنشورٌ ضمن main@f42633b:" in lay03
    assert "قيد الطابور" not in lay03 and "غيرُ منشورٍ بعدُ" not in lay03
    dbt36 = RoadmapItem.objects.get(code="DBT-36").note
    assert "(#586 و#587 مدموجان)" in dbt36 and "#586 قيد الطابور" not in dbt36


def test_0027_corrects_the_n041_and_own23_phrases_written_by_0025():
    _item("N-041", "doing", 33, pr="#577")
    _item("OWN-23", "todo", 0, gate="owner")
    assert sorted(_sync25.sync(RoadmapItem)) == ["N-041", "OWN-23"]
    assert "ولم يدخل هذا النشر" in RoadmapItem.objects.get(code="N-041").note
    assert "ولم تُدفع بانتظار إذنٍ صريح" in RoadmapItem.objects.get(code="OWN-23").note
    assert _sync27.correct(RoadmapItem) == ["N-041", "OWN-23"]
    assert _sync27.correct(RoadmapItem) == []
    n041 = RoadmapItem.objects.get(code="N-041").note
    assert "صار مدموجاً (f42633bf) ومنشوراً ضمن main@f42633b" in n041
    assert "ولم يدخل هذا النشر" not in n041 and "مفتوحٌ بدمجٍ مفعَّلٍ" not in n041
    own23 = RoadmapItem.objects.get(code="OWN-23").note
    assert "بُنيت واندمجت في #601 ونُشرت ضمن main@e7c461d" in own23
    assert "ولم تُدفع بانتظار إذنٍ صريح" not in own23


def test_0027_corrects_the_dbt44_phrase_about_dbt45_being_on_an_unpushed_branch():
    _item("DBT-44", "done", 100, pr="#576")
    assert _sync25.sync(RoadmapItem) == ["DBT-44"]
    assert "بدأته 8103 على فرعٍ محلّيّ لم يُدفع" in RoadmapItem.objects.get(code="DBT-44").note
    assert _sync27.correct(RoadmapItem) == ["DBT-44"]
    assert _sync27.correct(RoadmapItem) == []
    note = RoadmapItem.objects.get(code="DBT-44").note
    assert "صار #600 مدموجاً وسطحُ المكتب 0 من 491" in note and "لم يُدفع" not in note


def test_0027_closes_dbt45_by_600_published_with_the_ci_baseline():
    _item("DBT-45", "todo", 0)
    assert _sync27.sync(RoadmapItem) == ["DBT-45"]
    assert _sync27.sync(RoadmapItem) == []
    dbt45 = RoadmapItem.objects.get(code="DBT-45")
    assert (dbt45.status, dbt45.progress, dbt45.pr) == ("done", 100, "#600")
    note = dbt45.note
    # نُشر #600 في main@ff70a32 بتحقّق 8103 على الإنتاج (القاعدةُ العامّةُ للخانات في CSS المبصوم).
    assert "ea95a261" in note and "منشورٌ على الإنتاج ضمن main@ff70a32" in note
    assert "تحقّقُ 8103 على الإنتاج" in note and "خارجَ كتلة coarse" in note
    assert "غيرُ منشور" not in note and "بعد نشره" not in note
    assert (
        "0 من 491" in note and "0 من 431 (Chromium) و0 من 434 (WebKit)" in note and "K2 = 0" in note
    )
    assert "قياسٌ لا إعفاء" in note and "23 من 23" in note
    assert "صافي −282 بايتاً" in note


def test_0027_leaves_a_dbt45_the_developer_moved():
    _item("DBT-45", "doing", 60)
    assert _sync27.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="DBT-45").note == ""


def test_0027_records_mk1_at_zero_and_mk2_kept_at_zero_keeping_history():
    _kpi(
        "MK1",
        0.2,
        _sync25.PREVIOUS,
        source="خطّة الجوال K1",
        history=[{"d": "2026-09-24", "v": 0.2}],
    )
    _kpi(
        "MK2",
        0.0,
        _sync25.PREVIOUS,
        source="خطّة الجوال K2",
        history=[{"d": "2026-09-24", "v": 0.0}],
    )
    assert _sync27.sync_kpis(RoadmapKpi) == ["MK1", "MK2"]
    assert _sync27.sync_kpis(RoadmapKpi) == []
    mk1 = RoadmapKpi.objects.get(code="MK1")
    assert (mk1.current, mk1.measured_at) == (0.0, _sync27.DAY)
    assert mk1.history == [{"d": "2026-09-24", "v": 0.2}, {"d": "2026-09-25", "v": 0.0}]
    assert "Chromium 0 من 431 وWebKit 0 من 434" in mk1.source
    assert RoadmapKpi.objects.get(code="MK2").current == 0.0


def test_0027_leaves_an_mk1_that_was_remeasured():
    _kpi("MK1", 0.1, _sync25.PREVIOUS)
    assert _sync27.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="MK1").current == 0.1


def test_0027_leaves_a_note_the_developer_already_rewrote():
    _item("SCH-08", "doing", 95, note="كتب المطوّر ملاحظته بنفسه")
    _item("LAY-03", "doing", 50, note="ملاحظةٌ أخرى")
    assert _sync27.correct(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="SCH-08").note == "كتب المطوّر ملاحظته بنفسه"
    assert RoadmapItem.objects.get(code="LAY-03").note == "ملاحظةٌ أخرى"


def test_0027_closes_n041_at_3_of_3_with_the_three_reservations_and_keeps_d21_open():
    _item("N-041", "doing", 67, pr="#577 #584")
    assert _sync27.sync(RoadmapItem) == ["N-041"]
    assert _sync27.sync(RoadmapItem) == []
    n041 = RoadmapItem.objects.get(code="N-041")
    assert (n041.status, n041.progress, n041.pr) == ("done", 100, "#577 #584 #597")
    note = n041.note
    assert "منشورٌ على الإنتاج ضمن main@f42633b" in note and "N-041 → منجز 3/3" in note
    assert "(1) لم تُعاين الورقةُ وPDF وExcel بصرياً على الإنتاج" in note
    # قياسُ 8061 اللاحقُ محلّيٌّ لا على الإنتاج، فيُسقط تحفّظَ تقسيم صفحات PDF ويُبقي معاينةَ الإنتاج عند المالك.
    assert "(2) صفحاتُ «جدول لكلّ معلّم/شعبة» تبقى على الخطّة عمداً" in note
    assert "على قاعدة جلستها المحلّيّة لا الإنتاج" in note and "8751 حصّة أيّام" in note
    assert "صفحةٌ واحدة كالخطّة" in note and "شريطٍ 13.6mm بلا قصّ" in note
    assert "A1:AL81 للعامّ، A1:J11 للمعلّم" in note and "مقيسٌ محلّياً: صفحةٌ واحدة" in note
    assert "ويبقى (1) معاينةُ الإنتاج نفسِه بصرياً عند المالك" in note
    assert "لم يُقَس تقسيمُ صفحات PDF" not in note
    assert "عدُّ طلباتٍ (3 من 3) لا جهد" in note and "D-21 ما زال مفتوحاً" in note
    assert "12 اختباراً جديداً" in note and "سقطت الأربعةُ قبل إصلاحين" in note


def test_0027_leaves_an_n041_the_developer_moved():
    _item("N-041", "doing", 90)
    assert _sync27.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-041").note == ""


def test_0027_moves_own23_to_60_by_8096s_suggestion_keeping_its_gate_and_recording_it_published():
    _item("OWN-23", "doing", 30, pr="#593", gate="owner")
    assert _sync27.sync(RoadmapItem) == ["OWN-23"]
    assert _sync27.sync(RoadmapItem) == []
    own23 = RoadmapItem.objects.get(code="OWN-23")
    assert (own23.status, own23.progress, own23.pr, own23.gate) == (
        "doing",
        60,
        "#593 #601",
        "owner",
    )
    note = own23.note
    assert "core.refresh_backup_status" in note and "أخضرُ ≤ 30 ساعة" in note
    # نُشر #601 في main@e7c461d بإخطارٍ ثانٍ من جلسة النشر؛ والمعاينةُ المرسومةُ لـ/admin/ عند المالك فلا «تحقّق مرسوم».
    assert "منشورٌ على الإنتاج ضمن main@e7c461d" in note and "مهامُّ Celery 29 (كانت 28)" in note
    assert "لم يُعاين /admin/ مرسوماً على الإنتاج" in note and "فلا يُسجَّل «تحقّق مرسوم»" in note
    assert "غيرُ منشورٍ" not in note
    # النسبةُ اقتراحٌ باشتقاقٍ صريح لا قياس، والتنبيهُ عند الأحمر باقٍ فالبندُ مفتوح.
    assert "اقتراحُ 8096" in note and "لا قياس" in note and "فالبندُ مفتوح" in note
    assert "الحالةُ القديمةُ (> 3 ساعات) تُوسَم ولا تُطمئن" in note


def test_0027_leaves_an_own23_the_developer_moved():
    _item("OWN-23", "doing", 45, gate="owner")
    assert _sync27.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="OWN-23").note == ""


def test_0027_records_lay03_586_with_the_measurement_and_leaves_state_dates_untouched():
    from datetime import date

    _item(
        "LAY-03",
        "doing",
        50,
        pr="#567 #585",
        start_date=date(2026, 10, 19),
        end_date=date(2026, 11, 6),
    )
    assert _sync27.sync(RoadmapItem) == ["LAY-03"]
    assert _sync27.sync(RoadmapItem) == []
    lay03 = RoadmapItem.objects.get(code="LAY-03")
    assert (lay03.status, lay03.progress, lay03.pr) == ("doing", 50, "#567 #585 #586")
    assert (str(lay03.start_date), str(lay03.end_date)) == ("2026-10-19", "2026-11-06")
    note = lay03.note
    assert "164 صفحةً × 6 عروض" in note and "984 خليّة" in note and "405px ← 0" in note
    assert "تكتمل ثلاثيّةُ إصلاحات ADR-0006 (#585 و#586 و#587)" in note and "LAY-08" in note


def test_0027_closes_rep06_at_5_of_5_and_never_records_rk4_at_zero():
    _kpi("RK4", 12.0, _sync26.DAY)
    _item("REP-06", "todo", 0)
    assert _sync27.sync(RoadmapItem) == ["REP-06"]
    assert _sync27.sync(RoadmapItem) == []
    rep06 = RoadmapItem.objects.get(code="REP-06")
    assert (rep06.status, rep06.progress) == ("done", 100)
    note = rep06.note
    assert "بروفةُ إعادة الكتابة على مرآة ناجحة (RK4 = 0 على الناتج)" in note
    assert "5 من 5 خطواتٍ متساوية" in note and "إفادةُ جلسة Git" in note
    assert "الصفرُ للبروفة وحدها" in note and "لا يُسجَّل RK4 = 0 في المؤشّر قبل نافذة 10-02" in note
    # المؤشّرُ نفسُه لا يُمسّ، ولا وصفَ لحالة المستودع العامّ.
    assert RoadmapKpi.objects.get(code="RK4").current == 12.0
    assert "غيرُ صفر" not in note and "المستودع العامّ" not in note


def test_0027_moves_rep07_to_60_with_a_derivation_and_defers_rk5_to_the_merge():
    _item("REP-07", "todo", 0)
    assert _sync27.sync(RoadmapItem) == ["REP-07"]
    assert _sync27.sync(RoadmapItem) == []
    rep07 = RoadmapItem.objects.get(code="REP-07")
    assert (rep07.status, rep07.progress) == ("doing", 60)
    note = rep07.note
    assert "3 من 5 خطواتٍ متساوية" in note and "اقتراحُ جلسة Git لا قياس" in note
    assert "RK5 = 0 يُسجَّل عند اندماج الطلب لا قبله" in note
    for term in ("يسقط على main", "scripts/", ".py", "قيمة حقيقيّة"):
        assert term not in note


def test_0027_leaves_a_rep06_or_rep07_the_git_session_already_moved():
    _item("REP-06", "doing", 90)
    _item("REP-07", "done", 100)
    assert _sync27.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="REP-06").note == ""
    assert RoadmapItem.objects.get(code="REP-07").note == ""


def test_0027_adds_the_dbt36_margin_note_without_moving_it():
    _item("DBT-36", "todo", 0)
    assert _sync27.sync_notes(RoadmapItem) == ["DBT-36"]
    assert _sync27.sync_notes(RoadmapItem) == []
    dbt36 = RoadmapItem.objects.get(code="DBT-36")
    assert (dbt36.status, dbt36.progress) == ("todo", 0)
    assert "481,649 بايتاً من سقف 481,791" in dbt36.note and "هامشٌ 142 بايتاً فقط" in dbt36.note
    assert "129 بايتاً" in dbt36.note and "لم تُغيَّر الحالةُ ولا الموعد" in dbt36.note
    # بعد #600 (8103): 481,778 ← 481,496 والهامشُ 295 بعد أن كان 13.
    assert "481,778 ← 481,496" in dbt36.note and "صافي −282 بايتاً" in dbt36.note
    assert "الهامشُ الآن **295 بايتاً**" in dbt36.note


def test_0027_never_overflows_the_pr_field_limit():
    crowded = " ".join(f"#{n}" for n in range(500, 513))
    _item("OWN-23", "doing", 30, pr=crowded, gate="owner")
    assert _sync27.sync(RoadmapItem) == ["OWN-23"]
    own23 = RoadmapItem.objects.get(code="OWN-23")
    assert own23.pr == crowded and own23.progress == 60


def test_0027_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync27.forwards(_Apps27, None)
    assert RoadmapItem.objects.count() == 0
    _item("SCH-08", "doing", 95, pr="#548")
    _sync26.sync(RoadmapItem)
    _item("LAY-03", "doing", 50)
    _item("DBT-36", "todo", 0)
    _sync25.sync(RoadmapItem)
    _sync25.sync_notes(RoadmapItem)
    _item("N-041", "doing", 67, pr="#577 #584")
    _item("OWN-23", "doing", 30, pr="#593", gate="owner")
    _item("REP-06", "todo", 0)
    _sync27.forwards(_Apps27, None)

    def snapshot():
        return list(
            RoadmapItem.objects.order_by("code").values_list(
                "code", "status", "progress", "pr", "note"
            )
        )

    first = snapshot()
    _sync27.forwards(_Apps27, None)
    assert snapshot() == first


def test_0027_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0027_sync_items_2026_09_25g").origin
    body = open(origin, encoding="utf-8").read()
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "غيرُ صفر",
        "كم شخصاً",
        "التاريخ العامّ",
        "بصمات",
        "الحادثة",
        "قيد التقييم",
        "wave2",
        "archive/",
        "كلمةٌ افتراضيّةٌ",
        "رقمٌ حقيقيّ",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
    assert "تعليق نشر" not in body and "معلَّق النشر" not in body and "نشرُ main معلَّق" not in body


# ── 0028: قراراتُ المالك المؤكَّدة مباشرةً (2026-09-25) وما يترتّب عليها ──

_sync28 = importlib.import_module("roadmap.migrations.0028_owner_decisions_2026_09_25b")


class _Apps28:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapKpi": RoadmapKpi, "RoadmapDecision": RoadmapDecision}.get(name, RoadmapItem)


def _seed_decisions28(only=None):
    for code, expected, _status, _due, _line in _sync28.DECISIONS:
        if only is None or code in only:
            RoadmapDecision.objects.create(
                code=code,
                title=f"قرار {code}",
                status=expected,
                due="مفتوح",
                recommendation="توصية",
            )


def test_0028_decides_the_confirmed_decisions_and_only_notes_the_rest():
    _seed_decisions28()
    changed = _sync28.decide(RoadmapDecision)
    assert changed == [code for code, *_ in _sync28.DECISIONS]
    assert _sync28.decide(RoadmapDecision) == []
    for code, expected, status, due, line in _sync28.DECISIONS:
        d = RoadmapDecision.objects.get(code=code)
        assert d.status == status, code
        assert line in d.recommendation and d.recommendation.startswith("توصية"), code
        # الحسمُ/التأجيلُ يكتب تاريخَه؛ والملاحظةُ وحدَها (RD4 وD-06 وMD10 وMD13) لا تكتبه.
        assert (d.decision_date == _sync28.DAY) == (status != expected), code
        if due:
            assert d.due == due, code


def test_0028_decides_exactly_the_decisions_the_owner_confirmed_and_defers_the_three_he_postponed():
    by_code = {code: status for code, _e, status, _d, _l in _sync28.DECISIONS}
    assert sorted(c for c, s in by_code.items() if s == "decided") == sorted(
        [
            "RD5",
            "RD7",
            "RD8",
            "D-01",
            "D-02",
            "D-03",
            "D-04",
            "D-05",
            "D-07",
            "D-14",
            "D-15",
            "D-23",
            "D-24",
            "MD2",
            "MD3",
            "MD4",
            "MD13",
        ]
    )
    assert sorted(c for c, s in by_code.items() if s == "deferred") == ["D-09", "MD5", "RD6"]
    # ما لم يؤكّده المالك أو أبقاه مفتوحاً لا يُحسم.
    for code in ("RD4", "D-06", "MD10"):
        assert by_code[code] == "open", code
    for code in ("D-08", "D-21", "D-22", "OWN-03"):
        assert code not in by_code


def test_0028_keeps_rd4_open_with_the_saturday_date_and_states_the_decision_is_still_the_owners():
    _seed_decisions28({"RD4"})
    _sync28.decide(RoadmapDecision)
    rd4 = RoadmapDecision.objects.get(code="RD4")
    assert (rd4.status, rd4.decision_date, rd4.due) == ("open", None, "2026-09-26")
    assert "الموعدُ لا القرار" in rd4.recommendation and "ويبقى مفتوحاً" in rd4.recommendation


def test_0028_states_that_rd5_replaces_the_original_option_and_counts_no_branches():
    import re

    _seed_decisions28({"RD5"})
    _sync28.decide(RoadmapDecision)
    rec = RoadmapDecision.objects.get(code="RD5").recommendation
    assert "خلال 48 ساعةً حدّاً أقصى" in rec and "يحلّ محلَّ الخيار (أ) بنصّه الأصليّ" in rec
    assert "سقفُ 40 وسبعةُ أيّامٍ بعد الدمج" in rec and "RK1 يستثني الفرعَ الحيَّ" in rec
    # لا عددَ فروعٍ (المستودعُ عامّ): الرقمُ الوحيدُ سقفُ السياسة 40 وساعاتُ المهلة 48.
    assert set(re.findall(r"\d+", rec)) == {"2026", "09", "25", "48", "40", "1", "08"}


def test_0028_leaves_a_decision_the_owner_already_took_differently():
    RoadmapDecision.objects.create(code="RD7", title="x", status="decided", recommendation="حسمه")
    RoadmapDecision.objects.create(code="D-09", title="x", status="decided", recommendation="حسمه")
    assert _sync28.decide(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="RD7").recommendation == "حسمه"


def test_0028_moves_d07_from_deferred_to_decided_inside_the_own06_decision_without_describing_passwords():
    _seed_decisions28({"D-07"})
    _sync28.decide(RoadmapDecision)
    d07 = RoadmapDecision.objects.get(code="D-07")
    assert (d07.status, d07.decision_date) == ("decided", _sync28.DAY)
    assert "دُمج في قرار OWN-06 (أ)" in d07.recommendation and "المستودع الخاصّ" in d07.recommendation


def test_0028_creates_d25_open_for_the_cpsat_measurement_on_oct_5_and_never_overwrites():
    assert _sync28.add_decisions(RoadmapDecision) == ["D-25"]
    assert _sync28.add_decisions(RoadmapDecision) == []
    d25 = RoadmapDecision.objects.get(code="D-25")
    assert (d25.status, d25.due, d25.blocks, d25.decider) == (
        "open",
        "2026-10-05",
        "SCH-13",
        "المالك",
    )
    assert "SK1 = 0" in d25.options and "SK4 ≤ 15%" in d25.options
    assert d25.sort_order == 139
    RoadmapDecision.objects.filter(code="D-25").update(status="decided")
    assert _sync28.add_decisions(RoadmapDecision) == []
    assert RoadmapDecision.objects.get(code="D-25").status == "decided"


def test_0028_adds_each_item_note_once_without_touching_state_dates_or_gates():
    from datetime import date

    codes = []
    for code, _line in _sync28.ITEM_NOTES:
        if code not in codes:
            codes.append(code)
            _item(
                code,
                "doing",
                40,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 9),
                gate="owner",
            )
    assert _sync28.sync_notes(RoadmapItem) == [code for code, _l in _sync28.ITEM_NOTES]
    assert _sync28.sync_notes(RoadmapItem) == []
    for item in RoadmapItem.objects.all():
        assert (item.status, item.progress, item.gate) == ("doing", 40, "owner"), item.code
        assert (str(item.start_date), str(item.end_date)) == ("2026-10-01", "2026-10-09")
        assert "[2026-09-25]" in item.note


def test_0028_skips_a_note_for_an_absent_item():
    assert _sync28.sync_notes(RoadmapItem) == []
    assert RoadmapItem.objects.count() == 0


def test_0028_clears_only_the_owner_gate_of_the_decided_items():
    for code in _sync28.GATE_CLEARS:
        _item(code, "todo", 0, gate="owner")
    _item("U-01", "todo", 0, gate="owner")  # قرارٌ لم يرفع بوّابتَه (تشغيلٌ بيد المالك)
    _item("X-1", "todo", 0, gate="")
    RoadmapItem.objects.filter(code="M-12").update(gate="release")
    changed = _sync28.clear_gates(RoadmapItem)
    assert changed == [code for code in _sync28.GATE_CLEARS if code != "M-12"]
    assert _sync28.clear_gates(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-12").gate == "release"
    assert RoadmapItem.objects.get(code="U-01").gate == "owner"
    assert RoadmapItem.objects.get(code="VI-19").gate == ""


def test_0028_moves_u01_owns25_and_prp01_by_the_owners_decision():
    from datetime import date

    for code, (status, progress, start, end), *_rest in _sync28.DATES:
        _item(code, status, progress, start_date=start, end_date=end, gate="owner")
    assert _sync28.move_dates(RoadmapItem) == ["U-01", "OWN-25", "PRP-01"]
    assert _sync28.move_dates(RoadmapItem) == []
    u01 = RoadmapItem.objects.get(code="U-01")
    assert (str(u01.start_date), str(u01.end_date)) == ("2026-09-28", "2026-09-28")
    assert "الاثنين 2026-09-28 مساءً بعد الدوام" in u01.note and "كان 2026-09-25" in u01.date_basis
    assert "نسخةٍ احتياطيّةٍ حديثةٍ متحقَّقةٍ" in u01.note
    own25 = RoadmapItem.objects.get(code="OWN-25")
    assert (str(own25.start_date), str(own25.end_date)) == ("2026-09-26", "2026-09-26")
    assert "السبتَ 2026-09-26" in own25.note and "اقتراحٌ لم يؤكّده المالك" in own25.note
    prp01 = RoadmapItem.objects.get(code="PRP-01")
    assert prp01.end_date == date(2027, 5, 15) and "قبل منتصف مايو 2027" in prp01.date_basis
    # الحالةُ والتقدّمُ والبوّابةُ لا تُمسّ.
    assert all(
        (i.status, i.progress, i.gate) == ("todo", 0, "owner") for i in RoadmapItem.objects.all()
    )


def test_0028_leaves_a_date_the_developer_already_moved():
    from datetime import date

    _item("U-01", "todo", 0, start_date=date(2026, 9, 21), end_date=date(2026, 9, 27))
    _item("OWN-25", "doing", 20, start_date=date(2026, 9, 22), end_date=date(2026, 9, 29))
    assert _sync28.move_dates(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="U-01").note == ""
    assert str(RoadmapItem.objects.get(code="U-01").end_date) == "2026-09-27"


def test_0028_defers_m17_and_prp06_and_blocks_dbt34_only_from_their_expected_states():
    for code, (status, progress), *_rest in _sync28.STATUSES:
        _item(code, status, progress)
    assert _sync28.set_statuses(RoadmapItem) == ["M-17", "PRP-06", "DBT-34"]
    assert _sync28.set_statuses(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-17").status == "deferred"
    assert RoadmapItem.objects.get(code="PRP-06").status == "deferred"
    assert RoadmapItem.objects.get(code="DBT-34").status == "blocked"
    assert "مؤجَّلٌ بقرار** لا محجوب" in RoadmapItem.objects.get(code="M-17").note


def test_0028_leaves_a_status_the_developer_moved():
    _item("M-17", "doing", 30)
    _item("DBT-34", "done", 100)
    assert _sync28.set_statuses(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-17").status == "doing"


def test_0028_appends_the_definition_notes_to_rk1_and_rk7_within_the_field_limit():
    _kpi("RK1", 287.0, _sync28.DAY, source="git for-each-ref refs/heads")
    _kpi("RK7", 6.0, _sync28.DAY, source="deployments مقابل deploy_window")
    assert _sync28.kpi_source_notes(RoadmapKpi) == ["RK1", "RK7"]
    assert _sync28.kpi_source_notes(RoadmapKpi) == []
    assert "يستثني الفرعَ الحيَّ والمفتوحَ بطلب" in RoadmapKpi.objects.get(code="RK1").source
    assert "لا يُعدّ مخالفةً" in RoadmapKpi.objects.get(code="RK7").source
    # المؤشّرُ نفسُه لا يُمسّ قيمةً ولا تاريخاً.
    assert RoadmapKpi.objects.get(code="RK7").current == 6.0


def test_0028_skips_a_kpi_whose_source_would_exceed_255_characters():
    _kpi("RK1", 287.0, _sync28.DAY, source="س" * 250)
    assert _sync28.kpi_source_notes(RoadmapKpi) == []
    assert len(RoadmapKpi.objects.get(code="RK1").source) == 250


def test_0028_writes_the_owner05_exception_without_any_reason_and_the_own06_note_without_passwords():
    notes = dict(_sync28.ITEM_NOTES)
    assert "استثناءٌ موثَّقٌ للدورين من استمارة التقييم (لا يداوم شاغلُهما)" in notes["OWN-05"]
    assert "التفصيلُ في المستودع الخاصّ" in notes["OWN-06"]
    for term in ("كلمة", "مرض", "صحّة", "حمل"):
        assert term not in notes["OWN-05"] and term not in notes["OWN-06"], term


def test_0028_forwards_does_nothing_on_an_empty_database_and_is_idempotent():
    _sync28.forwards(_Apps28, None)
    assert RoadmapDecision.objects.count() == 0 and RoadmapItem.objects.count() == 0
    _seed_decisions28()
    _item(
        "U-01",
        "todo",
        0,
        start_date=_sync28.D(2026, 9, 21),
        end_date=_sync28.D(2026, 9, 25),
        gate="owner",
    )
    for code, (status, progress, start, end), *_rest in _sync28.DATES[1:]:
        _item(code, status, progress, start_date=start, end_date=end)
    for code, (status, progress), *_rest in _sync28.STATUSES:
        _item(code, status, progress)
    for code in ("VI-19", "M-12", "REP-08", "U-03", "OWN-05"):
        _item(code, "todo", 0, gate="owner")
    _kpi("RK1", 287.0, _sync28.DAY, source="س")
    _sync28.forwards(_Apps28, None)

    def snapshot():
        return (
            list(
                RoadmapDecision.objects.order_by("code").values_list(
                    "code", "status", "due", "recommendation"
                )
            ),
            list(
                RoadmapItem.objects.order_by("code").values_list(
                    "code", "status", "gate", "note", "start_date"
                )
            ),
            list(RoadmapKpi.objects.values_list("code", "source")),
        )

    first = snapshot()
    _sync28.forwards(_Apps28, None)
    assert snapshot() == first


def test_0028_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0028_owner_decisions_2026_09_25b").origin
    body = open(origin, encoding="utf-8").read()
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "بصمات",
        "الحادثة",
        "قيد التقييم",
        "wave2",
        "archive/",
        "كلمة المرور",
        "كلمة مرور",
        "Temp@",
        "رقمٌ حقيقيّ",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
    assert "تعليق نشر" not in body and "معلَّق النشر" not in body and "نشرُ main معلَّق" not in body


# ── 0029: #599 وVI-11 وVI-31، #602 وM-06، #606، وإعادةُ تعريف OWN-30، وبندا الجوال، وملاحظاتُ مالكي المسارات ──

_sync29 = importlib.import_module("roadmap.migrations.0029_sync_items_2026_09_25h")


class _Apps29:
    @staticmethod
    def get_model(_app, name):
        return RoadmapItem


def test_0029_closes_vi11_vi31_m06_vi23_and_moves_dbt13_only_from_their_expected_states():
    _item("VI-11", "doing", 50, pr="#583")
    _item("VI-31", "todo", 0)
    _item("M-06", "todo", 0)
    _item("VI-23", "todo", 0)
    _item("DBT-13", "blocked", 0)
    assert _sync29.sync(RoadmapItem) == ["VI-11", "VI-31", "M-06", "VI-23", "DBT-13"]
    assert _sync29.sync(RoadmapItem) == []
    by = {i.code: i for i in RoadmapItem.objects.all()}
    assert (by["VI-11"].status, by["VI-11"].progress, by["VI-11"].pr) == ("done", 100, "#583 #599")
    assert (by["VI-31"].status, by["VI-31"].pr) == ("done", "#583 #599")
    assert (by["M-06"].status, by["M-06"].pr) == ("done", "#602")
    assert (by["VI-23"].status, by["VI-23"].progress) == ("done", 100)
    assert (by["DBT-13"].status, by["DBT-13"].progress) == ("doing", 50)


def test_0029_closes_own01_by_the_owners_direct_verification_without_any_session_action():
    _item("OWN-01", "todo", 0, gate="owner")
    assert _sync29.sync(RoadmapItem) == ["OWN-01"]
    assert _sync29.sync(RoadmapItem) == []
    own01 = RoadmapItem.objects.get(code="OWN-01")
    assert (own01.status, own01.progress, own01.gate) == ("done", 100, "")
    assert "بتحقّق المالك المباشر" in own01.note and "غيرُ موجودٍ على الخدمات الثلاث" in own01.note
    assert "لم يُنفَّذ إجراءٌ من الجلسات" in own01.note


def test_0029_leaves_an_own01_the_developer_moved():
    _item("OWN-01", "doing", 40, gate="owner")
    assert _sync29.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="OWN-01").gate == "owner"


def test_0029_records_the_vi11_measurements_with_their_reservations_and_scope():
    _item("VI-11", "doing", 50, pr="#583")
    _sync29.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="VI-11").note
    assert "منشوران على الإنتاج ضمن main@ff70a32" in note and "V-K19 من 4 إلى 0" in note
    assert "−46,339 بايتاً" in note and "لم يُقَس على الإنتاج قبل النشر" in note
    assert "لم يُقَس:" in note and "VD3/VD4" in note and "خارجَ معيار الإغلاق" in note


def test_0029_records_m06_as_published_with_its_measured_cost_and_unverified_device_parts():
    _item("M-06", "todo", 0)
    _sync29.sync(RoadmapItem)
    note = RoadmapItem.objects.get(code="M-06").note
    assert "منشورٌ على الإنتاج ضمن main@ff70a32" in note and "44×44" in note and "32×32" in note
    assert "375: 150 ← 84px" in note and "M-05c" in note and "صافي CSS −21 بايتاً" in note
    assert "لم يُتحقَّق:" in note and "MK10 = نعم" in note


def test_0029_marks_vi23_as_a_local_measurement_and_dbt13_progress_as_the_owners_suggestion():
    _item("VI-23", "todo", 0)
    _item("DBT-13", "blocked", 0)
    _sync29.sync(RoadmapItem)
    vi23 = RoadmapItem.objects.get(code="VI-23").note
    assert "بياناتٌ محلّيّة لا إنتاج" in vi23 and "تحفّظان" in vi23 and "ولا قياسَ على الإنتاج" in vi23
    dbt13 = RoadmapItem.objects.get(code="DBT-13").note
    assert "2,466" in dbt13 and "معيارٌ من اثنين مقيس" in dbt13 and "اقتراحٌ لا قياس" in dbt13


def test_0029_leaves_items_the_developer_moved():
    _item("VI-11", "done", 100)
    _item("M-06", "doing", 60)
    _item("DBT-13", "doing", 20)
    assert _sync29.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="VI-11").note == ""


def test_0029_never_overflows_the_pr_field_limit():
    crowded = " ".join(f"#{n}" for n in range(500, 513))
    _item("VI-11", "doing", 50, pr=crowded)
    assert _sync29.sync(RoadmapItem) == ["VI-11"]
    assert RoadmapItem.objects.get(code="VI-11").pr == crowded


def test_0029_redefines_own30_by_the_owners_decision_and_assigns_it_for_oct_2():
    from datetime import date

    _item(
        "OWN-30",
        "todo",
        0,
        title="سقّاطةُ mypy تفشل على main نفسها الآن، بمعزلٍ عن أيّ فرعٍ من فروعي",
        criterion="تحديدٌ من لمس كلّ ملفٍّ",
        gate="owner",
    )
    assert _sync29.redefine(RoadmapItem) == ["OWN-30"]
    assert _sync29.redefine(RoadmapItem) == []
    own30 = RoadmapItem.objects.get(code="OWN-30")
    assert own30.title.startswith("توحيدُ إصدار mypy بين التطوير وCI")
    assert "mypy==1.10.0" in own30.criterion and "dependabot.yml" in own30.criterion
    assert "1,735 كـCI" in own30.criterion and "لا `--update` بغير إصدار CI" in own30.criterion
    assert (own30.start_date, own30.end_date) == (date(2026, 10, 2), date(2026, 10, 2))
    assert own30.gate == "" and "قرارُ المالك 2026-09-25" in own30.date_basis
    assert (own30.status, own30.progress) == ("todo", 0)


def test_0029_leaves_an_own30_the_developer_rewrote_or_moved():
    _item("OWN-30", "todo", 0, title="عنوانٌ حرّره المطوّر", gate="owner")
    assert _sync29.redefine(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="OWN-30").title == "عنوانٌ حرّره المطوّر"
    RoadmapItem.objects.filter(code="OWN-30").update(
        title="سقّاطةُ mypy تفشل على main نفسها", status="doing", progress=30
    )
    assert _sync29.redefine(RoadmapItem) == []


def test_0029_creates_the_two_approved_mobile_items_open_and_undated_and_never_overwrites():
    assert _sync29.add_new_items(RoadmapItem) == ["M-05c", "M-19"]
    assert _sync29.add_new_items(RoadmapItem) == []
    m05c = RoadmapItem.objects.get(code="M-05c")
    m19 = RoadmapItem.objects.get(code="M-19")
    # M-05c مقترَحٌ مفتوحٌ لا يبدأ قبل القرار، وM-19 حسمه المالكُ فقيدُ التنفيذ (مؤجَّلُ التشغيل للذاكرة).
    assert (m05c.status, m05c.progress) == ("todo", 0)
    assert (m19.status, m19.progress) == ("doing", 0)
    for item in (m05c, m19):
        assert (item.lane, item.src) == ("mobile", "M")
        assert item.start_date is None and item.end_date is None
    assert (m05c.sort_order, m19.sort_order) == (726, 727)
    assert "سجّله المالكُ بنداً مقترَحاً مفتوحاً" in m05c.note
    assert m05c.deps == "M-06" and "60px عند 320px" in m05c.criterion
    assert "عددُ الصفحات ذات العيب المسجَّل" in m19.criterion
    assert "حسمه المالكُ لجلسة الخارطة مباشرةً" in m19.note and "مؤجَّلُ التشغيل للذاكرة" in m19.note
    assert "Chromium وحدَه" in m19.note and "WebKit يحتاج إذنَ المالك" in m19.note
    assert "C:/" not in m19.note
    RoadmapItem.objects.filter(code="M-19").update(status="doing", title="حرّره المطوّر")
    assert _sync29.add_new_items(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="M-19").title == "حرّره المطوّر"


def test_0029_adds_each_note_once_without_touching_state_dates_or_gates():
    from datetime import date

    codes = []
    for code, _line in _sync29.NOTES:
        if code not in codes:
            codes.append(code)
            _item(
                code,
                "doing",
                40,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 9),
                gate="owner",
            )
    assert _sync29.sync_notes(RoadmapItem) == [code for code, _l in _sync29.NOTES]
    assert _sync29.sync_notes(RoadmapItem) == []
    for item in RoadmapItem.objects.all():
        assert (item.status, item.progress, item.gate) == ("doing", 40, "owner"), item.code
        assert (str(item.start_date), str(item.end_date)) == ("2026-10-01", "2026-10-09")


def test_0029_states_that_vi24_and_own20_and_dbt46_proposals_are_not_the_owners_decisions():
    notes = dict(_sync29.NOTES)
    assert "لم يقرّها المالك" in notes["VI-24"]
    # OWN-20 مُغلَقٌ أصلاً (0010) وقرأه 8096 مُغلَقاً على الإنتاج؛ والأدلّةُ المحلّيّةُ لا تُوسَم مطابقةً للإنتاج.
    assert "والبندُ مُغلَقٌ أصلاً" in notes["OWN-20"] and "فلم يتحقّق منها أحدٌ" in notes["OWN-20"]
    assert "محلّيّاً لا على الإنتاج" in notes["OWN-20"]
    assert "لم يُعتمد ترتيبُه" in notes["DBT-46"]
    assert "معيارُ قبولٍ مقترَح" in notes["REP-18"] and "لم يُعتمد" in notes["REP-18"]
    # قياساتُ مسار الديون والتشغيل تُسجَّل بمصدرها وتاريخها.
    assert "1,735 في 160 ملفّاً" in notes["DBT-01"] and "5,728" in notes["DBT-03"]
    assert "29 موقعاً" in notes["DBT-04"] and "سبعَ" in notes["REP-18"]
    # مراقبُ Sentry Uptime فعّالٌ على الإنتاج وقد كشف سقوطاً فعليّاً (8203، ثلاثةُ تصحيحات): DONE-07 بلا تصحيح، ووصولُ بريده للمالك لم يتأكّد.
    assert "الشقُّ الخارجيّ قائم" in notes["DONE-07"] and "فلا تصحيحَ" in notes["DONE-07"]
    assert (
        "كشف سقوطاً فعليّاً يوم 2026-09-17" in notes["DONE-07"] and "لا يصمد" not in notes["DONE-07"]
    )
    assert (
        "ووصولُه إلى المالك لم يتأكّد بعد" in notes["DONE-07"]
        and "لم يُختبر قطّ" not in notes["DONE-07"]
    )
    assert "معطَّلٌ بلا أيّ check-in" in notes["U-07"]
    assert "غيرُ ممكنٍ الآن" in notes["REP-17"] and "قرارُ المالك:" in notes["REP-17"]
    assert "لا «تمديد Uptime»" in notes["REP-17"] and "مقعدُ Cron" in notes["REP-17"]
    assert "ولا يُعدَّل RK8" in notes["REP-17"] and "التي لم تُختبر" not in notes["REP-17"]
    assert "وصولُ بريد الإنذار إلى المالك لم يتأكّد بعد" in notes["REP-17"]


def test_0029_skips_a_note_for_an_absent_item_and_forwards_is_idempotent_on_an_empty_database():
    assert _sync29.sync_notes(RoadmapItem) == []
    _sync29.forwards(_Apps29, None)
    assert RoadmapItem.objects.count() == 0
    _item("VI-11", "doing", 50, pr="#583")
    _item("VI-31", "todo", 0)
    _item("DBT-13", "blocked", 0)
    _item("U-31", "todo", 0)
    _item("OWN-01", "todo", 0, gate="owner")
    _item("OWN-30", "todo", 0, title="سقّاطةُ mypy تفشل على main نفسها", gate="owner")
    _sync29.forwards(_Apps29, None)

    def snapshot():
        return list(
            RoadmapItem.objects.order_by("code").values_list(
                "code", "status", "progress", "pr", "gate", "title", "note", "sort_order"
            )
        )

    first = snapshot()
    _sync29.forwards(_Apps29, None)
    assert snapshot() == first
    assert RoadmapItem.objects.filter(code__in=["M-05c", "M-19"]).count() == 2


def test_0029_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0029_sync_items_2026_09_25h").origin
    body = open(origin, encoding="utf-8").read()
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "بصمات",
        "الحادثة",
        "قيد التقييم",
        "wave2",
        "archive/",
        "كلمة المرور",
        "كلمة مرور",
        "Temp@",
        "رقمٌ حقيقيّ",
        "مرض",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
    assert "تعليق نشر" not in body and "معلَّق النشر" not in body and "نشرُ main معلَّق" not in body


# ── 0030: ما نُشر على main@5877f35 (#616 #619 #622 #604 #620) وقراراتُ المالك المؤكَّدة بعد 0029 ──

_sync30 = importlib.import_module("roadmap.migrations.0030_sync_items_2026_09_25i")


class _Apps30:
    @staticmethod
    def get_model(_app, name):
        return RoadmapItem


def test_0030_closes_the_four_published_items_only_from_their_expected_states():
    _item("M-02", "todo", 0)
    _item("VI-35", "todo", 0)
    _item("DBT-24", "todo", 0)
    _item("REP-07", "doing", 60)
    assert _sync30.sync(RoadmapItem) == ["M-02", "VI-35", "DBT-24", "REP-07"]
    assert _sync30.sync(RoadmapItem) == []
    by = {i.code: (i.status, i.progress, i.pr) for i in RoadmapItem.objects.all()}
    assert by == {
        "M-02": ("done", 100, "#616"),
        "VI-35": ("done", 100, "#619"),
        "DBT-24": ("done", 100, "#622"),
        "REP-07": ("done", 100, "#604"),
    }


def test_0030_records_what_was_measured_and_what_was_not():
    for code, status, progress in (
        ("M-02", "todo", 0),
        ("VI-35", "todo", 0),
        ("DBT-24", "todo", 0),
        ("REP-07", "doing", 60),
    ):
        _item(code, status, progress)
    _sync30.sync(RoadmapItem)
    notes = {i.code: i.note for i in RoadmapItem.objects.all()}
    assert "منشور (#616" in notes["M-02"] and "6 من 6 إلى 0 من 6" in notes["M-02"]
    assert (
        "تحفّظان" in notes["M-02"] and "MK1" in notes["M-02"] and "جهاز لمسٍ حقيقيّ" in notes["M-02"]
    )
    assert "تسعةُ أرقامٍ متقادمة لا ستّة" in notes["VI-35"] and "لقطةٌ مؤرَّخةٌ عمداً" in notes["VI-35"]
    assert "breach_assigned" in notes["DBT-24"] and "بلا هجرةٍ ولا متغيّرِ بيئة" in notes["DBT-24"]
    assert "14 اختباراً" in notes["DBT-24"] and "على حدّ الحجم" in notes["DBT-24"]
    assert "RK5 يُسجَّل مؤشّراً في الهجرة التالية" in notes["REP-07"] and "REP-07b" in notes["REP-07"]
    assert "خارجَ معيار هذا البند" in notes["REP-07"]


def test_0030_leaves_items_the_developer_moved():
    _item("M-02", "doing", 40)
    _item("VI-35", "done", 100)
    _item("DBT-24", "doing", 20)
    _item("REP-07", "doing", 80)
    assert _sync30.sync(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="REP-07").progress == 80


def test_0030_never_overflows_the_pr_field_limit():
    crowded = " ".join(f"#{n}" for n in range(500, 513))
    _item("M-02", "todo", 0, pr=crowded)
    assert _sync30.sync(RoadmapItem) == ["M-02"]
    assert RoadmapItem.objects.get(code="M-02").pr == crowded


def test_0030_creates_the_four_new_items_once_and_never_overwrites():
    from datetime import date

    assert _sync30.add_new_items(RoadmapItem) == ["N-042", "N-043", "PRP-02a", "PRP-04a"]
    assert _sync30.add_new_items(RoadmapItem) == []
    by = {i.code: i for i in RoadmapItem.objects.all()}
    n42, n43, p02a, p04a = by["N-042"], by["N-043"], by["PRP-02a"], by["PRP-04a"]
    assert (n42.lane, n42.status, n42.progress, n42.src) == ("ops", "doing", 0, "NEW")
    assert (n42.start_date, n42.end_date) == (date(2026, 9, 25), date(2026, 9, 26))
    assert "قبل الأحد 09-27 07:00 الدوحة" in n42.date_basis and n42.effort == 0.5
    assert "collectstatic" in n42.note and "قرارُ المالك (2026-09-25، مباشرةً)" in n42.note
    assert "المنفِّذ: مقعدُ المنصّة" in n42.note and "لا وسمَ «نشر-عاجل»" in n42.note
    assert "staticfiles.json" in n42.criterion and "تتحقّق جلسةُ النشر" in n42.criterion
    assert (n43.lane, n43.status, n43.progress, n43.pr) == ("backend", "doing", 33, "#620")
    assert n43.start_date is None and n43.end_date is None
    assert "التقدّم 33% = جزءٌ من ثلاثة منشور — اشتقاقٌ لا قياس" in n43.note
    assert "ولا يُوسم منجَزاً كلّياً" in n43.note and "لم يُمنح أحدٌ شيئاً بعد" in n43.criterion
    assert (p02a.lane, p02a.status, p02a.gate, p02a.deps) == ("product", "todo", "owner", "PRP-02")
    assert "بلا اسمٍ ولا رقم رخصة" in p02a.title and "check_license_expiry" in p02a.note
    assert (p04a.lane, p04a.status, p04a.gate) == ("product", "todo", "")
    assert "تحذيراتٌ ظاهرةٌ لا منع" in p04a.title and "لا يُمنع حفظُ زيارةٍ وقعت فعلاً" in p04a.criterion
    assert [i.sort_order for i in (n42, n43, p02a, p04a)] == [731, 732, 733, 734]
    for item in (n42, n43, p02a, p04a):
        assert len(item.date_basis) <= 120 and item.note.startswith("[2026-09-25]")


def test_0030_does_not_overwrite_an_existing_new_item():
    _item("N-042", "done", 100, title="أنشأه المطوّر يدوياً")
    assert _sync30.add_new_items(RoadmapItem) == ["N-043", "PRP-02a", "PRP-04a"]
    assert RoadmapItem.objects.get(code="N-042").title == "أنشأه المطوّر يدوياً"


def test_0030_restates_prp03_and_vi53_by_the_owners_decision():
    _item(
        "PRP-03",
        "todo",
        0,
        title="مقترح: لوحة نواقص بيانات التقييم (بلا تاريخ مباشرة)",
        effort=2.0,
        gate="owner",
    )
    _item(
        "VI-53",
        "todo",
        0,
        title="اسمُ المنتج بصيغةٍ واحدة (12+ صيغةً اليوم) والمانيفستان متّسقان",
        effort=2.0,
    )
    assert _sync30.restate(RoadmapItem) == ["PRP-03", "VI-53"]
    assert _sync30.restate(RoadmapItem) == []
    prp03 = RoadmapItem.objects.get(code="PRP-03")
    assert prp03.title.startswith("مقترح: حقلُ تاريخ المباشرة وإدخالُه") and prp03.effort == 1.0
    assert "**بلا أثرٍ آليّ**" in prp03.criterion and "nullable" in prp03.criterion
    assert "بعد وصول ردّ النائب الأكاديميّ" in prp03.note and "أربعةُ استعمالات" in prp03.note
    assert "ولا يُنسخ تاريخُ أيّ شخصٍ إلى المستودع" in prp03.criterion
    vi53 = RoadmapItem.objects.get(code="VI-53")
    assert "نحو خمسِ صيغٍ مرئيّةٍ اليوم لا 12+" in vi53.title and vi53.effort == 2.0
    assert (
        "المانيفستُ العامّ يبقى باسم المدرسة" in vi53.criterion
        and "بلا تعليقات الشيفرة" in vi53.criterion
    )
    assert "school.name" in vi53.note and "يُضيّق نطاقَ VD6 دون تغيير حسمه" in vi53.note
    assert "لا رفعَ لـCACHE_NAME" in vi53.note and "(≈10-09)" in vi53.note


def test_0030_leaves_a_restatement_the_developer_rewrote_or_moved():
    _item("PRP-03", "todo", 0, title="عنوانٌ حرّره المطوّر")
    _item("VI-53", "doing", 30, title="اسمُ المنتج بصيغةٍ واحدة (12+ صيغةً اليوم)")
    assert _sync30.restate(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="PRP-03").title == "عنوانٌ حرّره المطوّر"


def test_0030_adds_the_fifth_source_to_own04_only_while_its_criterion_is_untouched():
    old = "المصادر الأربعة في مجلّد الوثائق الوزاريّة"
    _item("OWN-04", "todo", 0, criterion=old)
    assert _sync30.amend_criteria(RoadmapItem) == ["OWN-04"]
    assert _sync30.amend_criteria(RoadmapItem) == []
    own04 = RoadmapItem.objects.get(code="OWN-04")
    assert "أصلُ استمارة الزيارة الصفّيّة" in own04.criterion and "مصدرٌ خامس" in own04.note
    RoadmapItem.objects.filter(code="OWN-04").delete()
    _item("OWN-04", "todo", 0, criterion="صيغةٌ حرّرها المطوّر")
    assert _sync30.amend_criteria(RoadmapItem) == []


def test_0030_moves_the_owner_decided_dates_and_records_why():
    from datetime import date

    _item("LAY-07", "todo", 0, start_date=date(2026, 12, 1), end_date=date(2026, 12, 17))
    _item("Q-05", "todo", 0, start_date=date(2026, 10, 14), end_date=date(2026, 10, 20))
    _item("VI-24", "todo", 0, start_date=date(2026, 11, 2), end_date=date(2026, 12, 17))
    _item("VI-53", "todo", 0, start_date=date(2026, 12, 6), end_date=date(2026, 12, 9))
    _item("PRP-01", "todo", 0, start_date=date(2027, 5, 15), end_date=date(2027, 5, 15))
    assert _sync30.move_dates(RoadmapItem) == ["LAY-07", "Q-05", "VI-24", "VI-53", "PRP-01"]
    assert _sync30.move_dates(RoadmapItem) == []
    by = {i.code: i for i in RoadmapItem.objects.all()}
    assert (by["LAY-07"].start_date, by["LAY-07"].end_date) == (
        date(2026, 11, 8),
        date(2027, 1, 21),
    )
    assert (by["Q-05"].start_date, by["Q-05"].end_date) == (date(2026, 11, 8), date(2026, 11, 19))
    assert (by["VI-24"].start_date, by["VI-24"].end_date) == (date(2026, 12, 7), date(2026, 12, 17))
    assert (by["VI-53"].start_date, by["VI-53"].end_date) == (date(2026, 10, 8), date(2026, 10, 9))
    assert (by["PRP-01"].start_date, by["PRP-01"].end_date) == (
        date(2027, 4, 15),
        date(2027, 5, 15),
    )
    assert "حملةٌ واحدةٌ بجولتين" in by["LAY-07"].note and "الميسِّرُ: المالكُ بنفسه" in by["LAY-07"].note
    assert "11-08..11-19" in by["Q-05"].note and "بوّابةَ Q-ب" in by["Q-05"].note
    assert "النهايةُ (12-17) لم تُعدَّل" in by["VI-24"].note and "بعد LAY-05" in by["VI-24"].note
    assert "اشتقاقٌ من اقتراح 8209" in by["VI-53"].note and "بدايتُه 2027-04-15" in by["PRP-01"].note
    for item in by.values():
        assert len(item.date_basis) <= 120


def test_0030_leaves_a_date_the_developer_moved():
    from datetime import date

    _item("LAY-07", "todo", 0, start_date=date(2026, 12, 3), end_date=date(2026, 12, 20))
    _item("VI-24", "doing", 10, start_date=date(2026, 11, 2), end_date=date(2026, 12, 17))
    assert _sync30.move_dates(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="LAY-07").end_date == date(2026, 12, 20)


def test_0030_blocks_prp04_and_prp05_by_owner_decision_and_links_them_to_own04():
    _item("PRP-04", "todo", 0)
    _item("PRP-05", "todo", 0)
    assert _sync30.set_statuses(RoadmapItem) == ["PRP-04", "PRP-05"]
    assert _sync30.set_statuses(RoadmapItem) == []
    assert _sync30.set_deps(RoadmapItem) == ["PRP-04", "PRP-05"]
    assert _sync30.set_deps(RoadmapItem) == []
    by = {i.code: i for i in RoadmapItem.objects.all()}
    assert (by["PRP-04"].status, by["PRP-04"].deps) == ("blocked", "OWN-04")
    assert (by["PRP-05"].status, by["PRP-05"].deps) == ("blocked", "OWN-04")
    assert "قُسِّم البند" in by["PRP-04"].note and "PRP-04ب" in by["PRP-04"].note
    assert "لا منجزاً" in by["PRP-05"].note and "نموذج 51" in by["PRP-05"].note
    assert "فلا يُبنى قبل النموذج" in by["PRP-05"].note


def test_0030_leaves_prp_items_the_developer_moved_or_linked_elsewhere():
    _item("PRP-04", "doing", 20, deps="X-1")
    _item("PRP-05", "todo", 0, deps="U-38")
    assert _sync30.set_statuses(RoadmapItem) == ["PRP-05"]
    assert _sync30.set_deps(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="PRP-04").status == "doing"
    assert RoadmapItem.objects.get(code="PRP-05").deps == "U-38"


def test_0030_lifts_the_owner_gate_only_where_it_is_the_owner_gate():
    _item("PRP-01", "todo", 0, gate="owner")
    _item("PRP-03", "todo", 0, gate="owner")
    _item("PRP-06", "deferred", 0, gate="owner")
    _item("VI-53", "todo", 0, gate="other")
    assert _sync30.clear_gates(RoadmapItem) == ["PRP-01", "PRP-03", "PRP-06"]
    assert RoadmapItem.objects.get(code="VI-53").gate == "other"
    assert _sync30.clear_gates(RoadmapItem) == []


def test_0030_corrects_the_stale_vi24_statement_and_adds_the_prp02_correction_once():
    _item("VI-24", "todo", 0, note="توصيةُ مسار سطح المكتب — **لم يقرّها المالك**: يبدأ بعد LAY-05")
    assert _sync30.correct(RoadmapItem) == ["VI-24"]
    assert _sync30.correct(RoadmapItem) == []
    note = RoadmapItem.objects.get(code="VI-24").note
    assert "لم يقرّها المالك" not in note and "أقرّها المالكُ (2026-09-25، مباشرةً" in note
    _item("PRP-02", "todo", 0, note="غير عاجل: مهلة الحرمان الفعليّة 2029–2030")
    _item("REP-11", "todo", 0)
    assert _sync30.sync_notes(RoadmapItem) == ["PRP-02", "REP-11"]
    assert _sync30.sync_notes(RoadmapItem) == []
    prp02 = RoadmapItem.objects.get(code="PRP-02").note
    assert "تخصّ من **لم يحصل** على الرخصة" in prp02 and "«ضعيف» نافذٌ بنصّ المادة 19" in prp02
    assert "غيرُ مجدولةٍ في shschool/celery.py" in prp02 and "PRP-02a" in prp02
    assert "لم يُعتمد" in RoadmapItem.objects.get(code="REP-11").note


def test_0030_skips_an_absent_item_and_forwards_is_idempotent_on_an_empty_database():
    assert _sync30.sync_notes(RoadmapItem) == []
    _sync30.forwards(_Apps30, None)
    assert RoadmapItem.objects.count() == 0
    _item("M-02", "todo", 0)
    _item("REP-07", "doing", 60)
    _item("PRP-04", "todo", 0)
    _item("PRP-05", "todo", 0)
    _item("PRP-01", "todo", 0, gate="owner")
    _sync30.forwards(_Apps30, None)

    def snapshot():
        return list(
            RoadmapItem.objects.order_by("code").values_list(
                "code", "status", "progress", "pr", "gate", "deps", "title", "note", "sort_order"
            )
        )

    first = snapshot()
    _sync30.forwards(_Apps30, None)
    assert snapshot() == first
    assert (
        RoadmapItem.objects.filter(code__in=["N-042", "N-043", "PRP-02a", "PRP-04a"]).count() == 4
    )


def test_0030_new_item_codes_and_orders_do_not_collide_with_any_earlier_block():
    codes = [row[0] for row in _sync30.NEW_ITEMS]
    orders = [row[-1] for row in _sync30.NEW_ITEMS]
    assert len(set(codes)) == len(codes) and len(set(orders)) == len(orders)
    assert min(orders) > 730


def test_0030_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0030_sync_items_2026_09_25i").origin
    body = open(origin, encoding="utf-8").read()
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "بصمات",
        "بالبصمات",
        "الحادثة",
        "قيد التقييم",
        "wave2",
        "archive/",
        "كلمة المرور",
        "كلمة مرور",
        "Temp@",
        "رقمٌ حقيقيّ",
        "مرض",
        "C:/",
        "localhost",
        "up.railway.app",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
    assert "تعليق نشر" not in body and "معلَّق النشر" not in body and "نشرُ main معلَّق" not in body


# ── 0031: قراءاتُ المؤشّرات (2026-09-25) وDK1..DK5 وتوافرُ الإنتاج وإعادةُ تعريف PK18 وV-K38 ──

_sync31 = importlib.import_module("roadmap.migrations.0031_kpi_readings_2026_09_25")


class _Apps31:
    @staticmethod
    def get_model(_app, name):
        return RoadmapKpi if name == "RoadmapKpi" else RoadmapItem


def _named_kpi(code, name, current, measured_at, **kw):
    return RoadmapKpi.objects.create(
        code=code,
        lane="quality",
        name=name,
        baseline=current,
        current=current,
        measured_at=measured_at,
        **kw,
    )


def test_0031_records_readings_only_from_the_expected_states_and_keeps_the_history():
    from datetime import date

    _kpi(
        "V-K01",
        248203.0,
        date(2026, 9, 21),
        source="لوحة الهويّة K01",
        history=[{"d": "2026-09-21", "v": 248203.0}],
    )
    _kpi("MK3", None, None, source="خطّة الجوال K3")
    assert _sync31.sync_kpis(RoadmapKpi) == ["V-K01", "MK3"]
    assert _sync31.sync_kpis(RoadmapKpi) == []
    vk01 = RoadmapKpi.objects.get(code="V-K01")
    assert (vk01.current, vk01.measured_at) == (259134.0, date(2026, 9, 25))
    assert vk01.history == [{"d": "2026-09-21", "v": 248203.0}, {"d": "2026-09-25", "v": 259134.0}]
    assert "259,134" in vk01.source and "261,568 على ff70a32f" in vk01.source
    mk3 = RoadmapKpi.objects.get(code="MK3")
    assert (mk3.current, mk3.measured_at) == (0.0, date(2026, 9, 25))
    assert mk3.history == [{"d": "2026-09-25", "v": 0.0}] and "أدنى خطٍّ 12px" in mk3.source


def test_0031_replaces_a_stale_not_measured_source_and_clears_the_reason():
    from datetime import date

    _kpi(
        "PK14",
        None,
        date(2026, 9, 21),
        source="D1 — لم يُقَس (يحتاج متصفّحاً)",
        why="يحتاج متصفّحاً",
    )
    assert _sync31.sync_kpis(RoadmapKpi) == ["PK14"]
    pk14 = RoadmapKpi.objects.get(code="PK14")
    assert pk14.current == 66.0 and pk14.why == ""
    assert "لم يُقَس" not in pk14.source and "محلّيّ لا إنتاج" in pk14.source
    assert pk14.source.startswith("D1 — 8207")


def test_0031_keeps_the_source_when_the_reference_would_overflow_255():
    from datetime import date

    long_source = "س" * 250
    _kpi("V-K02", 14.0, date(2026, 9, 21), source=long_source)
    assert _sync31.sync_kpis(RoadmapKpi) == ["V-K02"]
    vk02 = RoadmapKpi.objects.get(code="V-K02")
    assert vk02.current == 17.0 and vk02.source == long_source


def test_0031_leaves_a_kpi_that_was_remeasured():
    from datetime import date

    _kpi("V-K02", 15.0, date(2026, 9, 23))
    assert _sync31.sync_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="V-K02").current == 15.0


def test_0031_mirrors_carry_the_value_of_their_origin():
    values = {row[0]: row[2] for row in _sync31.KPI_UPDATES}
    assert values["V-K01"] == values["MK14"] == 259134.0
    assert round(values["V-K01"] / 1024, 1) == values["PK10"]
    assert values["PK14"] == values["V-D1"] == 66.0
    assert values["PK6"] == values["UK10"] == 1735.0
    assert values["V-C1"] == values["PK11"] and values["PK9"] == values["V-A1"] == 1.0
    assert values["PK8"] == 0.0  # مرآة MK1 (صفرٌ بعد #600)


def test_0031_yes_no_readings_use_one_for_yes_and_zero_for_no():
    values = {row[0]: row[2] for row in _sync31.KPI_UPDATES}
    assert (values["MK6"], values["MK10"], values["MK16"], values["MK21"]) == (0.0, 1.0, 1.0, 1.0)


def test_0031_creates_the_five_debt_kpis_and_the_availability_kpi_once():
    from datetime import date

    assert _sync31.add_kpis(RoadmapKpi) == ["DK1", "DK2", "DK3", "DK4", "DK5", "OPK1"]
    assert _sync31.add_kpis(RoadmapKpi) == []
    by = {k.code: k for k in RoadmapKpi.objects.all()}
    assert [by[c].current for c in ("DK1", "DK2", "DK3", "DK4", "DK5")] == [
        11.0,
        5728.0,
        38.0,
        158.0,
        23.0,
    ]
    assert all(
        by[c].lane == "debt" and by[c].direction == "down"
        for c in ("DK1", "DK2", "DK3", "DK4", "DK5")
    )
    assert (by["DK1"].baseline, by["DK1"].target, by["DK2"].baseline) == (13.0, 0.0, 7082.0)
    assert by["DK3"].target is None and "لا زيادة" in by["DK3"].target_text
    assert by["DK1"].history == [{"d": "2026-09-25", "v": 11.0}] and by["DK1"].measured_at == date(
        2026, 9, 25
    )
    assert "main@ff70a32f" in by["DK5"].source and "8208" in by["DK5"].source
    opk1 = by["OPK1"]
    assert (opk1.lane, opk1.direction, opk1.unit, opk1.current, opk1.target) == (
        "ops",
        "up",
        "pct",
        99.573,
        None,
    )
    assert "لا هدفَ رقميّاً إلّا بقرار المالك" in opk1.target_text and "14:35" in opk1.source
    assert len(opk1.source) <= 255 and all(len(k.source) <= 255 for k in by.values())


def test_0031_does_not_overwrite_an_existing_kpi():
    _kpi("DK1", 3.0, None, source="أنشأه المطوّر")
    assert _sync31.add_kpis(RoadmapKpi) == ["DK2", "DK3", "DK4", "DK5", "OPK1"]
    assert RoadmapKpi.objects.get(code="DK1").current == 3.0


def test_0031_restates_pk18_and_vk38_by_the_owners_definition_and_only_once():
    from datetime import date

    _named_kpi(
        "PK18",
        "الوثائق الأربع للحوكمة الموقّعة",
        0.0,
        date(2026, 9, 21),
        source="الخطة الموحّدة K21",
        history=[{"d": "2026-09-21", "v": 0.0}],
    )
    _named_kpi("V-K38", "صيغُ اسم المنتج وصيغُ «حفظ»", None, None, source="خطّةُ إصلاح الهويّة")
    assert _sync31.restate_kpis(RoadmapKpi) == ["PK18", "V-K38"]
    assert _sync31.restate_kpis(RoadmapKpi) == []
    pk18 = RoadmapKpi.objects.get(code="PK18")
    assert pk18.name.startswith("الوثائقُ الأربع للحوكمة الحيّة") and "90 يوماً" in pk18.name
    assert (pk18.current, pk18.measured_at) == (0.0, date(2026, 9, 25))
    assert pk18.history == [{"d": "2026-09-21", "v": 0.0}, {"d": "2026-09-25", "v": 0.0}]
    assert "تعريفٌ مؤكَّدٌ من المالك 09-25" in pk18.source
    vk38 = RoadmapKpi.objects.get(code="V-K38")
    assert "بلا تعليقات الشيفرة" in vk38.name and vk38.current is None
    assert (
        vk38.baseline_text.startswith("نحو 5 صيغٍ مرئيّة")
        and "لم يُقَس بعدُ بالتعريف الجديد" in vk38.why
    )
    assert "12+ يشمل تعليقاتِ الشيفرة" in vk38.source


def test_0031_leaves_a_kpi_the_developer_renamed():
    _named_kpi("PK18", "اسمٌ حرّره المطوّر", 0.0, None)
    assert _sync31.restate_kpis(RoadmapKpi) == []
    assert RoadmapKpi.objects.get(code="PK18").name == "اسمٌ حرّره المطوّر"


def test_0031_appends_the_item_notes_once_and_skips_an_absent_item():
    _item("DBT-36", "todo", 0)
    assert _sync31.sync_item_notes(RoadmapItem) == ["DBT-36"]
    assert _sync31.sync_item_notes(RoadmapItem) == []
    dbt36 = RoadmapItem.objects.get(code="DBT-36").note
    assert "23,635 بايتاً" in dbt36 and "259,134" in dbt36 and "لم يُحسم تعريفُ" in dbt36
    _item("N-042", "doing", 0)
    assert _sync31.sync_item_notes(RoadmapItem) == ["N-042"]
    n042 = RoadmapItem.objects.get(code="N-042").note
    assert "#621" in n042 and "العَرَضُ" in n042 and "العلّةُ البنيويّة باقية" in n042
    assert "لا بندَ مستقلّ لـ#621" in n042 and "لم يُقَس بعدُ" in n042


def test_0031_corrects_the_n043_grant_statement_and_records_the_measurement():
    _sync30.add_new_items(RoadmapItem)
    assert _sync31.correct_fields(RoadmapItem) == ["N-043"]
    assert _sync31.correct_fields(RoadmapItem) == []
    n43 = RoadmapItem.objects.get(code="N-043")
    assert "لم يُمنح أحدٌ شيئاً بعد" not in n43.criterion
    assert "مُنحت لمعلّمَين بيد المالك مساء 2026-09-25" in n43.criterion
    assert "يبقى منحُ القدرة (خطوةُ المالك" not in n43.note
    assert "تمّ بيد المالك مساء 2026-09-25" in n43.note
    assert "ويبقى الجزءان ب وج" in n43.note
    assert _sync31.sync_item_notes(RoadmapItem) == ["N-042", "N-043"]
    n43.refresh_from_db()
    assert "منحَين فعّالين" in n43.note and "بلا تأثّرٍ بوقف المنسّقين" in n43.note
    assert "فلا يُوسم البندُ منجَزاً كلّياً" in n43.note
    assert (n43.status, n43.progress) == ("doing", 33)


def test_0031_leaves_an_n043_the_developer_rewrote():
    _item("N-043", "doing", 33, criterion="معيارٌ كتبه المطوّر", note="ملاحظةٌ كتبها المطوّر")
    assert _sync31.correct_fields(RoadmapItem) == []
    assert RoadmapItem.objects.get(code="N-043").criterion == "معيارٌ كتبه المطوّر"


def test_0031_forwards_is_a_noop_on_an_empty_database_and_idempotent_after():
    from datetime import date

    _sync31.forwards(_Apps31, None)
    assert RoadmapKpi.objects.count() == 0
    _item("DBT-36", "todo", 0)
    _kpi("V-K01", 248203.0, date(2026, 9, 21), source="لوحة الهويّة K01")
    _named_kpi("PK18", "الوثائق الأربع للحوكمة الموقّعة", 0.0, date(2026, 9, 21))
    _sync31.forwards(_Apps31, None)

    def snapshot():
        return list(
            RoadmapKpi.objects.order_by("code").values_list(
                "code", "name", "current", "measured_at", "source", "why", "history", "sort_order"
            )
        ) + list(RoadmapItem.objects.order_by("code").values_list("code", "note"))

    first = snapshot()
    _sync31.forwards(_Apps31, None)
    assert snapshot() == first
    assert RoadmapKpi.objects.filter(code__in=["DK1", "DK5", "OPK1"]).count() == 3


def test_0031_new_kpi_codes_and_orders_do_not_collide():
    codes = [row[0] for row in _sync31.NEW_KPIS]
    orders = [row[-1] for row in _sync31.NEW_KPIS]
    assert len(set(codes)) == len(codes) and len(set(orders)) == len(orders)
    assert min(orders) > 442 and not any(code.startswith("PK") for code in codes)


def test_0031_publishes_nothing_a_public_repo_must_not_say():
    import re

    origin = importlib.util.find_spec("roadmap.migrations.0031_kpi_readings_2026_09_25").origin
    body = open(origin, encoding="utf-8").read()
    banned = (
        "aaaa",
        ".zip",
        "FERNET",
        "artifact",
        "Security Summary",
        "بصمات",
        "بالبصمات",
        "الحادثة",
        "قيد التقييم",
        "wave2",
        "archive/",
        "كلمة المرور",
        "كلمة مرور",
        "Temp@",
        "رقمٌ حقيقيّ",
        "مرض",
        "C:/",
        "localhost",
        "up.railway.app",
    )
    assert [term for term in banned if term in body] == []
    assert not re.search(r"\b\d{11}\b", body)
    assert not re.search(r"\b[0-9a-f]{40}\b", body)
