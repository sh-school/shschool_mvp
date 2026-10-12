"""أداةُ قياس أثر التفضيلات (W-20261011-008): منطقُها بلا حلّالٍ ولا قاعدة.

القياسُ نفسُه دقائقُ لكلّ سيناريو على نسخة الإسنادات، فلا يُختبر هنا؛ يُختبر ما يقرّر صحّتَه: أيُّ المعلّمين
يُختار، وأيُّ تفضيلٍ تقبله الشاشة، ورفضُ أيّ قاعدةٍ غير قاعدة الجلسة، وعدُّ التلاصق والفراغ من الخانات؛
وفي التقرير: حكمُ السيناريو بترتيبه، والعتبةُ من الأرخى إلى الأشدّ، وألّا تبقى في الصفحة خانةٌ بلا قيمة.
"""

from __future__ import annotations

import pytest

from tools.pref_impact import (
    Recorder,
    Scenario,
    breach_details,
    isolation_problem,
    kept_breaches,
    scope_pool,
    screen_slack,
    select_teachers,
    stress_summary,
    teacher_stress,
)
from tools.pref_impact_report import (
    Baseline,
    render,
    teacher_cell,
    threshold,
    threshold_rows,
    verdict,
)


def test_scenario_parse_and_key():
    assert Scenario.parse("base").key == "base"
    scenario = Scenario.parse("gap:0:30")
    assert (scenario.column, scenario.value, scenario.share) == ("max_gap", 0, 30)
    assert scenario.key == "gap:0:30"


def test_scenario_scope_is_part_of_the_key():
    scenario = Scenario.parse("gap:1:100:single")
    assert (scenario.scope, scenario.key) == ("single", "gap:1:100:single")
    assert Scenario.parse("gap:1:100").scope == ""


def test_scope_pool_splits_by_bell_bands():
    loads = {"a": 12, "b": 16, "c": 20}
    bands = {"a": 1, "b": 2}  # «c» بلا مهامّ معروفة: يُعدّ نطاقاً واحداً
    assert scope_pool(loads, bands, "") == loads
    assert scope_pool(loads, bands, "single") == {"a": 12, "c": 20}
    assert scope_pool(loads, bands, "multi") == {"b": 16}


@pytest.mark.parametrize(
    "spec", ["daily:4", "weekly:4:100", "daily:4:0", "gap:-1:10", "gap:1:100:all"]
)
def test_scenario_parse_rejects_malformed(spec):
    with pytest.raises(ValueError):
        Scenario.parse(spec)


def test_select_teachers_heaviest_first_and_ceiling():
    loads = {f"t{i:02d}": i for i in range(1, 21)} | {"a00": 20}
    picked = select_teachers(loads, 10)
    assert len(picked) == 3  # ⌈21 × 10%⌉
    assert picked == ["a00", "t20", "t19"]  # التعادلُ يُحسم بالمعرّف
    assert select_teachers(loads, 100)[-1] == "t01"
    assert select_teachers(loads, 0) == []


def _values(daily=5, consecutive=None, gap=None):
    return {"max_daily_periods": daily, "max_consecutive": consecutive, "max_gap": gap}


def test_screen_slack_mirrors_teacher_screen():
    # نصابُ 18 على خمسة أيّام يحتاج 4 في بعضها: سقفُ 3 تردّه الشاشة، و4 تقبله بهامش 2.
    assert screen_slack(18, _values(daily=3), None) is None
    assert screen_slack(18, _values(daily=4), None) == 2
    # يومُ تفريغٍ يرفع حصّةَ القسمة: 18 ÷ 4 أيّام = 5.
    assert screen_slack(18, _values(daily=4), 2) is None
    # «لا فراغ» مع السقف العامّ للتتالي (حصّة) = حصّةٌ في اليوم.
    assert screen_slack(18, _values(gap=0), None) is None
    # «فراغٌ واحد» مع السقف العامّ: الأولى فالثالثة فالخامسة فالسابعة = 4 يوميّاً.
    assert screen_slack(18, _values(gap=1), None) == 2


@pytest.mark.parametrize(
    ("name", "host", "module", "refused"),
    [
        ("ss_w008_pref_impact", "host.docker.internal", "shschool.settings.development", False),
        ("shschool_db", "host.docker.internal", "shschool.settings.development", True),
        ("ss_copy", "db.railway.internal", "shschool.settings.development", True),
        ("ss_copy", "localhost", "shschool.settings.production", True),
    ],
)
def test_isolation_guard(name, host, module, refused):
    assert bool(isolation_problem(name, host, module)) is refused


