"""سقفُ التتالي الشخصيّ للمعلّم في حلّال V2 (W-20261012-020): يقرؤه الحلّالُ كما يقرؤه المقيِّم."""

from __future__ import annotations

from operations.scheduler_v2.model import ModelOptions, build_model
from tests.test_scheduler_v2_hard import feasible, make

ROWS4 = [
    ("C1", "S1", "T1", "", 1),
    ("C2", "S2", "T1", "", 1),
    ("C3", "S3", "T1", "", 1),
    ("C4", "S4", "T1", "", 1),
]


def test_cap_two_allows_pair_and_forbids_triple():
    inp = make(ROWS4[:3])
    caps = (("T1", 2),)
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2)])
    assert feasible(inp, [(0, 0, 1), (1, 0, 2)], run_cap_override=caps)
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2), (2, 0, 3)], run_cap_override=caps)


def test_cap_three_allows_triple_and_forbids_quad():
    inp = make(ROWS4)
    caps = (("T1", 3),)
    assert feasible(inp, [(0, 0, 4), (1, 0, 5), (2, 0, 6)], run_cap_override=caps)
    assert not feasible(inp, [(0, 0, 4), (1, 0, 5), (2, 0, 6), (3, 0, 7)], run_cap_override=caps)


def test_other_teachers_stay_under_hc5():
    """من لا سقفَ شخصيًّا له يبقى تحت HC5 ولو وُجد سقفٌ لغيره."""
    inp = make([("C1", "S1", "T2", "", 1), ("C2", "S2", "T2", "", 1)])
    assert not feasible(inp, [(0, 0, 1), (1, 0, 2)], run_cap_override=(("T1", 2),))


def test_personal_cap_is_declared_in_relaxations():
    inp = make(ROWS4[:3])
    built = build_model(inp, ModelOptions(run_cap_override=(("T1", 2),)))
    assert any(r["teacher"] == "T1" and r["code"] == "HC5" for r in built.relaxations)
