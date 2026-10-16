"""cpsat_audit.py — مدقّقٌ مستقلّ بعد التوليد (W-20260930-004). سكربتُ تجربةٍ لا يُشحن.

يقرأ ناتجَ حلّال V2 (فهرس الصفّ، اليوم، الحصّة) ويعيد حساب القيود من تعريفاتها **بلا استيراد شيءٍ من
`hard_constraints`**: لا يثق بالنموذج ولا بعدّاداته. وكلُّ تطابقٍ بين ما بناه الحلّالُ وما يحسبه المدقّق دليلٌ؛
وكلُّ خلافٍ مخالفةٌ صامتةٌ محتملة. لا يكتب في القاعدة ولا يمسّ المحرّك.

التشغيل:  python -m tools.cpsat_audit [--seconds 120] [--workers 8] [--drop HC22,HC8,...]
"""

from __future__ import annotations

import argparse
import math
import time
from collections import Counter, defaultdict

import django
from ortools.sat.python import cp_model

django.setup()

from operations.scheduler_v2.model import ModelOptions, build_model
from tests.test_scheduler_v2_hard import _NO_FAIRNESS, _fixture_inputs

MAX_SAME_PERIOD = 2  # HC7
MAX_DAILY = 5  # سقفُ الحمل اليوميّ الافتراضيّ
JOIN_GAP = 10  # دقائق: فاصلٌ أقلُّ منه يعدّ الحصّتين متلاصقتين


class _Audit:
    """كلُّ فحصٍ دالّةٌ صغيرةٌ تعدّ مخالفات قيدٍ واحدٍ من المواضع وحدَها."""

    def __init__(self, inp, placement, available):
        self.inp, self.placement, self.available = inp, placement, available
        self.rows = inp.demand
        self.bad: Counter[str] = Counter()
        self.where: defaultdict[str, list] = defaultdict(list)
        # المتوازيةُ والمشتركةُ تُوضع معاً في الخانة نفسها فلا تُعدّ تضارباً.
        self.group = {
            i: (r.joint or (f"pg|{r.cls}|{r.elec}" if r.elec else f"solo|{i}"))
            for i, r in enumerate(self.rows)
        }
        self.by_t_day: defaultdict[tuple, list] = defaultdict(list)
        for i, d, p in placement:
            self.by_t_day[self.rows[i].teacher, d].append((i, p))

    def flag(self, code, *info):
        self.bad[code] += 1
        if len(self.where[code]) < 5:
            self.where[code].append(info)

    def span(self, cls, d, p):
        band = f"{self.inp.class_band.get(cls, '')}|{'thursday' if d == 4 else 'regular'}"
        return self.inp.times.get(band, {}).get(p)

    def demand(self):
        per_row = Counter(i for i, _d, _p in self.placement)
        for i, r in enumerate(self.rows):
            if per_row[i] != r.n:
                self.flag("DEMAND", i, per_row[i], r.n)
        for cell in self.placement:
            if cell not in self.available:
                self.flag("UNAVAILABLE", cell)

    def teacher_overlap(self):
        """HC1/HC12: معلّمٌ في موضعين متزامنَين (بالساعة لا برقم الحصّة)."""
        for (t, d), cells in self.by_t_day.items():
            for a in range(len(cells)):
                for b in range(a + 1, len(cells)):
                    (ia, pa), (ib, pb) = cells[a], cells[b]
                    if self.group[ia] == self.group[ib]:
                        continue
                    sa, sb = (
                        self.span(self.rows[ia].cls, d, pa),
                        self.span(self.rows[ib].cls, d, pb),
                    )
                    if sa and sb and sa[0] < sb[1] and sb[0] < sa[1]:
                        self.flag("HC1/HC12", t, d, pa, pb)

    def class_overlap(self):
        """HC2: شعبةٌ في مادّتين معاً (غير مجموعةٍ واحدة)."""
        by_c: defaultdict[tuple, set] = defaultdict(set)
        for i, d, p in self.placement:
            by_c[self.rows[i].cls, d, p].add(self.group[i])
        for key, gs in by_c.items():
            if len(gs) > 1:
                self.flag("HC2", key)

    def day_cap(self):
        """HC6: سقفُ اليوم للصفّ = ⌈n / أيامه المتاحة⌉ (وللمزدوج ≥ 2)."""
        days_of: defaultdict[int, set] = defaultdict(set)
        for i, d, _p in self.available:
            days_of[i].add(d)
        for (i, d), n in Counter((i, d) for i, d, _p in self.placement).items():
            r = self.rows[i]
            cap = max(1, math.ceil(r.n / max(1, len(days_of[i]))))
            if r.blocks > 0:
                cap = max(cap, 2)
            if n > cap:
                self.flag("HC6", i, d, n, cap)

    def same_period(self):
        """HC7: المادّةُ في الحصّة نفسِها من اليوم ≤ 2 أسبوعيّاً."""
        for (i, p), n in Counter((i, p) for i, _d, p in self.placement).items():
            if n > MAX_SAME_PERIOD:
                self.flag("HC7", i, p, n)

    def _blocks_in_row(self, i):
        r = self.rows[i]
        days = defaultdict(list)
        for ii, d, p in self.placement:
            if ii == i:
                days[d].append(p)
        blocks = 0
        for d, ps in days.items():
            ps.sort()
            k = 0
            while k < len(ps):
                s1 = self.span(r.cls, d, ps[k])
                s2 = k + 1 < len(ps) and ps[k + 1] == ps[k] + 1 and self.span(r.cls, d, ps[k + 1])
                if s1 and s2 and 0 <= s2[0] - s1[1] <= JOIN_GAP:
                    blocks += 1
                    k += 2
                else:
                    k += 1
        return blocks

    def doubles(self):
        """HC19: المزدوجةُ كتلٌ من حصّتين متلاصقتين."""
        for i, r in enumerate(self.rows):
            if r.blocks > 0 and self._blocks_in_row(i) < r.blocks:
                self.flag("HC19", i, r.blocks)

    def touching(self):
        """HC5: معلّمٌ في حصّتين متلاصقتين بلا استراحة — الاستثناءُ كتلةُ المزدوجة وحدَها."""
        for (t, d), cells in self.by_t_day.items():
            timed = sorted((self.span(self.rows[i].cls, d, p) or (p, p), i, p) for i, p in cells)
            for (s1, i1, p1), (s2, i2, p2) in zip(timed, timed[1:], strict=False):
                if self.group[i1] == self.group[i2] and i1 != i2:
                    continue
                if 0 <= s2[0] - s1[1] <= JOIN_GAP and not (i1 == i2 and self.rows[i1].blocks > 0):
                    self.flag("HC5", t, d, p1, p2)

    def daily_load(self):
        """الحمل اليوميّ: معلّمٌ فوق سقفه الشخصيّ أو العامّ."""
        for (t, d), cells in self.by_t_day.items():
            pref = self.inp.prefs.get(t)
            cap = pref.max_daily_periods if pref and pref.max_daily_periods else MAX_DAILY
            lessons = len({(p, self.group[i]) for i, p in cells})
            if lessons > max(cap, MAX_DAILY):
                self.flag("LOAD", t, d, lessons, cap)


