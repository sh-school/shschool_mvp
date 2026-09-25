"""[ROADMAP] هجرةُ المزامنة 0002 حارسةٌ: تُحدِّث ما لم يُمسّ وتترك ما عدّله المطوّر."""

import importlib

import pytest

from roadmap.models import RoadmapDecision, RoadmapItem, RoadmapKpi

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