def test_teacher_stress_counts_touch_gaps_and_heaviest_day():
    times = {1: (0, 45), 2: (45, 90), 3: (100, 145), 4: (145, 190), 6: (250, 295)}
    slots = [
        ("c1", "s", "T", 0, 1),
        ("c2", "s", "T", 0, 2),  # يلاصق الأولى (0 دقيقة)
        ("c1", "s", "T", 0, 4),  # بعد فراغ الثالثة
        ("c1", "s", "T", 1, 3),
        ("c2", "s", "T", 1, 6),  # فراغان: الرابعة والخامسة
        ("c1", "s", "U", 0, 3),
    ]
    stress = teacher_stress(slots, lambda _c, _d, p: times[p], 10)
    assert stress["T"] == {"touch": 1, "gaps": 3, "max_day": 3}
    assert stress["U"] == {"touch": 0, "gaps": 0, "max_day": 1}


def test_teacher_stress_counts_split_cell_once():
    times = {1: (0, 45)}
    slots = [("c1", "s1", "T", 0, 1), ("c1", "s2", "T", 0, 1)]
    assert teacher_stress(slots, lambda _c, _d, p: times[p], 10)["T"]["max_day"] == 1


def test_stress_summary_picks_worst_among_preference_holders():
    stress = {
        "aaaaaaaa1": {"touch": 9, "gaps": 0, "max_day": 4},
        "bbbbbbbb2": {"touch": 1, "gaps": 2, "max_day": 4},
    }
    loads = {"aaaaaaaa1": 18, "bbbbbbbb2": 16}
    summary = stress_summary(stress, ["bbbbbbbb2"], loads)
    assert summary["worst"]["teacher"] == "bbbbbbbb"
    assert summary["totals"] == {"touch": 10, "gaps": 2, "max_day": 4}
    assert stress_summary(stress, [], loads)["worst"]["teacher"] == "aaaaaaaa"


def _breach(code, key, day=0, period=0):
    from types import SimpleNamespace

    return SimpleNamespace(code=code, key=key, day=day, period=period)


def test_kept_breaches_mirrors_evaluator_easing():
    strict = [_breach("HC5", ("HC5", ("t1",), 0)), _breach("HC10", ("HC10", ("t2",), 1))]
    relaxed = [_breach("HC10", ("HC10", ("t2",), 1))]  # التخفيفُ رفع HC5 وأبقى HC10
    assert [b.code for b in kept_breaches([strict, relaxed])] == ["HC10"]
    assert kept_breaches([strict]) == strict
    assert kept_breaches([]) == []


def test_breach_details_carry_short_ids_and_day_cells_only():
    teacher = "abcdef0123456789"
    slots = [
        ("cls-a", "s", teacher, 1, 2),
        ("cls-b", "s", teacher, 1, 4),
        ("cls-a", "s", teacher, 2, 1),
    ]
    bands = {"cls-a": "band-one-uuid", "cls-b": "band-two-uuid"}
    (item,) = breach_details([_breach("HC10", ("HC10", (teacher,), 1), day=1)], slots, bands)
    assert item["key"] == [["abcdef01"], 1]
    assert item["cells"] == {"abcdef01": [[2, "band-one"], [4, "band-two"]]}


def test_recorder_tracks_stages_and_ignores_closing_call():
    recorder = Recorder()
    recorder.begin(300.0)
    recorder.on_solution(120.0, 80.0)
    recorder.on_solution(110.0, 80.0)
    recorder.end("FEASIBLE", 300.2)
    recorder.on_solution(110.0, 80.0)  # نداءُ `solve()` الختاميّ
    (stage,) = recorder.stages
    assert stage["solutions"] == 2 and stage["best"] == 110.0
    assert stage["status"] == "FEASIBLE" and stage["first_s"] is not None
    assert recorder.publish() is False


# ───────────────────────── التقرير: الحكمُ والعتبةُ والقالب ─────────────────────────

SECTIONS = {
    key: f"<p>{key}</p>"
    for key in ("head", "date", "summary", "recommendation", "method", "not_measured", "findings")
}


def _row(scenario="base", hc5=90, hc22=4, ok=True, **extra):
    field, value, share = ("", None, 0)
    if scenario != "base":
        field, raw, pct = scenario.split(":")
        value, share = int(raw), int(pct)
    row = {
        "scenario": scenario,
        "field": field,
        "value": value,
        "share": share,
        "ok": ok,
        "reason": "ok" if ok else extra.pop("reason", "failed"),
        "status": "FEASIBLE",
        "eased": {"HC5": hc5, "HC22": hc22},
        "gate": {"blocked": False, "codes": []},
        "applied": 72,
        "selected": 72,
        "wall_s": 600.0,
        "stages": [{"first_s": 80.0}],
        "database": "ss_x",
        "teachers": 72,
        "seconds_cap": 1800.0,
        "quality_cap": 300.0,
        "seed": 1,
        "workers": 8,
        "finished_at": "2026-10-12T14:00:00",
    }
    row.update(extra)
    return row


