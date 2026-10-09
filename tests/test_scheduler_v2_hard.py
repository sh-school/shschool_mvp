"""[SCHEDULE-V2] نواةُ CP-SAT الصلبة (V2-S3a، W-20261003-016) — كلُّ قيدٍ باختبارٍ إيجابيٍّ وسلبيّ على مثالٍ صغير.

الأسلوب: يُثبَّت وضعٌ جزئيٌّ بخاناتٍ (`forced`) فيُسأل الحلّالُ: أيُكمَل إلى جدولٍ صالح؟ فالسلبيُّ INFEASIBLE مُبرهَن
(لا مهلةٌ) والإيجابيُّ OPTIMAL/FEASIBLE. ثمّ تشغيلٌ على `fixture_anonymized.json` بزمنٍ مقيس.
"""

import json
import time
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from operations.cpsat_adapter import CpSatInputs, DemandRow, TeacherPref
from operations.scheduler_v2.hard_constraints import (
    AS6_SUCCESS_MESSAGE,
    check_assignment,
    max_independent_slots,
)
from operations.scheduler_v2.model import ModelOptions, add_soft_terms, build_model

FIXTURE = (
    Path(__file__).resolve().parent.parent / "docs" / "schedule_v2" / "fixture_anonymized.json"
)
STARTS = {1: 430, 2: 480, 3: 530, 4: 600, 5: 650, 6: 700, 7: 750}
OK = (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _times(shift=0, last=7):
    return {p: (s + shift, s + 50 + shift) for p, s in STARTS.items() if p <= last}


def _bell(times):
    ps = sorted(times)
    touch = [(p, p + 1) for p in ps if p + 1 in times and times[p + 1][0] == times[p][1]]
    return {"periods": ps, "touch": touch}


def _add_band(inp, band, shift):
    t = _times(shift)
    for kind in ("regular", "thursday"):
        inp.times[f"{band}|{kind}"] = t
        inp.bell[f"{band}|{kind}"] = _bell(t)


def _derive_blocks(inp, doubles):
    """كتلُ الازدواج كما يبنيها `build_tasks`: مادّةٌ منفردةٌ مزدوجةٌ ← n//2 كتلةً؛ ومجموعةٌ متوازيةٌ لا تكون
    مزدوجةً إلّا إن كان كلُّ أعضائها مزدوجين، وإلّا فحصصٌ مفردةٌ (W-20261009-001)."""
    members: dict[tuple, list] = {}
    for r in inp.demand:
        if r.elec:
            members.setdefault((r.cls, r.elec), []).append(r)
    inp.demand = [
        DemandRow(
            r.cls,
            r.subj,
            r.teacher,
            r.elec,
            r.n,
            r.joint,
            r.n // 2
            if (
                all(m.subj in doubles for m in members[(r.cls, r.elec)])
                if r.elec
                else r.subj in doubles
            )
            else 0,
        )
        for r in inp.demand
    ]


def make(rows, *, bands=None, levels=None, **kw):
    """مدخلاتٌ صغيرة. rows: (cls, subj, teacher, elec, n[, joint]). bands: {شعبةٌ: نطاق}."""
    inp = CpSatInputs()
    inp.demand = [DemandRow(*r) for r in rows]
    bands = bands or {}
    for r in inp.demand:
        inp.class_band[r.cls] = bands.get(r.cls, "B")
        inp.class_level[r.cls] = (levels or {}).get(r.cls, "sec")
    for band in set(inp.class_band.values()):
        _add_band(inp, band, {"B": 0, "B2": 25, "B3": 50}.get(band, 0))
    _derive_blocks(inp, kw.get("doubles", frozenset()))
    for k, v in kw.items():
        setattr(inp, k, v)
    return inp


def solve(built, forced=(), workers=1, limit=30.0):
    for cell in forced:
        built.model.Add(built.x[cell] == 1)
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = limit
    sv.parameters.num_search_workers = workers
    sv.parameters.random_seed = 7
    return sv.Solve(built.model), sv


def feasible(inp, forced=(), **opt):
    """HC16 المشتقّ مُطفأٌ هنا افتراضاً كي لا يحجب مثالاً صغيراً بنصابٍ دون يومَين؛ يُفعَّل صراحةً في اختباره."""
    opt.setdefault("derived_day_cap", False)
    built = build_model(inp, ModelOptions(**opt))
    st, _ = solve(built, forced)
    assert st != cp_model.UNKNOWN
    return st in OK


# ───────── النواة ─────────


def test_hc1_teacher_cannot_teach_two_classes_at_once():
    inp = make([("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)])
    assert not feasible(inp, [(0, 0, 3), (1, 0, 3)])
    assert feasible(inp, [(0, 0, 3), (1, 1, 3)])


def test_hc2_class_cannot_take_two_subjects_at_once():
    inp = make([("C1", "S1", "T1", "", 1), ("C1", "S2", "T2", "", 1)])
    assert not feasible(inp, [(0, 0, 3), (1, 0, 3)])
    assert feasible(inp, [(0, 0, 3), (1, 0, 4)])


def test_hc2_optional_group_not_with_plain_nor_other_group():
    inp = make(
        [("C1", "S1", "T1", "G1", 1), ("C1", "S2", "T2", "G2", 1), ("C1", "S3", "T3", "", 1)]
    )
    assert not feasible(
        inp, [(0, 0, 3), (1, 0, 3)]
    )  # مجموعتان مختلفتان: يرفضه المُقيِّم (orphan_cells)
    assert not feasible(inp, [(0, 0, 3), (2, 0, 3)])  # مجموعةٌ مع عامّة


def test_hc9_resource_capacity():
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S1", "T2", "", 1), ("C3", "S1", "T3", "", 1)]
    tight = make(rows, res_cap={"R": 2}, res_subjects={"R": frozenset({"S1"})})
    assert not feasible(tight, [(0, 0, 3), (1, 0, 3), (2, 0, 3)])
    assert feasible(tight, [(0, 0, 3), (1, 0, 3), (2, 0, 4)])


def test_hc9_resource_capacity_is_by_clock_across_bands():
    # ح2 في B (480-530) تتداخل بالساعة مع ح2 في B2 (505-555) لا مع ح4
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S1", "T2", "", 1)]
    inp = make(rows, bands={"C2": "B2"}, res_cap={"R": 1}, res_subjects={"R": frozenset({"S1"})})
    assert not feasible(inp, [(0, 0, 2), (1, 0, 2)])
    assert feasible(inp, [(0, 0, 2), (1, 0, 4)])


def test_hc12_clock_overlap_between_bands_is_forbidden_even_without_hc5():
    inp = make([("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)], bands={"C2": "B2"})
    off = frozenset({"HC5"})
    assert not feasible(inp, [(0, 0, 2), (1, 0, 2)], disabled=off)  # 480-530 مع 505-555
    assert feasible(inp, [(0, 0, 2), (1, 0, 4)], disabled=off)


def test_hc13_touching_across_floors_is_forbidden_when_hc5_off():
    # B3 مُزاحٌ 50 دقيقة: ح1 فيه (480-530) تلامس نهايةَ ح1 في B (480)
    inp = make([("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)], bands={"C2": "B3"})
    off = frozenset({"HC5"})
    forced = [(0, 0, 1), (1, 0, 1)]
    assert feasible(inp, forced, band_floor={"B": 1, "B3": 1}, disabled=off)  # الطابقُ نفسُه
    assert not feasible(inp, forced, band_floor={"B": 1, "B3": 2}, disabled=off)  # طابقان
    assert not feasible(inp, forced)  # HC5 قائم: يمنع التلاصقَ أيضاً


def test_hc19_double_is_adjacent_and_not_across_break():
    inp = make([("C1", "S1", "T1", "", 2)], doubles=frozenset({"S1"}))
    assert feasible(inp, [(0, 0, 1), (0, 0, 2)])
    assert not feasible(inp, [(0, 0, 3), (0, 0, 4)])  # فسحةٌ بين ح3 وح4
    assert not feasible(inp, [(0, 0, 1), (0, 0, 5)])  # غيرُ متلاصقتين


# ───────── القفل الإداريّ ─────────


def test_hc4_thursday_cap_by_level():
    rows = [("CP", "S1", "T1", "", 1), ("CS", "S1", "T2", "", 1)]
    built = build_model(make(rows, levels={"CP": "prep", "CS": "sec"}))
    assert (0, 4, 7) not in built.x and (0, 4, 6) in built.x
    assert (1, 4, 7) in built.x
    assert built.notes["HC4_cut_cells"] >= 1


def test_hc6_even_distribution_across_days():
    inp = make([("C1", "S1", "T1", "", 3)])
    assert not feasible(inp, [(0, 0, 1), (0, 0, 4)])  # سقفُ اليوم ⌈3/5⌉ = 1
    assert feasible(inp, [(0, 0, 1), (0, 1, 1), (0, 2, 3)])
    built = build_model(make([("C1", "S1", "T1", "", 6)]))
    st, sv = solve(built)
    per_day = [
        sum(sv.Value(v) for (_i, d, _p), v in built.x.items() if d == day) for day in range(5)
    ]
    assert st in OK and sorted(per_day) == [1, 1, 1, 1, 2]  # يومٌ بحصّتين وأربعةٌ بواحدة


def test_hc6_divides_by_available_days_not_five():
    inp = make([("C1", "S1", "T1", "", 4)], ex_full=frozenset({("T1", 2)}))
    built = build_model(inp)
    st, sv = solve(built)
    assert st in OK and not any(d == 2 for (_i, d, _p) in built.x)
    per_day = [
        sum(sv.Value(v) for (_i, d, _p), v in built.x.items() if d == day) for day in (0, 1, 3, 4)
    ]
    assert per_day == [1, 1, 1, 1]


def test_hc10_personal_gap_cap():
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)]
    pref0 = {"T1": TeacherPref("T1", None, None, 0, None)}
    pref1 = {"T1": TeacherPref("T1", None, None, 1, None)}
    # ح1 وح3 في يومٍ واحد: فراغٌ بينهما حصّةٌ واحدة (ح2)
    assert not feasible(make(rows, prefs=pref0), [(0, 0, 1), (1, 0, 3)])
    assert feasible(make(rows, prefs=pref1), [(0, 0, 1), (1, 0, 3)])
    assert feasible(make(rows), [(0, 0, 1), (1, 0, 3)])  # بلا تفضيلٍ لا قيد


# ───────── افتراضاتٌ قابلةٌ للإيقاف ─────────


def test_hc5_no_adjacent_periods_unless_declared_double_or_disabled():
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)]
    inp = make(rows)
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2)])
    assert feasible(inp, [(0, 0, 1), (1, 0, 2)], disabled=frozenset({"HC5"}))
    assert feasible(inp, [(0, 0, 1), (1, 0, 3)])  # غيرُ متلاصقتين
    dbl = make([("C1", "S1", "T1", "", 2)], doubles=frozenset({"S1"}))
    assert feasible(dbl, [(0, 0, 1), (0, 0, 2)])  # المزدوجةُ المعلَنة مستثناة


def test_toggle_by_policy_object():
    class Policy:
        def __init__(self, rank):
            self.rank = rank

        def break_at(self, code):
            return self.rank.get(code, "never")

    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)]
    inp = make(rows)
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2)], policy=Policy({}))
    assert feasible(inp, [(0, 0, 1), (1, 0, 2)], policy=Policy({"HC5": "relaxed"}))


