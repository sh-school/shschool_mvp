"""اختبارُ حساسيّة المدقّق المستقلّ (W-20260930-004): كلُّ قيدٍ يُكشف بمخالفةٍ مصنوعةٍ يدويّاً، والسليمُ لا يُبلَّغ."""

from tests.test_scheduler_v2_hard import make
from tools.cpsat_audit import audit


def _run(rows, placement, **kw):
    inp = make(rows, **kw)
    avail = {(i, d, p) for i in range(len(rows)) for d in range(5) for p in range(1, 8)}
    return audit(inp, set(placement), avail)["violations"]


def test_clean_placement_reports_nothing():
    rows = [("C1", "S1", "T1", "", 2)]
    assert _run(rows, [(0, 0, 1), (0, 1, 1)]) == {}


def test_hc1_and_hc2_conflicts():
    two = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)]
    assert _run(two, [(0, 0, 3), (1, 0, 3)]).get("HC1/HC12") == 1
    cls = [("C1", "S1", "T1", "", 1), ("C1", "S2", "T2", "", 1)]
    assert _run(cls, [(0, 0, 3), (1, 0, 3)]).get("HC2") == 1


def test_hc5_touching_lessons():
    rows = [("C1", "S1", "T1", "", 1), ("C2", "S2", "T1", "", 1)]
    assert _run(rows, [(0, 0, 1), (1, 0, 2)]).get("HC5") == 1


def test_hc6_day_cap_and_hc7_same_period():
    rows = [("C1", "S1", "T1", "", 3)]
    assert _run(rows, [(0, 0, 1), (0, 0, 4), (0, 1, 1)]).get("HC6") == 1
    assert _run(rows, [(0, 0, 2), (0, 1, 2), (0, 2, 2)]).get("HC7") == 1


def test_demand_shortfall_and_unavailable_cell():
    rows = [("C1", "S1", "T1", "", 2)]
    assert _run(rows, [(0, 0, 1)]).get("DEMAND") == 1
    inp = make(rows)
    assert audit(inp, {(0, 0, 1), (0, 1, 1)}, {(0, 0, 1)})["violations"].get("UNAVAILABLE") == 1