def test_baseline_band_is_spread_with_floor():
    base = Baseline.of([_row(hc5=85), _row(hc5=96), _row(ok=False)])
    assert (base.hc5, base.band5, base.runs) == (96, 11, 2)
    assert Baseline.of([_row(hc5=90), _row(hc5=91)]).band5 == 5  # ⌈5% × 91⌉ أكبرُ من الفرق
    assert Baseline.of([_row(hc22=4)]).band22 == 1
    with pytest.raises(ValueError):
        Baseline.of([_row("daily:4:100")])


def test_verdict_order_gate_before_solver_before_effect():
    base = Baseline.of([_row(hc5=90)])
    assert verdict(_row("daily:4:100", hc5=95), base) == "ok"  # ضمن النطاق (90 + 5)
    assert verdict(_row("daily:4:100", hc5=96), base) == "hc"
    assert verdict(_row("daily:4:100", hc22=6), base) == "hc"
    blocked = _row("daily:3:100", gate={"blocked": True, "codes": ["AS-4"]}, status="INFEASIBLE")
    assert verdict(blocked, base) == "gate"
    assert (
        verdict(_row("gap:0:100", ok=False, status="INFEASIBLE", reason="infeasible"), base)
        == "infeasible"
    )
    assert (
        verdict(_row("gap:0:100", ok=False, status="UNKNOWN", reason="timeout"), base) == "timeout"
    )
    assert verdict(_row("gap:0:100", error="X"), base) == "error"


def test_threshold_scans_from_loosest_and_reports_shares():
    rows = [
        _row(hc5=90),
        _row("daily:6:100"),
        _row("daily:5:100"),
        _row("daily:4:100", ok=False, status="UNKNOWN", reason="timeout"),
        _row("daily:4:30", ok=False, status="UNKNOWN", reason="timeout"),
        _row("daily:4:10"),
        _row("daily:3:100", ok=False, status="INFEASIBLE", reason="infeasible"),
    ]
    found = threshold(rows, "daily", Baseline.of(rows))
    assert (found["safe"], found["broken"], found["broken_kind"]) == (5, 4, "timeout")
    assert (found["min_breaking_share"], found["max_holding_share"]) == (30, 10)
    assert found["measured"] == [6, 5, 4, 3]
    # سيناريو نطاقٍ لا يغيّر العتبة ولو انكسر عند قيمةٍ أرخى.
    scoped = _row("daily:6:100", ok=False, status="INFEASIBLE", reason="infeasible", scope="multi")
    assert threshold([*rows, scoped], "daily", Baseline.of(rows))["safe"] == 5
    assert threshold(rows, "gap", Baseline.of(rows))["measured"] == []


def test_threshold_does_not_count_unapplied_share_as_holding():
    """سيناريو سليمٌ رفضت الشاشةُ فيه القيمةَ لكلّ المختارين هو الأساسُ نفسُه، لا صمودٌ للقيمة."""
    rows = [
        _row(hc5=90),
        _row("daily:4:100"),
        _row("daily:3:100", ok=False, status="INFEASIBLE", reason="infeasible"),
        _row("daily:3:10", applied=0),
    ]
    found = threshold(rows, "daily", Baseline.of(rows))
    assert (found["min_breaking_share"], found["max_holding_share"]) == (100, None)
    assert found["unapplied_shares"] == [10]
    assert "لم تُطبَّق على أحد" in threshold_rows(rows, Baseline.of(rows))


def test_render_fills_every_marker_and_refuses_missing_section():
    rows = [_row(hc5=90), _row("gap:1:100", hc5=120)]
    page = render(rows, SECTIONS)
    assert "@@" not in page
    assert "gap:1:100" in page and "زيادةٌ في التخفيف" in page
    with pytest.raises(KeyError):
        render(rows, {k: v for k, v in SECTIONS.items() if k != "findings"})


def test_teacher_cell_names_breach_owner_for_rejected_schedule():
    breach = {
        "code": "HC10",
        "day": 4,
        "period": 5,
        "cells": {"abcdef01": [[2, "band-one"], [5, "band-two"]]},
        "loads": {"abcdef01": 12},
    }
    row = _row("gap:0:100", ok=False, reason="rejected", breaches=[breach, breach])
    text = teacher_cell(row, "rejected")
    assert text.startswith("abcdef01 (12 حصّة) يوم الخميس: الحصص 2 (band-one)، 5 (band-two)")
    assert text.endswith("و1 مخالفةً غيرُها")