def test_hc8_last_period_cap_and_not_same_class():
    rows = [("C1", "S1", "T1", "", 3), ("C2", "S2", "T1", "", 3)]
    three = [(0, 0, 7), (0, 1, 7), (1, 2, 7)]
    assert not feasible(make(rows), three)  # ثلاثُ أخيراتٍ > 2
    assert feasible(make(rows), three, disabled=frozenset({"HC8"}))
    assert feasible(make(rows), [(0, 0, 7), (1, 1, 7)])
    same_class = [(0, 0, 7), (0, 1, 7)]  # طرفان على شعبةٍ واحدة
    assert not feasible(make(rows), same_class)


def test_hc22_first_period_cap():
    rows = [("C1", "S1", "T1", "", 3), ("C2", "S2", "T1", "", 3)]
    three = [(0, 0, 1), (0, 1, 1), (1, 2, 1)]
    assert not feasible(make(rows), three)
    assert feasible(make(rows), three, disabled=frozenset({"HC22"}))
    assert feasible(make(rows), [(0, 0, 1), (1, 1, 1)])


def test_hc11_resource_does_not_mix_levels():
    rows = [("CP", "S1", "T1", "", 1), ("CS", "S1", "T2", "", 1)]
    inp = make(
        rows,
        levels={"CP": "prep", "CS": "sec"},
        res_cap={"R": 2},
        res_subjects={"R": frozenset({"S1"})},
    )
    assert not feasible(inp, [(0, 0, 3), (1, 0, 3)])
    assert feasible(inp, [(0, 0, 3), (1, 0, 4)])
    assert feasible(inp, [(0, 0, 3), (1, 0, 3)], disabled=frozenset({"HC11"}))


