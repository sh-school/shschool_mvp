"""soft_constraints.py — القيودُ المرنةُ الثلاثةَ عشرَ بصيغة CP-SAT (V2-S3، W-20261003-016).

كلُّ قيدٍ هنا **عدٌّ خطّيٌّ بلا وزن**: دالّةٌ تُرجع تعبيراً صحيحاً (عددَ المخالفات
بوحدتها) والوزنُ يُضرب فيه في `objective.py`. فالوزنُ بيانٌ (تعدادٌ مغلقٌ ومدًى
متحقَّق) والصيغةُ شيفرة، ولا يختلط أحدُهما بالآخر.

الأصلُ المحاكى هو `operations/scheduler_constraints.evaluate_soft_constraints` (كلفةٌ
تُقيَّم خانةً خانةً أثناء الجشع)؛ وهنا تُقيَّم **على الأسبوع كلِّه** دفعةً واحدة، فتُرمَّز
الكلفةُ التراكميّةُ بصيغتها المغلقة:

    extra_edge_period   e أطرافٍ للمعلّم ← 1+2+…+(e−1) = e(e−1)/2
    daily_load          e فوق السقف     ← 1+2+…+e     = e(e+1)/2 (×2 لمن كُتب تفضيلُه)
    first_period_floor  مكافأةٌ متصاعدةٌ: الأولى 2 والثانيةُ 1 (MIN_FIRST_PERIODS=2)

**لا حركةَ عن جدولٍ قائم**: لا يدخل الجدولُ الحاليُّ أيَّ حدٍّ هنا (قرارُ المالك
2026-10-01 — التوليدُ من الصفر).

**سلامةُ التصغير:** الأوزانُ الموجبةُ تُصغَّر، فالمتغيّراتُ المساعدةُ يكفي لها حدٌّ أدنى
(تُجبَر على الصحّة ما لزمت). أمّا المكافآتُ (وزنٌ سالب) فمتغيّراتُها تُقيَّد من الجهة
الأخرى (`u ⇒ شرطُها`) كي لا يحصد الحلُّ مكافأةً لم يستحقّها. ويحرس ذلك اختبارٌ يقارن
قيمةَ الهدف بمقيِّمٍ مستقلٍّ بلا CP-SAT (`evaluate_placements`).

**ما هو تقريبٌ لا مطابقة** (موثَّقٌ في الدالّة): `day_balance` (تُعدّ الزيادةُ فوق حصّة
القسمة والأيّامُ الفارغةُ على الأسبوع بدل الفحص عند كلّ وضع)، و`gap` يعدّ الثقوبَ بأرقام الحصص.

ولا يستورد هذا الملفُّ `model.py` (ملكُ v2-core): يتّفق معه عبر `BuiltModelView`.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Protocol

from ..constraint_registry import SOFT_CONSTRAINTS

if TYPE_CHECKING:
    from ortools.sat.python import cp_model

    from ..cpsat_adapter import CpSatInputs

#: مفاتيحُ القيود المرنة — مصدرُها السجلُّ نفسُه فلا قائمةَ ثانيةً تتقادم.
SOFT_KEYS: tuple[str, ...] = tuple(s.code for s in SOFT_CONSTRAINTS)

#: ثوابتُ الدالّة القائمة (`scheduler_constraints`) منسوخةً مقروءة — يحرس تطابقَها اختبار.
DAYS = range(5)
THURSDAY = 4
FIRST_PERIOD, LAST_PERIOD = 1, 7
#: آخرُ حصّةٍ في «النصف الأوّل» (المختبر: `MORNING_LAST`) — الثقيلةُ بعدها تُعاقَب والنشاطُ فيه.
MORNING_LAST = 4
MIN_FIRST_PERIODS = 2
DEFAULT_MAX_DAILY = 5
EXPLICIT_PREFERENCE_FACTOR = 2
HIGH_WEEKLY_THRESHOLD = 5
#: التلاصقُ بالساعة (HC5): فجوةٌ ≤ 10 دقائق بين حصّتين تُعدّ اتّصالاً.
JOINABLE_GAP_MINUTES = 10


class BuiltModelView(Protocol):
    """ما أحتاجه من `BuiltModel` (v2-core) — عقدٌ مؤقّتٌ يُستبدل باستيرادها حين تستقرّ.

    `x[(i, day, period)]` متغيّرُ قرارٍ ثنائيّ: الطلبُ `inputs.demand[i]` يقع في (يوم، حصّة).
    """

    model: cp_model.CpModel
    x: Mapping[tuple[int, int, int], cp_model.IntVar]
    inputs: CpSatInputs


def _day_kind(day: int) -> str:
    return "thursday" if day == THURSDAY else "regular"


def touching(inputs: CpSatInputs, cls: str, day: int) -> list[tuple[int, int]]:
    """أزواجُ الحصص المتجاورةِ زمناً (بلا فسحةٍ ولا صلاة) في جرس هذه الشعبة."""
    entry = inputs.bell.get(f"{inputs.class_band.get(cls, '')}|{_day_kind(day)}")
    if entry and "touch" in entry:
        return [(int(a), int(b)) for a, b in entry["touch"]]
    ps = sorted(inputs.periods(cls, day))
    return [(a, a + 1) for a in ps if a + 1 in ps]


def gap_minutes(inputs: CpSatInputs, ri, pa: int, rj, pb: int, day: int) -> int | None:
    """الفجوةُ بالدقائق بين خانتين لمعلّمٍ في يومٍ؛ بلا أوقاتٍ ← 1 للمتجاورتين رقماً وإلّا لا شيء."""
    spans = []
    for row, p in ((ri, pa), (rj, pb)):
        band = inputs.class_band.get(row.cls, "")
        span = inputs.times.get(f"{band}|{_day_kind(day)}", {}).get(p)
        if span is None:
            return 1 if abs(pa - pb) == 1 else None
        spans.append(span)
    (s1, e1), (s2, e2) = spans
    return s2 - e1 if e1 <= s2 else s1 - e2


def _is_intended_double(inputs: CpSatInputs, ri, rj) -> bool:
    return ri.cls == rj.cls and ri.subj == rj.subj and ri.subj in inputs.doubles


class SoftContext:
    """فهارسُ مشتركةٌ بين القيود: تُبنى مرّةً واحدة."""

    def __init__(self, built: BuiltModelView, pedagogy: Mapping[str, str]) -> None:
        self.model = built.model
        self.x = built.x
        self.inputs = built.inputs
        #: {معرّفُ المادّة: heavy|activity|regular} — لا يحمله `CpSatInputs` اليوم (طلبٌ لـv2-core).
        self.pedagogy = pedagogy
        self.demand = self.inputs.demand
        self.cell: dict[tuple[int, int], dict[int, cp_model.IntVar]] = defaultdict(dict)
        for (i, d, p), var in self.x.items():
            self.cell[i, d][p] = var
        self.rows_of_teacher: dict[str, list[int]] = defaultdict(list)
        self.rows_of_group: dict[tuple[str, str], list[int]] = defaultdict(list)
        for i, row in enumerate(self.demand):
            self.rows_of_teacher[row.teacher].append(i)
            self.rows_of_group[row.cls, row.subj].append(i)
        self._occ: dict[tuple[str, int], dict[int, cp_model.IntVar]] = {}

    def occ(self, teacher: str, day: int) -> dict[int, cp_model.IntVar]:
        """إشغالُ المعلّم لكلّ حصّةٍ في اليوم — متغيّرٌ مساوٍ تماماً لـOR متغيّراتها."""
        key = teacher, day
        if key not in self._occ:
            by_p: dict[int, list] = defaultdict(list)
            for i in self.rows_of_teacher[teacher]:
                for p, var in self.cell.get((i, day), {}).items():
                    by_p[p].append(var)
            cells = {}
            for p, vs in sorted(by_p.items()):
                if len(vs) == 1:
                    cells[p] = vs[0]
                else:
                    o = self.model.NewBoolVar("")
                    self.model.AddMaxEquality(o, vs)
                    cells[p] = o
            self._occ[key] = cells
        return self._occ[key]

    def group_at(self, cls: str, subj: str, day: int, period: int) -> list:
        """متغيّراتُ (الشعبة، المادّة) في خانة — مجموعُها 0 أو 1 بعد HC2."""
        return [
            self.cell[i, day][period]
            for i in self.rows_of_group[cls, subj]
            if period in self.cell.get((i, day), {})
        ]


def _sum(items: Iterable):
    from ortools.sat.python import cp_model

    return cp_model.LinearExpr.Sum(list(items))


# ── القيود: كلٌّ يُرجع تعبيراً بوحدة المخالفة، والوزنُ يُضرب لاحقاً ─────────────────────


def core_early(ctx: SoftContext):
    """الموادُّ الثقيلةُ بعد الحصّة الرابعة — حصّةٌ ثقيلةٌ ⇒ وحدة."""
    return _sum(
        var
        for (i, _d, p), var in ctx.x.items()
        if ctx.pedagogy.get(ctx.demand[i].subj) == "heavy" and p > MORNING_LAST
    )


def pe_after_break(ctx: SoftContext):
    """مادّةُ النشاط (بدنيّةٌ وفنّيّةٌ…) قبل الاستراحة — حصّةٌ في 1..4 ⇒ وحدة."""
    return _sum(
        var
        for (i, _d, p), var in ctx.x.items()
        if ctx.pedagogy.get(ctx.demand[i].subj) == "activity" and p <= MORNING_LAST
    )


def thursday_pair(ctx: SoftContext):
    """الحصّةُ الثانيةُ فأكثر للمادّة (غيرِ المزدوجة) يومَ الخميس ⇒ وحدةٌ لكلّ حصّةٍ زائدة."""
    terms = []
    for (_cls, subj), rows in ctx.rows_of_group.items():
        if subj in ctx.inputs.doubles:
            continue
        vs = [v for i in rows for v in ctx.cell.get((i, THURSDAY), {}).values()]
        if len(vs) < 2:
            continue
        excess = ctx.model.NewIntVar(0, len(vs), "")
        ctx.model.Add(excess >= _sum(vs) - 1)
        terms.append(excess)
    return _sum(terms)


def free_day(ctx: SoftContext):
    """حصّةٌ في اليوم الذي طلب المعلّمُ تفريغَه ⇒ وحدة."""
    terms = []
    for teacher, pref in ctx.inputs.prefs.items():
        if pref.free_day is None:
            continue
        for i in ctx.rows_of_teacher.get(teacher, ()):
            terms.extend(ctx.cell.get((i, pref.free_day), {}).values())
    return _sum(terms)


def extra_edge_period(ctx: SoftContext):
    """أطرافُ المعلّم (أولى أو سابعة) تتصاعد: e طرفاً ⇒ e(e−1)/2."""
    terms = []
    for teacher in ctx.rows_of_teacher:
        edges = [
            o
            for d in DAYS
            for p, o in ctx.occ(teacher, d).items()
            if p in (FIRST_PERIOD, LAST_PERIOD)
        ]
        if len(edges) < 2:
            continue
        e = _sum(edges)
        for j in range(2, len(edges) + 1):
            z = ctx.model.NewBoolVar("")
            ctx.model.Add(e <= j - 1).OnlyEnforceIf(z.Not())
            terms.append((j - 1) * z)
    return _sum(terms)


def first_period_floor(ctx: SoftContext):
    """مكافأةٌ متصاعدةٌ لمن دون MIN_FIRST_PERIODS من الأُولى: الأولى 2 والثانيةُ 1 (وزنُه سالب).

    `u_j ⇒ f ≥ j` يمنع حصدَ مكافأةٍ لأُولى لم تقع.
    """
    terms = []
    for teacher in ctx.rows_of_teacher:
        firsts = [
            ctx.occ(teacher, d)[FIRST_PERIOD] for d in DAYS if FIRST_PERIOD in ctx.occ(teacher, d)
        ]
        if not firsts:
            continue
        f = _sum(firsts)
        for j in range(1, min(MIN_FIRST_PERIODS, len(firsts)) + 1):
            u = ctx.model.NewBoolVar("")
            ctx.model.Add(f >= j).OnlyEnforceIf(u)
            terms.append((MIN_FIRST_PERIODS - j + 1) * u)
    return _sum(terms)


def double_bonus(ctx: SoftContext):
    """مكافأةٌ لكلّ زوجٍ متجاورٍ من مادّةٍ مزدوجة (وزنُه سالب)."""
    terms = []
    for cls, subj in ctx.rows_of_group:
        if subj not in ctx.inputs.doubles:
            continue
        for d in DAYS:
            for a, b in touching(ctx.inputs, cls, d):
                va, vb = ctx.group_at(cls, subj, d, a), ctx.group_at(cls, subj, d, b)
                if not va or not vb:
                    continue
                y = ctx.model.NewBoolVar("")
                ctx.model.Add(y <= _sum(va))
                ctx.model.Add(y <= _sum(vb))
                terms.append(y)
    return _sum(terms)


def high_weekly_adjacent(ctx: SoftContext):
    """مادّةٌ بخمسٍ فأكثر (غيرُ مزدوجة): حصّتان متجاورتان في اليوم ⇒ وحدةٌ لكلّ زوج."""
    terms = []
    for (cls, subj), rows in ctx.rows_of_group.items():
        if subj in ctx.inputs.doubles:
            continue
        if sum(ctx.demand[i].n for i in rows) < HIGH_WEEKLY_THRESHOLD:
            continue
        for d in DAYS:
            for a, b in touching(ctx.inputs, cls, d):
                va, vb = ctx.group_at(cls, subj, d, a), ctx.group_at(cls, subj, d, b)
                if not va or not vb:
                    continue
                y = ctx.model.NewBoolVar("")
                ctx.model.Add(y >= _sum(va) + _sum(vb) - 1)
                terms.append(y)
    return _sum(terms)


def consecutive(ctx: SoftContext):
    """معلّمٌ في حصّتين متّصلتين (فجوةٌ ≤ 10 د) ⇒ وحدةٌ لكلّ زوج، عدا المزدوجة المقصودة."""
    terms = []
    for rows in ctx.rows_of_teacher.values():
        for d in DAYS:
            cand = [(i, p) for i in rows for p in sorted(ctx.cell.get((i, d), {}))]
            for n, (i, pa) in enumerate(cand):
                for j, pb in cand[n + 1 :]:
                    if pa == pb or _is_intended_double(ctx.inputs, ctx.demand[i], ctx.demand[j]):
                        continue
                    gap = gap_minutes(ctx.inputs, ctx.demand[i], pa, ctx.demand[j], pb, d)
                    if gap is None or gap > JOINABLE_GAP_MINUTES:
                        continue
                    y = ctx.model.NewBoolVar("")
                    ctx.model.Add(y >= ctx.cell[i, d][pa] + ctx.cell[j, d][pb] - 1)
                    terms.append(y)
    return _sum(terms)


def gap(ctx: SoftContext):
    """ثقبٌ في يوم المعلّم: حصّةٌ فارغةٌ بين حصّتين له ⇒ وحدة."""
    m = ctx.model
    terms = []
    for teacher in ctx.rows_of_teacher:
        for d in DAYS:
            occ = ctx.occ(teacher, d)
            ps = sorted(occ)
            if len(ps) < 3:
                continue
            pre: dict[int, object] = {}
            suf: dict[int, object] = {}
            for k, p in enumerate(ps):
                pre[p] = m.NewBoolVar("")
                m.Add(pre[p] >= occ[p])
                if k:
                    m.Add(pre[p] >= pre[ps[k - 1]])
            for k in range(len(ps) - 1, -1, -1):
                p = ps[k]
                suf[p] = m.NewBoolVar("")
                m.Add(suf[p] >= occ[p])
                if k < len(ps) - 1:
                    m.Add(suf[p] >= suf[ps[k + 1]])
            for k in range(1, len(ps) - 1):
                hole = m.NewBoolVar("")
                m.Add(hole >= pre[ps[k - 1]] + suf[ps[k + 1]] - occ[ps[k]] - 1)
                terms.append(hole)
    return _sum(terms)


def subject_spread(ctx: SoftContext):
    """تكرارُ المادّة (غيرِ المزدوجة) في يومٍ بينما يومٌ آخرُ ممكنٌ فارغ.

    = حصصُ المادّة − الأيّامُ المستعملة − ما لا مفرَّ منه (n − الأيّامُ الممكنة).
    """
    m = ctx.model
    terms = []
    for (_cls, subj), rows in ctx.rows_of_group.items():
        if subj in ctx.inputs.doubles:
            continue
        n = sum(ctx.demand[i].n for i in rows)
        used = []
        for d in DAYS:
            vs = [v for i in rows for v in ctx.cell.get((i, d), {}).values()]
            if not vs:
                continue
            u = m.NewBoolVar("")
            m.Add(_sum(vs) >= 1).OnlyEnforceIf(u)
            used.append(u)
        if used:
            terms.append(n - max(n - len(used), 0) - _sum(used))
    return _sum(terms)


def daily_load(ctx: SoftContext):
    """الحملُ اليوميُّ فوق السقف يتصاعد: e فوقه ⇒ e(e+1)/2، مضاعفاً لمن كُتب تفضيلُه."""
    m = ctx.model
    terms = []
    for teacher in ctx.rows_of_teacher:
        cap, factor = _load_cap(ctx.inputs, teacher)
        for d in DAYS:
            occ = ctx.occ(teacher, d)
            if len(occ) <= cap:
                continue
            c = _sum(occ.values())
            for j in range(1, len(occ) - cap + 1):
                z = m.NewBoolVar("")
                m.Add(c <= cap + j - 1).OnlyEnforceIf(z.Not())
                terms.append(factor * j * z)
    return _sum(terms)


def _load_cap(inputs: CpSatInputs, teacher: str) -> tuple[int, int]:
    pref = inputs.prefs.get(teacher)
    if pref is not None and pref.max_daily_periods is not None:
        return pref.max_daily_periods, EXPLICIT_PREFERENCE_FACTOR
    return DEFAULT_MAX_DAILY, 1


def day_balance(ctx: SoftContext):
    """توازنُ أيّام المعلّم: ما فوق حصّة القسمة ⌈النصاب÷الأيّام⌉، ويومٌ فارغٌ يمكن ملؤه."""
    m = ctx.model
    terms = []
    for teacher, rows in ctx.rows_of_teacher.items():
        days = [d for d in DAYS if ctx.occ(teacher, d)]
        if not days:
            continue
        load = sum(ctx.demand[i].n for i in rows)
        share = math.ceil(load / len(days))
        for d in days:
            c = _sum(ctx.occ(teacher, d).values())
            over = m.NewIntVar(0, len(ctx.occ(teacher, d)), "")
            m.Add(over >= c - share)
            terms.append(over)
            if load >= len(days):
                empty = m.NewBoolVar("")
                m.Add(c >= 1).OnlyEnforceIf(empty.Not())
                terms.append(empty)
    return _sum(terms)


#: مفتاحٌ ← مُنشئُ تعبيره. المفاتيحُ هي مفاتيحُ السجلّ حرفاً (يحرسه اختبار).
BUILDERS: dict[str, Callable[[SoftContext], object]] = {
    "consecutive": consecutive,
    "gap": gap,
    "subject_spread": subject_spread,
    "daily_load": daily_load,
    "day_balance": day_balance,
    "thursday_pair": thursday_pair,
    "core_early": core_early,
    "pe_after_break": pe_after_break,
    "double_bonus": double_bonus,
    "high_weekly_adjacent": high_weekly_adjacent,
    "extra_edge_period": extra_edge_period,
    "first_period_floor": first_period_floor,
    "free_day": free_day,
}


def build_terms(built: BuiltModelView, pedagogy: Mapping[str, str]) -> dict[str, object]:
    """تعابيرُ القيود الثلاثةَ عشر بلا أوزان."""
    ctx = SoftContext(built, pedagogy)
    return {key: BUILDERS[key](ctx) for key in SOFT_KEYS}


# ── المقيِّم المستقلّ: الصيغةُ نفسُها بلا CP-SAT، على جدولٍ جاهز ───────────────────────


def evaluate_placements(
    inputs: CpSatInputs,
    pedagogy: Mapping[str, str],
    placements: Iterable[tuple[int, int, int]],
    available: Iterable[tuple[int, int, int]],
) -> dict[str, int]:
    """عددُ مخالفات كلّ قيدٍ على جدولٍ `{(i, day, period)}` — بوحدات `build_terms`.

    `available` مفاتيحُ `x` (الخاناتُ الممكنةُ)، يحتاجها `subject_spread` و`day_balance` لمعرفة
    الأيّام الممكنة. يتحقّق به الاختبارُ من أنّ ترميزَ CP-SAT يطابق التعريف، ويصلح مقيِّماً
    مستقلاًّ عن الباني (ADR 0008) لتقرير جودة جدولٍ بلا حلّال.
    """
    placed = set(placements)
    cost = dict.fromkeys(SOFT_KEYS, 0)
    tcells: dict[tuple[str, int], dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    gcells: dict[tuple[str, str, int], set[int]] = defaultdict(set)
    for i, d, p in placed:
        row = inputs.demand[i]
        tcells[row.teacher, d][p].append(i)
        gcells[row.cls, row.subj, d].add(p)
    _eval_cell_terms(inputs, pedagogy, placed, cost)
    _eval_teacher_terms(inputs, set(available), tcells, cost)
    _eval_group_terms(inputs, set(available), gcells, cost)
    return {k: int(v) for k, v in cost.items()}


def _eval_cell_terms(inputs, pedagogy, placed, cost) -> None:
    """القيودُ التي تُقاس خانةً خانة: core_early وpe_after_break وfree_day."""
    for i, d, p in placed:
        row = inputs.demand[i]
        ped = pedagogy.get(row.subj)
        cost["core_early"] += ped == "heavy" and p > MORNING_LAST
        cost["pe_after_break"] += ped == "activity" and p <= MORNING_LAST
        pref = inputs.prefs.get(row.teacher)
        cost["free_day"] += pref is not None and pref.free_day == d


def _eval_teacher_terms(inputs, avail, tcells, cost) -> None:
    """قيودُ المعلّم الأسبوعيّة: الحملُ والثقوبُ والتلاصقُ والتوازنُ والأطراف والأُولى."""
    dem = inputs.demand
    for t in {r.teacher for r in dem}:
        cap, factor = _load_cap(inputs, t)
        edges = firsts = 0
        cand_days = [d for d in DAYS if any(k[1] == d and dem[k[0]].teacher == t for k in avail)]
        load = sum(r.n for r in dem if r.teacher == t)
        share = math.ceil(load / len(cand_days)) if cand_days else 0
        for d in DAYS:
            cells = tcells.get((t, d), {})
            edges += (FIRST_PERIOD in cells) + (LAST_PERIOD in cells)
            firsts += FIRST_PERIOD in cells
            over = max(len(cells) - cap, 0)
            cost["daily_load"] += factor * over * (over + 1) // 2
            ps = sorted(cells)
            if ps:
                cost["gap"] += sum(1 for p in range(ps[0], ps[-1] + 1) if p not in cells)
            cost["consecutive"] += _count_consecutive(inputs, cells, d)
            if d in cand_days:
                cost["day_balance"] += max(len(cells) - share, 0)
                cost["day_balance"] += load >= len(cand_days) and not cells
        cost["extra_edge_period"] += edges * (edges - 1) // 2
        cost["first_period_floor"] += sum(
            MIN_FIRST_PERIODS - j + 1 for j in range(1, min(MIN_FIRST_PERIODS, firsts) + 1)
        )


def _eval_adjacent_pairs(inputs, gcells, cls, subj) -> int:
    """أزواجُ الحصص المتجاورةِ لـ(الشعبة، المادّة) على الأسبوع."""
    total = 0
    for d in DAYS:
        cells = gcells.get((cls, subj, d), set())
        total += sum(1 for a, b in touching(inputs, cls, d) if a in cells and b in cells)
    return total


def _eval_group_terms(inputs, avail, gcells, cost) -> None:
    """قيودُ (الشعبة، المادّة): المزدوجةُ والخميسُ والتفريقُ وتلاصقُ عاليةِ النصاب."""
    dem = inputs.demand
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, r in enumerate(dem):
        groups[r.cls, r.subj].append(i)
    for (cls, subj), rows in groups.items():
        if subj in inputs.doubles:
            cost["double_bonus"] += _eval_adjacent_pairs(inputs, gcells, cls, subj)
            continue
        n = sum(dem[i].n for i in rows)
        possible = {d for (i, d, _p) in avail if i in rows}
        used = sum(1 for d in DAYS if gcells.get((cls, subj, d)))
        # HC2 يمنع حصّتين في خانة، فعدُّ الخانات المميّزة = عدُّ الحصص
        cost["thursday_pair"] += max(len(gcells.get((cls, subj, THURSDAY), ())) - 1, 0)
        if possible:
            cost["subject_spread"] += n - max(n - len(possible), 0) - used
        if n >= HIGH_WEEKLY_THRESHOLD:
            cost["high_weekly_adjacent"] += _eval_adjacent_pairs(inputs, gcells, cls, subj)


def _count_consecutive(inputs: CpSatInputs, cells: dict[int, list[int]], day: int) -> int:
    dem = inputs.demand
    items = [(i, p) for p, rows in sorted(cells.items()) for i in rows]
    total = 0
    for n, (i, pa) in enumerate(items):
        for j, pb in items[n + 1 :]:
            if pa == pb or _is_intended_double(inputs, dem[i], dem[j]):
                continue
            gap = gap_minutes(inputs, dem[i], pa, dem[j], pb, day)
            total += gap is not None and gap <= JOINABLE_GAP_MINUTES
    return total
