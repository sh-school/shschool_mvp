"""[ROADMAP] هجرةُ المزامنة 0002 حارسةٌ: تُحدِّث ما لم يُمسّ وتترك ما عدّله المطوّر."""

import importlib

import pytest

from roadmap.models import RoadmapItem, RoadmapKpi

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
    assert "منسوبٌ إليها لا قرارٌ مسجَّل" in n033.note


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