# ───────── الحمولة والتفريغ ─────────


def test_hc7_subject_not_piled_on_one_period():
    inp = make([("C1", "S1", "T1", "", 3)])
    assert not feasible(inp, [(0, 0, 5), (0, 1, 5), (0, 2, 5)])
    assert feasible(inp, [(0, 0, 5), (0, 1, 5), (0, 2, 4)])


def test_daily_load_cap_from_hc16_and_personal_preference():
    rows = [("C1", "S1", "T1", "", 5), ("C2", "S2", "T1", "", 5)]  # نصابُ 10 على 5 أيّام ⇒ ≤ 2 يوميّاً
    three_a_day = [(0, 0, 1), (1, 0, 3), (0, 1, 3), (1, 0, 5)]  # ثلاثٌ يومَ الأحد
    assert not feasible(make(rows), three_a_day, derived_day_cap=True)
    two_a_day = [(0, 0, 1), (1, 0, 3), (0, 1, 3), (1, 1, 5)]
    assert feasible(make(rows), two_a_day, derived_day_cap=True)
    pref = make(rows, prefs={"T1": TeacherPref("T1", 1, None, None, None)})
    assert not feasible(pref, two_a_day)  # سقفٌ شخصيٌّ 1


def test_exemptions_remove_cells():
    inp = make(
        [("C1", "S1", "T1", "", 2)],
        ex_full=frozenset({("T1", 1)}),
        ex_period=frozenset({("T1", 0, 3)}),
    )
    built = build_model(inp)
    assert not any(d == 1 for (_i, d, _p) in built.x)
    assert (0, 0, 3) not in built.x and (0, 0, 2) in built.x
    assert built.notes["exempt_cut_cells"] >= 8