def audit(inp, placement: set[tuple[int, int, int]], available: set[tuple[int, int, int]]) -> dict:
    """يعدّ مخالفاتِ كلّ قيدٍ من المواضع وحدَها. المفتاحُ رمزُ القيد، والقيمةُ عددُ المخالفات."""
    a = _Audit(inp, placement, available)
    for check in (
        a.demand,
        a.teacher_overlap,
        a.class_overlap,
        a.day_cap,
        a.same_period,
        a.doubles,
        a.touching,
        a.daily_load,
    ):
        check()
    return {"violations": dict(a.bad), "samples": dict(a.where)}


def run(seconds: float, workers: int, drop: frozenset[str]) -> dict:
    inp = _fixture_inputs()
    opts = dict(_NO_FAIRNESS)
    opts["disabled"] = frozenset(opts.get("disabled", frozenset())) | drop
    built = build_model(inp, ModelOptions(**opts))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = seconds
    sv.parameters.num_search_workers = workers
    sv.parameters.random_seed = 7
    t0 = time.perf_counter()
    status = sv.Solve(built.model)
    took = time.perf_counter() - t0
    out = {"status": sv.StatusName(status), "seconds": round(took, 1), "lessons": inp.total}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        placed = {k for k, v in built.x.items() if sv.Value(v)}
        out["placed"] = len(placed)
        out.update(audit(inp, placed, set(built.x)))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--drop", default="")
    a = ap.parse_args()
    import json

    print(
        json.dumps(
            run(a.seconds, a.workers, frozenset(filter(None, a.drop.split(",")))),
            ensure_ascii=False,
            indent=1,
            default=str,
        )
    )