def test_joint_task_members_share_slots():
    rows = [("C1", "S1", "T1", "", 2, "J"), ("C1", "S2", "T2", "", 2, "J")]
    built = build_model(make(rows))
    st, sv = solve(built)
    assert st in OK
    for (i, d, p), v in built.x.items():
        if i == 0:
            assert sv.Value(v) == sv.Value(built.x[1, d, p])


def test_overdemand_is_proven_infeasible_not_timeout():
    inp = make([("C1", "S1", "T1", "", 1)], ex_full=frozenset(("T1", d) for d in range(5)))
    st, _ = solve(build_model(inp))
    assert st == cp_model.INFEASIBLE


# ───────── القيودُ الباقية: HC14 HC16B HC17 HC20 والسقفان المرنان ─────────


def test_hc14_no_empty_day_for_full_load_teacher():
    inp = make([("C1", "S1", "T1", "", 5)], ex_full=frozenset({("T1", 2)}))  # 5 حصصٍ على 4 أيّام
    built = build_model(
        inp, ModelOptions(derived_day_cap=False, even_spread=False, disabled=frozenset({"HC16B"}))
    )
    st, sv = solve(built)
    assert st in OK
    for day in (0, 1, 3, 4):
        assert sum(sv.Value(v) for (_i, d, _p), v in built.x.items() if d == day) >= 1
    # معلّمٌ نصابُه دون أيّامه (منسّق): اليومُ الفارغ مباحٌ
    few = make([("C1", "S1", "T1", "", 3)])
    assert feasible(few, [(0, 0, 1), (0, 1, 1), (0, 2, 3)])


def test_hc14_can_be_disabled_by_tag():
    rows = [("C1", "S1", "T1", "", 3), ("C2", "S2", "T1", "", 3)]  # 6 ≥ 5 أيّام
    # الأيّام 0..2 بحصّتين والخميسُ والأربعاءُ فارغان
    forced = [(0, 0, 1), (1, 0, 3), (0, 1, 3), (1, 1, 5), (0, 2, 5), (1, 2, 1)]
    assert not feasible(make(rows), forced)
    assert feasible(make(rows), forced, disabled=frozenset({"HC14", "HC16B"}))


def test_hc16b_day_floor_is_floor_of_load_over_days():
    rows = [("C1", "S1", "T1", "", 5), ("C2", "S2", "T1", "", 5)]  # 10 على 5 أيّام ⇒ ≥ 2 يوميّاً
    built = build_model(make(rows), ModelOptions(derived_day_cap=False))
    st, sv = solve(built)
    assert st in OK
    for day in range(5):
        assert sum(sv.Value(v) for (_i, d, _p), v in built.x.items() if d == day) >= 2
    # يومٌ بحصّةٍ واحدةٍ ممنوع: يلزم أن يُوزَّع الباقي في الأيّام الأخرى فقط
    one_in_day0 = [(0, 0, 1)]
    off = {"disabled": frozenset({"HC16B", "HC14"}), "even_spread": False}
    assert feasible(make(rows), one_in_day0)
    assert build_model(make(rows), ModelOptions(**off)).constraint_counts["HC16B"] == 0


def test_hc20_same_subject_not_adjacent_unless_double():
    inp = make([("C1", "S1", "T1", "", 7)])  # سقفُ اليوم 2
    assert not feasible(inp, [(0, 0, 1), (0, 0, 2)])  # متجاورتان
    assert feasible(inp, [(0, 0, 1), (0, 0, 3)])  # بينهما حصّة
    assert feasible(inp, [(0, 0, 3), (0, 0, 4)])  # تفصلهما فسحة
    assert feasible(inp, [(0, 0, 1), (0, 0, 2)], disabled=frozenset({"HC20", "HC5"}))
    dbl = make([("C1", "S1", "T1", "", 4)], doubles=frozenset({"S1"}))
    assert feasible(dbl, [(0, 0, 1), (0, 0, 2)])  # الكتلةُ وحدَها مستثناة


def test_hc17_thursday_single_period_for_grade_11_12():
    rows = [("C1", "S1", "T1", "", 6)]
    grades = {"class_grade": {"C1": "G11"}}
    two = [(0, 4, 1), (0, 4, 3)]
    assert not feasible(make(rows), two, **grades)
    assert feasible(make(rows), two)  # بلا صفٍّ معلوم لا حكم (مدخلٌ ناقص)
    assert feasible(make(rows), two, class_grade={"C1": "G9"})
    assert feasible(make(rows), [(0, 4, 1)], **grades)
    assert feasible(make(rows), two, disabled=frozenset({"HC17"}), **grades)


def test_hc17_reads_class_grade_from_inputs_when_adapter_supplies_it():
    inp = make([("C1", "S1", "T1", "", 6)])
    inp.class_grade = {"C1": "G12"}
    assert not feasible(inp, [(0, 4, 1), (0, 4, 3)])


def test_edge_caps_are_hard_with_decision_d166_defaults():
    opt = ModelOptions()
    assert (opt.first_cap, opt.last_cap) == (2, 2)  # قرارُ المالك: السقفان صلبان، لا تحويلَ مرنٌ
    built = build_model(make([("C1", "S1", "T1", "", 3), ("C2", "S2", "T1", "", 3)]), opt)
    assert built.constraint_counts["HC22"] == 1 and built.constraint_counts["HC8"] >= 1
    assert not built.soft_terms


# ───────── فحصُ الإسناد AS ─────────


def test_as2_parallel_group_needs_distinct_teachers():
    same = make([("C1", "S1", "T1", "G", 2), ("C1", "S2", "T1", "G", 2)])
    assert [f.code for f in check_assignment(same) if f.code == "AS-2"] == ["AS-2"]
    ok = make([("C1", "S1", "T1", "G", 2), ("C1", "S2", "T2", "G", 2)])
    assert not [f for f in check_assignment(ok) if f.code == "AS-2"]


def test_as2_joint_task_with_one_teacher_is_a_silent_breach_and_model_proves_it():
    inp = make([("C1", "S1", "T1", "", 2, "J"), ("C1", "S2", "T1", "", 2, "J")])
    assert any(f.code == "AS-2" for f in check_assignment(inp))
    st, _ = solve(build_model(inp))
    assert st == cp_model.INFEASIBLE


def test_as4_personal_cap_vs_load_names_governing_check():
    inp = make([("C1", "S1", "T1", "", 16)], prefs={"T1": TeacherPref("T1", 2, None, None, None)})
    f = next(x for x in check_assignment(inp) if x.teacher_id == "T1")
    assert (f.code, f.severity, f.detail["governing"]) == ("AS-4", "reject", "AS-4")


def test_as5_structural_cap_reject_and_margin_warning():
    # أقصى مجموعةٍ غيرِ متلاصقةٍ في يومٍ بهذا الجرس = 4 فالأسبوعُ 20
    assert max_independent_slots(list(_times().values())) == 4
    assert check_assignment(make([("C1", "S1", "T1", "", 21)]))[0].severity == "reject"
    assert [x.severity for x in check_assignment(make([("C1", "S1", "T1", "", 19)]))] == ["warn"]
    assert (
        check_assignment(make([("C1", "S1", "T1", "", 10)])) == []
    )  # AS-6: لا مانعَ ⇏ الإسنادُ صالح
    assert AS6_SUCCESS_MESSAGE == "لم يُكتشف مانع"


def test_as1_multi_band_teacher_capacity_by_clock():
    # نطاقان بتماسٍّ بالساعة: السقفُ يُحسب بالفواصل الزمنيّة المتّحدة (5 يوميّاً = 25) لا بعدد الحصص (14 خانةً × 5)
    inp = make([("C1", "S1", "T1", "", 13), ("C2", "S2", "T1", "", 13)], bands={"C2": "B3"})
    rejects = [f for f in check_assignment(inp) if f.severity == "reject"]
    assert [f.code for f in rejects] == ["AS-1"]


# ───────── واجهةُ الامتداد ─────────


def test_interface_ids_and_soft_terms_extension_point():
    built = build_model(make([("C1", "S1", "T1", "", 2)]))
    assert built.row_ids == ["C1|S1|T1|"]
    assert all(isinstance(k, tuple) and len(k) == 3 for k in built.x)
    assert built.var_counts["bool_x"] == len(built.x) and built.var_counts["constraints"] > 0
    known = {"DEMAND", "JOINT", "HC1", "HC2", "HC5", "HC6", "HC7", "HC8", "HC9", "HC10", "HC11"}
    known |= {
        "HC12",
        "HC13",
        "HC16",
        "HC19",
        "HC22",
        "DAILY_CAP",
        "HC14",
        "HC16B",
        "HC17",
        "HC20",
        "NO_6_7",
    }
    assert set(built.constraint_counts) <= known
    n = add_soft_terms(built, [("consecutive", built.x[0, 0, 1], 10), ("gap", built.x[0, 0, 2], 8)])
    assert n == 2
    st, sv = solve(built)
    assert st == cp_model.OPTIMAL and sv.ObjectiveValue() == 0


# ───────── fixture_anonymized.json ─────────


def _fixture_inputs():
    d = json.loads(FIXTURE.read_text(encoding="utf-8"))
    inp = CpSatInputs()
    inp.demand = [
        DemandRow(r["cls"], r["subj"], r["teacher"], r["elec"], r["n"]) for r in d["demand"]
    ]
    inp.bell = {
        k: {"periods": v["periods"], "touch": [tuple(t) for t in v["touch"]]}
        for k, v in d["bell"].items()
    }
    inp.times = {k: {int(p): tuple(t) for p, t in v.items()} for k, v in d["times"].items()}
    inp.class_band = d["class_band"]
    # الحزمةُ بلا مراحل: تُستنتج من جرس الخميس (7 حصصٍ = ثانويّ، 6 = إعداديّ) — وبلا استنتاجٍ يقصّ HC4 كلَّ خميسٍ إلى 6.
    inp.class_level = {
        c: "sec" if len(d["bell"][f"{b}|thursday"]["periods"]) >= 7 else "prep"
        for c, b in d["class_band"].items()
    }
    inp.doubles = frozenset(d["doubles"])
    _derive_blocks(inp, inp.doubles)
    inp.ex_full = frozenset((t, day) for t, day in d["ex_full"])
    inp.ex_period = frozenset((t, day, p) for t, day, p in d["ex_period"])
    inp.prefs = {
        p["teacher_id"]: TeacherPref(
            p["teacher_id"],
            p["max_daily_periods"],
            p["max_consecutive"],
            p["max_gap"],
            p["free_day"],
        )
        for p in d["prefs"]
    }
    inp.res_cap = {r["id"]: r["capacity"] for r in d["resources"]}
    inp.res_subjects = {k: frozenset(v) for k, v in d["res_subjects"].items()}
    return inp


def _run_fixture(capsys, label, limit, **opt):
    inp = _fixture_inputs()
    t0 = time.perf_counter()
    built = build_model(inp, ModelOptions(**opt))
    build_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    st, sv = solve(built, workers=8, limit=limit)
    solve_s = time.perf_counter() - t1
    with capsys.disabled():
        print(
            f"[V2-S3a fixture:{label}] status={sv.StatusName(st)} build={build_s:.1f}s solve={solve_s:.1f}s "
            f"limit={limit:.0f}s lessons={inp.total} vars={built.var_counts} "
            f"disabled={list(built.disabled)} workers=8 seed=7 counts={dict(built.constraint_counts)}"
        )
    return st


# الجدوى على الحزمة المقنَّعة تعتمد على التفاصيل لا النسب (AS-6)؛ فالمراتبُ المقيسةُ هنا هي ما يُثبَت لا ما يُرجى.
_NO_FAIRNESS = {
    "disabled": frozenset({"HC22", "HC8", "HC14", "HC16B"}),
    "derived_day_cap": False,
    "even_spread": False,
}


@pytest.mark.slow
def test_fixture_physical_core_and_assumptions_solve(capsys):
    """HC1 HC2 HC4 HC5 HC6(سقف) HC7 HC9 HC10 HC11 HC12 HC19 + سقفُ اليوم الشخصيّ: OPTIMAL (قيس ~7 ثوانٍ، 8 عمّال)."""
    st = _run_fixture(capsys, "core", 120.0, **_NO_FAIRNESS)
    assert st in OK


@pytest.mark.slow
def test_fixture_with_even_day_spread_solves(capsys):
    """+ HC6 بالقسمة الكاملة (⌊n/D⌋ ≤ عددُ اليوم ≤ ⌈n/D⌉): OPTIMAL (قيس 9–54 ثانية بحسب الحمل)."""
    st = _run_fixture(capsys, "core+even", 120.0, **{**_NO_FAIRNESS, "even_spread": True})
    assert st in OK


@pytest.mark.slow
def test_fixture_with_day_floors_hc14_hc16b_is_recorded_not_assumed(capsys):
    """+ HC14 (لا يومَ فارغاً) وHC16B (حدٌّ أدنى لليوم): قيس 2026-10-08 UNKNOWN في 90ث على هذا الإسناد (HC14 وحدَه كذلك)."""
    st = _run_fixture(
        capsys,
        "core+floors",
        30.0,
        disabled=frozenset({"HC22", "HC8"}),
        derived_day_cap=False,
        even_spread=False,
    )
    assert st != cp_model.MODEL_INVALID


@pytest.mark.slow
def test_fixture_with_decision_d166_caps_is_recorded_not_assumed(capsys):
    """HC22 أولى≤2 وHC8 أخيرة≤2 وHC16 المشتقّ (الافتراضُ كلُّه): INFEASIBLE مُبرهَن على هذا الإسناد المولَّد.

    قيس 2026-10-08 (8 عمّال، بذرة 7): INFEASIBLE في ~3.5ث — برهانٌ لا مهلة، وهو ما يتنبّأ به ADR/المواصفة (2/2 يحتاج
    إسناداً يُبنى له، AS-6). وكلُّ قيدٍ وحدَه فوق النواة غيرُ محسومٍ في 120ث (أولى≤3: OPTIMAL ~79ث؛ أخيرة≤6: ~11ث).
    فالاختبار يسجّل الحالةَ المقيسة ولا يدّعي جدوى.
    """
    st = _run_fixture(capsys, "d166", 60.0)
    assert st == cp_model.INFEASIBLE  # برهانٌ مُقاس؛ تغيّرُه يستدعي إعادةَ قراءة الحزمة والسقفين


def test_parallel_group_members_share_the_same_cells():
    """المجموعةُ المتوازية مهمّةٌ واحدةٌ: أعضاؤها في الخانة نفسها لا في خاناتٍ منفصلة (كما يبنيها المنصّة ويطابقها المُقيِّم)."""
    rows = [("C1", "S1", "T1", "G", 1), ("C1", "S2", "T2", "G", 1)]
    inp = make(rows)
    assert feasible(inp, [(0, 0, 1), (1, 0, 1)])
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2)])


def test_adjacent_cells_of_a_double_subject_need_a_block():
    """ازدواجٌ صلبٌ بعدد الكتل: 4 حصصٍ بكتلة واحدة لا تجيز تلاصقَ أكثر من كتلة."""
    inp = make([("C1", "S1", "T1", "", 4)])
    inp.demand = [DemandRow("C1", "S1", "T1", "", 4, "", 1)]
    # كتلتان متلاصقتان (1-2 و3-4) تجمعان 3 تلاصقات: ممنوعٌ حين لا تُعلَن إلّا كتلة
    assert not feasible(inp, [(0, 0, 1), (0, 0, 2), (0, 1, 1), (0, 1, 2)])


def test_floor_relaxation_is_declared_for_block_only_teachers():
    """D-286م: معلّمٌ كلُّ حمله كتل لا يبلغ أرضيّةً فرديّة؛ تُخفَّف وتُعلَن بلا إرخاءٍ صامت."""
    from operations.scheduler_v2.hard_constraints import _feasible_floor

    # T-053 في الحزمة المقنَّعة: حمل 18 = 9 كتل، 5 أيام، الأرضيّة 3 ← 2
    assert _feasible_floor(18, 9, 5, 3, single_rows=0) == 2
    # كتلتان في 4 أيام: لا يومَ مضمون ← 0
    assert _feasible_floor(4, 2, 4, 1, single_rows=0) == 0
    # بلا كتلٍ تُستوفى الأرضيّة كما هي (لا يمرّ هنا أصلاً): كتلة وثلاثُ مفردات من ثلاثة صفوف في 4 أيام
    assert _feasible_floor(5, 1, 4, 1, single_rows=3) == 1
    # T-008: 4 كتل ومفردتان من صفٍّ واحدٍ (سقفُ HC6 مفردةٌ في اليوم) ← 2 غيرُ ممكنة، 1 ممكنة
    assert _feasible_floor(10, 4, 5, 2, single_rows=1) == 1
    rows = [("C1", "S1", "T1", "", 4)]
    inp = make(rows, doubles=frozenset({"S1"}))
    built = build_model(inp, ModelOptions(derived_day_cap=False))
    assert built.relaxations == []  # حمل 4 في 5 أيام: لا أرضيّةَ أصلاً فلا إرخاء


def test_two_different_elective_groups_cannot_share_a_class_cell():
    """المُقيِّم لا يجيز مجموعتين اختياريّتين مختلفتين في خانة شعبةٍ واحدة (البصمةُ اتحادٌ فتصير orphan_cells)."""
    inp = make([("C1", "S1", "T1", "GA", 1), ("C1", "S2", "T2", "GB", 1)])
    assert not feasible(inp, [(0, 0, 3), (1, 0, 3)])
    assert feasible(inp, [(0, 0, 3), (1, 0, 4)])


def test_touch_relaxation_is_declared_and_caps_runs_at_two():
    """تخفيف التلاصق المعلَن (قرار المالك 2026-10-09): حصتان متتاليتان مسموحتان لمعلّم مخفَّف، والثالثة تُرفض بسقف 2."""
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1), ("C3", "S3", "T1", "", 1)]
    inp = make(rows)
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2)])
    assert feasible(inp, [(0, 0, 1), (1, 0, 2)], touch_relaxed=frozenset({"T1"}))
    assert feasible(
        inp, [(0, 0, 1), (1, 0, 2)], touch_relaxed=frozenset({"T1"}), touch_relaxed_run_cap=2
    )
    assert not feasible(
        inp,
        [(0, 0, 1), (1, 0, 2), (2, 0, 3)],
        touch_relaxed=frozenset({"T1"}),
        touch_relaxed_run_cap=2,
    )
    built = build_model(inp, ModelOptions(touch_relaxed=frozenset({"T1"})))
    assert any(r["teacher"] == "T1" and r["code"] == "HC5" for r in built.relaxations)


def test_no_6_7_forbids_a_teacher_in_both_periods_of_a_day():
    """قيدٌ صلب بأمر المالك: السادسة والسابعة معاً ممنوعتان على المعلّم (ولو في شعبتين)."""
    inp = make([("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)])
    assert feasible(inp, [(0, 0, 6), (1, 0, 7)], touch_relaxed=frozenset({"T1"}))
    assert not feasible(inp, [(0, 0, 6), (1, 0, 7)], no_6_7=True, touch_relaxed=frozenset({"T1"}))
    assert feasible(inp, [(0, 0, 6), (1, 0, 5)], no_6_7=True, touch_relaxed=frozenset({"T1"}))


def test_band_transition_stays_hard_after_touch_relaxation():
    """HC13 يبقى صلباً مع تخفيف HC5: جرسان مختلفان يتماسّان تماماً لا يجتمعان لمعلّمٍ واحد."""
    inp = make([("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)])
    assert feasible(inp, [(0, 0, 3), (1, 0, 4)], touch_relaxed=frozenset({"T1"}))
