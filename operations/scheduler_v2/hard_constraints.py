"""القيودُ الصلبةُ لنموذج CP-SAT (V2-S3a، W-20261003-016) وفحصُ الإسناد AS-1..AS-5.

كلُّ قيدٍ برمزه من `constraint_registry` (HC1، HC2…). والمرجعُ في الترميز `docs/schedule_v2/cpsat_model_reference.py`
والمواصفةُ `docs/schedule_v2/constraints_spec.html`؛ وما خالف المرجعَ منها مُعلَّلٌ في موضعه:

  · نواةٌ (لا تُحرَّر): HC1 HC2 HC9 HC12 HC13 HC19
  · قفلٌ إداريّ: HC4 (سقفُ الخميس بالخانات المقطوعة) HC6 (القسمة) HC10 (سقفُ فراغٍ شخصيّ)
  · افتراضاتٌ قابلةٌ للإيقاف بوسم: HC5 HC8 HC11 HC22
  · حمولةٌ: HC7 (`MAX_SAME_PERIOD`) وسقفُ اليوم (HC16، والتفضيلُ الشخصيّ) والتفريغات (TeacherExemption)

معرّفاتٌ لا أسماء، وقراءةُ السياسة مرّةً واحدةً في `ModelOptions` — لا استعلامَ هنا.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from operations.scheduler_constraints import DEFAULT_MAX_DAILY, MAX_SAME_PERIOD

if TYPE_CHECKING:
    from operations.cpsat_adapter import CpSatInputs, DemandRow

    from .model import BuiltModel

DAYS = range(5)


class _Ctx:
    """فهارسُ البناء — تُحسب مرّةً وتُشارَك بين دوالّ القيود."""

    def __init__(self, built: BuiltModel):
        self.b = built
        self.m = built.model
        self.inp = built.inputs
        self.opt = built.options
        self.rows = built.inputs.demand
        self.doubles = built.inputs.doubles
        #: متغيّرُ الكتلة لكلّ زوجِ خانتين متلاصقتين (فهرسا المتغيّرين) — الإعفاءُ الوحيدُ من HC5/HC20.
        self.pairvar: dict[tuple[int, int], object] = {}
        #: كلُّ الخانات المرشّحة قبل التفريغ (لتحديد «الأخيرة» الحقيقيّة للمعلّم) ثمّ المتاحة بعده.
        self.all_periods: dict[tuple[str, int], int] = {}
        self.by_t: dict[str, list[int]] = defaultdict(list)
        self.by_cls: dict[str, list[int]] = defaultdict(list)
        for i, r in enumerate(self.rows):
            self.by_t[r.teacher].append(i)
            self.by_cls[r.cls].append(i)

    def count(self, code: str, n: int = 1) -> None:
        self.b.constraint_counts[code] += n

    def time_of(self, cls: str, day: int, period: int) -> tuple[int, int] | None:
        key = f"{self.inp.class_band.get(cls, '')}|{'thursday' if day == 4 else 'regular'}"
        return self.inp.times.get(key, {}).get(period)


def _add(ctx: _Ctx, code: str, ct) -> None:
    if ctx.opt.name_constraints:
        ct.WithName(code)
    ctx.count(code)


# ───────────────────────── المتغيّرات والتفريغات ─────────────────────────


def _create_vars(ctx: _Ctx) -> None:
    b, inp = ctx.b, ctx.inp
    cut_ex = 0
    for i, r in enumerate(ctx.rows):
        for day in DAYS:
            ps = inp.periods(r.cls, day)
            #: سقفُ الخميس (HC4) داخل `periods` — يُحصى ما قُطع منه للتشخيص.
            band = inp.class_band.get(r.cls, "")
            full = inp.bell.get(f"{band}|{'thursday' if day == 4 else 'regular'}", {}).get(
                "periods", []
            )
            b.notes["HC4_cut_cells"] = b.notes.get("HC4_cut_cells", 0) + (len(full) - len(ps))
            if ps:
                key = (r.teacher, day)
                ctx.all_periods[key] = max(ctx.all_periods.get(key, 0), max(ps))
            for p in ps:
                if (r.teacher, day) in inp.ex_full or (r.teacher, day, p) in inp.ex_period:
                    cut_ex += 1
                    continue
                b.x[i, day, p] = ctx.m.NewBoolVar("")
    b.notes["exempt_cut_cells"] = cut_ex


def _demand_totals(ctx: _Ctx) -> None:
    """مجموعُ حصص كلّ صفٍّ = n (يلزم وضعُها كلُّها: النقصُ استحالةٌ لا تساهل)."""
    by_row: dict[int, list] = defaultdict(list)
    for (i, _d, _p), v in ctx.b.x.items():
        by_row[i].append(v)
    for i, r in enumerate(ctx.rows):
        ctx.m.Add(sum(by_row.get(i, [])) == r.n)
        ctx.count("DEMAND")


def _joint(ctx: _Ctx) -> dict[int, int]:
    """المهامُّ المنقسمة والمجموعاتُ المتوازية: أعضاؤها صفوفٌ تُوضع معاً في الخانة نفسها. يُرجع {صفٌّ ← ممثّلُ مهمّته}."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(ctx.rows):
        # المتوازيةُ مهمّةٌ واحدةٌ بأعضاءٍ كلّهم في الخانة نفسها (كما يبنيها `build_tasks` ويطابقها المُقيِّم).
        key = r.joint or (f"pg|{r.cls}|{r.elec}" if r.elec else "")
        if key:
            groups[key].append(i)
    rep_of: dict[int, int] = {}
    for members in groups.values():
        rep = members[0]
        for j in members:
            rep_of[j] = rep
        for j in members[1:]:
            cells = {(d, p) for (i, d, p) in ctx.b.x if i in (rep, j)}
            for d, p in cells:
                a, c = ctx.b.x.get((rep, d, p)), ctx.b.x.get((j, d, p))
                if a is not None and c is not None:
                    ctx.m.Add(a == c)
                elif a is not None:
                    ctx.m.Add(a == 0)
                elif c is not None:
                    ctx.m.Add(c == 0)
                else:
                    continue
                ctx.count("JOINT")
    return rep_of


# ───────────────────────── HC2: الشعبة والمجموعات الاختياريّة ─────────────────────────


def _class_conflict(ctx: _Ctx, rep_of: dict[int, int]) -> None:
    x = ctx.b.x
    for cls, idxs in ctx.by_cls.items():
        #: أعضاءُ المهمّة المنقسمة تتساوى متغيّراتُهم: يُعدّ ممثّلُها وحدَه.
        live = [i for i in idxs if rep_of.get(i, i) == i]
        groups = sorted({ctx.rows[i].elec for i in live})
        for day in DAYS:
            for p in ctx.inp.periods(cls, day):
                plain = [x[i, day, p] for i in live if ctx.rows[i].elec == "" and (i, day, p) in x]
                if len(plain) > 1:
                    ctx.m.Add(sum(plain) <= 1)
                    ctx.count("HC2")
                for g in groups:
                    if not g:
                        continue
                    gv = [x[i, day, p] for i in live if ctx.rows[i].elec == g and (i, day, p) in x]
                    if len(gv) > 1:
                        ctx.m.Add(sum(gv) <= 1)
                        ctx.count("HC2")
                    if gv and plain:
                        ctx.m.Add(sum(plain) + sum(gv) <= 1)
                        ctx.count("HC2")
                # المُقيِّم الرسميّ (load_grid/build_tasks) يرفض مجموعتين مختلفتين في خانةٍ واحدةٍ لشعبة:
                # البصمةُ اتحادٌ لا تطابق مهمّةً فتصير orphan_cells. فخانةُ الشعبة تحمل مهمّةً واحدةً أياً كان نوعها.
                every = [x[i, day, p] for i in live if (i, day, p) in x]
                if len(groups) > 1 and len(every) > 1:
                    ctx.m.Add(sum(every) <= 1)
                    ctx.count("HC2")


# ───────────────────────── HC19 والمزدوجات، HC7، HC6 ─────────────────────────


def _per_row(ctx: _Ctx) -> None:
    x = ctx.b.x
    cells: dict[int, dict[int, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    for i, d, p in x:
        cells[i][d].append((d, p))
    for i, r in enumerate(ctx.rows):
        is_double = r.blocks > 0
        days_avail = [d for d in DAYS if cells[i].get(d)]
        n_days = len(days_avail)
        # HC6: القسمةُ على الأيّام المتاحة لا الخمسةِ المحفورة (AS-3: المنصّةُ تحسب available_days).
        if n_days:
            cap = max(1, math.ceil(r.n / n_days))
            if is_double:
                cap = max(cap, 2)
            lo = 0 if is_double or not ctx.opt.even_spread else r.n // n_days
            for d in days_avail:
                vs = [x[i, d, p] for (_d, p) in cells[i][d]]
                if len(vs) > cap:
                    ctx.m.Add(sum(vs) <= cap)
                    ctx.count("HC6")
                if lo:
                    ctx.m.Add(sum(vs) >= lo)
                    ctx.count("HC6")
        # HC7: المادّةُ لا تتكدّس في حصّةٍ واحدةٍ من اليوم (≤ MAX_SAME_PERIOD أسبوعيّاً).
        byp: dict[int, list] = defaultdict(list)
        for (ii, d, p), v in x.items():
            if ii == i:
                byp[p].append(v)
        for vs in byp.values():
            if len(vs) > MAX_SAME_PERIOD:
                ctx.m.Add(sum(vs) <= MAX_SAME_PERIOD)
                ctx.count("HC7")
        # HC19: المزدوجةُ كتلةٌ صلبة — بالضبط `blocks` كتلةً، كلٌّ حصّتان متلاصقتان بلا فسحةٍ ولا صلاة.
        if is_double:
            ys: list = []
            row_pairs: set = set()
            for d in days_avail:
                ps = sorted(p for (_d, p) in cells[i][d])
                prev = None
                for p in ps:
                    if (i, d, p + 1) in x and _touching(ctx, r.cls, d, p, p + 1):
                        y = ctx.m.NewBoolVar("")
                        ctx.m.Add(y <= x[i, d, p])
                        ctx.m.Add(y <= x[i, d, p + 1])
                        if prev is not None:
                            ctx.m.Add(prev + y <= 1)
                        ctx.pairvar[x[i, d, p].Index(), x[i, d, p + 1].Index()] = y
                        ctx.b.vars[("blk", i, d, p)] = y
                        row_pairs.add((x[i, d, p].Index(), x[i, d, p + 1].Index()))
                        ys.append(y)
                        prev = y
                    else:
                        prev = None
            ctx.m.Add(sum(ys) == r.blocks)
            ctx.count("HC19")
            if r.n == 2 * r.blocks:
                # كلُّ حصصه كتلٌ (لا مفردة): الخانةُ مشغولةٌ ⇔ داخلَ كتلة — تقويةٌ للصياغة تُسرّع الحلّ.
                cover: dict[int, list] = defaultdict(list)
                for (ia, ib), y in ((k, v) for k, v in ctx.pairvar.items() if k in row_pairs):
                    cover[ia].append(y)
                    cover[ib].append(y)
                for d in days_avail:
                    for _d, p in cells[i][d]:
                        ctx.m.Add(x[i, d, p] == sum(cover.get(x[i, d, p].Index(), [])))


def _same_subject_rules(ctx: _Ctx) -> None:
    """HC20: حصّتا المادّة في اليوم لا تتجاوران (إلّا المزدوجةَ المعلَنة) · HC17: خميسُ 11 و12 حصّةٌ واحدةٌ للمادّة (المزدوجةُ كتلة)."""
    x = ctx.b.x
    grouped: dict[tuple[str, str, int], list[tuple[int, int, object]]] = defaultdict(list)
    for (i, d, p), v in x.items():
        r = ctx.rows[i]
        grouped[r.cls, r.subj, d].append((i, p, v))
    for (cls, subj, day), cells in grouped.items():
        double = any(ctx.rows[i].blocks > 0 for i, _p, _v in cells)
        if "HC20" not in ctx.opt.disabled:
            for a, (_ia, pa, va) in enumerate(cells):
                for _ib, pb, vb in cells[a + 1 :]:
                    if pa != pb and _touching(ctx, cls, day, pa, pb):
                        y = _pair(ctx, va, vb)
                        ctx.m.Add(va + vb <= (1 if y is None else 1 + y))
                        ctx.count("HC20")
        grade = ctx.opt.class_grade.get(cls) or getattr(ctx.inp, "class_grade", {}).get(cls)
        if (
            "HC17" not in ctx.opt.disabled
            and day == 4
            and grade in ctx.opt.thursday_pair_grades
            and len(cells) > 1
        ):
            ctx.m.Add(sum(v for _i, _p, v in cells) <= (2 if double else 1))
            ctx.count("HC17")


def _pair(ctx: _Ctx, a, b):
    """متغيّرُ كتلةٍ يجيز تلاصقَ المتغيّرين (أو None)."""
    y = ctx.pairvar.get((a.Index(), b.Index()))
    return y if y is not None else ctx.pairvar.get((b.Index(), a.Index()))


def _touching(ctx: _Ctx, cls: str, day: int, p1: int, p2: int) -> bool:
    t1, t2 = ctx.time_of(cls, day, p1), ctx.time_of(cls, day, p2)
    if not t1 or not t2:
        return abs(p1 - p2) == 1
    if t1[0] > t2[0]:
        t1, t2 = t2, t1
    return 0 <= t2[0] - t1[1] <= ctx.opt.joinable_gap


# ───────────────────────── المعلّم: HC1 HC12 HC13 HC5 HC10 HC16 HC8 HC22 ─────────────────────────


@dataclass
class _Cell:
    i: int
    p: int
    start: int
    end: int
    var: object


def _teacher_day_cells(ctx: _Ctx, t: str, day: int) -> list[_Cell]:
    out = []
    for i in ctx.by_t[t]:
        r = ctx.rows[i]
        for p in ctx.inp.periods(r.cls, day):
            v = ctx.b.x.get((i, day, p))
            if v is None:
                continue
            tm = ctx.time_of(r.cls, day, p)
            if tm is None:
                tm = (p * 1000, p * 1000 + 1)  # بلا جرسٍ مفهوم: فاصلٌ مستقلٌّ بحسب الرقم
            out.append(_Cell(i, p, tm[0], tm[1], v))
    return out


def _teachers(ctx: _Ctx) -> None:
    opt = ctx.opt
    for t, idxs in ctx.by_t.items():
        edges = _Edges()
        load = sum(ctx.rows[i].n for i in idxs)
        has_double = any(ctx.rows[i].blocks > 0 for i in idxs)
        days_t = [d for d in DAYS if _teacher_day_cells(ctx, t, d)]
        for day in days_t:
            _teacher_day(
                ctx, t, day, _teacher_day_cells(ctx, t, day), edges, load, has_double, len(days_t)
            )
        _edge_caps(ctx, t, edges, opt.enabled("HC22"), opt.enabled("HC8"))


@dataclass
class _Edges:
    first: dict[int, object] = field(default_factory=dict)
    last: dict[int, object] = field(default_factory=dict)
    last_by_cls: dict[str, list] = field(default_factory=lambda: defaultdict(list))


def _touch_rules(ctx: _Ctx, t, day: int, cells: list[_Cell], by_key, occ) -> None:
    """HC5 (أو تخفيفُه المعلَن) مع HC13 وقيد 6-7 وسقف التتابع، لمعلّمٍ في يوم."""
    opt, m = ctx.opt, ctx.m
    relaxed = t in opt.touch_relaxed and opt.enabled("HC5")
    _day_pairs(ctx, by_key, occ, opt.enabled("HC5") and not relaxed)
    if relaxed and day == 0:
        ctx.b.relaxations.append(
            {
                "teacher": t,
                "code": "HC5",
                "original": "no_touch",
                "relaxed": f"run_cap_{opt.touch_relaxed_run_cap}",
                "decision": "قرار المالك 2026-10-09",
            }
        )
    if opt.no_6_7:
        six = [c.var for c in cells if c.p == 6]
        seven = [c.var for c in cells if c.p == 7]
        if six and seven:
            m.Add(sum(six) + sum(seven) <= 1)
            ctx.count("NO_6_7")
    if relaxed:
        _band_transition(ctx, cells, day)
    if relaxed and opt.touch_relaxed_run_cap == 2:
        _no_triples(ctx, by_key, occ)


def _teacher_day(ctx, t, day, cells, edges, load, has_double, n_days) -> None:
    m, opt = ctx.m, ctx.opt
    pref = ctx.inp.prefs.get(t)
    # فواصلُ زمنيّةٌ متطابقةٌ ← HC1 (معلّمٌ واحدٌ لا يُدرّس شعبتين معاً) وتُعرَّف إشغالَ الفاصل.
    by_key: dict[tuple[int, int], list[_Cell]] = defaultdict(list)
    for c in cells:
        by_key[c.start, c.end].append(c)
    occ: dict[tuple[int, int], object] = {}
    for key, cs in sorted(by_key.items()):
        if len(cs) == 1:
            occ[key] = cs[0].var
        else:
            o = m.NewBoolVar("")
            m.Add(sum(c.var for c in cs) == o)
            ctx.count("HC1")
            occ[key] = o
        ctx.b.vars[("occ", t, day, key[0], key[1])] = occ[key]
    _touch_rules(ctx, t, day, cells, by_key, occ)
    if pref is not None and pref.max_gap is not None:
        _max_gap(ctx, t, day, by_key, occ, pref.max_gap)  # HC10: سقفُ الفراغ الشخصيّ
    # سقفُ اليوم: التفضيلُ الشخصيّ (أو الافتراضيّ 5) وHC16 المشتقّ.
    cap = pref.max_daily_periods if pref and pref.max_daily_periods else DEFAULT_MAX_DAILY
    code = "DAILY_CAP"  # يصير HC16 حين يُشتقّ من النصاب
    if opt.derived_day_cap and load:
        code = "HC16"
        cap = min(cap, math.ceil(load / n_days) + (1 if has_double else 0))
    if len(occ) > cap:
        m.Add(sum(occ.values()) <= cap)
        ctx.count(code)
    if code == "HC16" and has_double:
        _single_day_cap(ctx, cells, occ, math.ceil(load / n_days))
    _day_floor(ctx, occ, t, load, n_days)
    # الطرفان: أولى (HC22) وأخيرةٌ متاحةٌ للمعلّم في اليوم (HC8).
    fv = [c.var for c in cells if c.p == 1]
    last_p = ctx.all_periods.get((t, day), 0)
    lcells = [c for c in cells if c.p == last_p]
    if fv:
        edges.first[day] = _any(ctx, fv)
    if lcells:
        edges.last[day] = _any(ctx, [c.var for c in lcells])
        for c in lcells:
            edges.last_by_cls[ctx.rows[c.i].cls].append(c.var)


def _single_day_cap(ctx: _Ctx, cells: list[_Cell], occ, base: int) -> None:
    """HC16 كما يفحصه المُقيِّم: زيادةُ الحصّة على سقف القسمة للمزدوجة وحدَها؛ فيومٌ فيه حصّةٌ مفردةٌ لا يتجاوز السقف."""
    singles = [c.var for c in cells if ctx.rows[c.i].blocks == 0]
    if not singles:
        return
    has_single = _any(ctx, singles)
    ctx.m.Add(sum(occ.values()) + has_single <= base + 1)
    ctx.count("HC16")


def _feasible_floor(load: int, blocks: int, n_days: int, want: int, single_rows: int = 1) -> int:
    """أكبرُ أرضيّةٍ ≤ want يمكن للمعلّم بلوغها في كلّ يومٍ مع كتله ومفرداته (حسابٌ دقيقٌ بلا حلّال).

    اليومُ = 2×كتل + مفردات، والمفردةُ الواحدةُ من صفٍّ واحدٍ في اليوم (سقفُ HC6)، فاليومُ يحمل مفرداتٍ بعددِ
    الصفوفِ ذات المفردات على الأكثر. DP على الأيّام: أقلُّ كتلٍ تكفي لأرضيّةٍ v بتوزيعٍ ما للمفردات."""
    singles = load - 2 * blocks
    if singles < 0 or (singles and single_rows * n_days < singles):
        return 0
    for v in range(want, 0, -1):
        inf = blocks + 1
        dp = {0: 0}  # مفرداتٌ مُسكَنة ← أقلّ كتلٍ مستعملة
        for _ in range(n_days):
            nxt: dict[int, int] = {}
            for used, nb in dp.items():
                for s_d in range(0, min(single_rows, singles - used) + 1):
                    cost = nb + (max(0, v - s_d) + 1) // 2
                    if cost < nxt.get(used + s_d, inf):
                        nxt[used + s_d] = cost
            dp = nxt
        if dp.get(singles, inf) <= blocks:
            return v
    return 0


def _day_floor(ctx: _Ctx, occ, t: str, load: int, n_days: int) -> None:
    """HC14: لا يومَ فارغاً لتامّ النصاب (load ≥ أيّامه) · HC16B: لا يومَ دون ⌊النصاب÷الأيّام⌋ (احتياطٌ مسبقٌ لا فحصٌ بعديّ).

    D-286م: أرضيّةٌ لا تبلغها كتلُ المعلّم الصلبة (زوجيّةُ الكتل) تُخفَّف إلى الممكن وتُعلَن في `relaxations`؛ بلا كتلٍ لا يتغيّر شيء."""
    if not n_days:
        return
    total = sum(occ.values())
    blocks = sum(ctx.rows[i].blocks for i in ctx.by_t[t])
    single_rows = sum(1 for i in ctx.by_t[t] if ctx.rows[i].n - 2 * ctx.rows[i].blocks > 0)
    for code, want, active in (
        ("HC14", 1, load >= n_days),
        ("HC16B", load // n_days, load // n_days >= 1),
    ):
        if code in ctx.opt.disabled or not active:
            continue
        got = want if not blocks else _feasible_floor(load, blocks, n_days, want, single_rows)
        if got != want and not any(
            r["teacher"] == t and r["code"] == code for r in ctx.b.relaxations
        ):
            ctx.b.relaxations.append(
                {
                    "teacher": t,
                    "code": code,
                    "load": load,
                    "blocks": blocks,
                    "days": n_days,
                    "original": want,
                    "relaxed": got,
                }
            )
        if got >= 1:
            ctx.m.Add(total >= got)
            ctx.count(code)


def _day_pairs(ctx: _Ctx, by_key, occ, hc5: bool) -> None:
    """فاصلان مختلفان: تداخلٌ بالساعة (HC12) أو تماسٌّ (HC5/HC13)."""
    gap = ctx.opt.joinable_gap
    keys = sorted(by_key)
    for a, ka in enumerate(keys):
        for kb in keys[a + 1 :]:
            if kb[0] > ka[1] + gap:
                break  # مرتَّبةٌ بالبداية: ما بعدها أبعد
            if ka[1] > kb[0] and kb[1] > ka[0]:
                ctx.m.Add(occ[ka] + occ[kb] <= 1)
                ctx.count("HC12")
            elif 0 <= kb[0] - ka[1] <= gap:
                _touch_pair(ctx, by_key[ka], by_key[kb], occ[ka], occ[kb], hc5)


def _band_transition(ctx: _Ctx, cells: list[_Cell], day: int) -> None:
    """HC13 بعد تخفيف HC5: لا تماسَّ تامّاً (نهايةٌ = بداية) بين جرسين مختلفين في اليوم نفسه (المُقيِّم: same_bell)."""
    bells: dict[str, tuple] = {}

    def bell(cls: str) -> tuple:
        if cls not in bells:
            bells[cls] = tuple(ctx.time_of(cls, day, q) for q in range(1, 8))
        return bells[cls]

    for a in cells:
        for c in cells:
            if (
                a.end == c.start
                and a.i != c.i
                and bell(ctx.rows[a.i].cls) != bell(ctx.rows[c.i].cls)
            ):
                ctx.m.Add(a.var + c.var <= 1)
                ctx.count("HC13")


def _no_triples(ctx: _Ctx, by_key, occ) -> None:
    """بعد تخفيف HC5: حصتان متتاليتان مسموحتان، وثلاثٌ متتاليةٌ ممنوعة."""
    gap = ctx.opt.joinable_gap
    keys = sorted(by_key)
    touch = lambda a, b: 0 <= b[0] - a[1] <= gap  # noqa: E731
    for a, ka in enumerate(keys):
        for b in range(a + 1, len(keys)):
            if not touch(ka, keys[b]):
                continue
            for c in range(b + 1, len(keys)):
                if touch(keys[b], keys[c]):
                    ctx.m.Add(occ[ka] + occ[keys[b]] + occ[keys[c]] <= 2)
                    ctx.count("HC5")


def _any(ctx: _Ctx, vs: list):
    if len(vs) == 1:
        return vs[0]
    o = ctx.m.NewBoolVar("")
    ctx.m.AddMaxEquality(o, vs)
    return o


def _touch_pair(ctx: _Ctx, ca: list[_Cell], cb: list[_Cell], oa, ob, hc5: bool) -> None:
    """فاصلان متماسّان (فجوةٌ ≤ الحدّ): HC5 يمنع التلاصقَ إلّا مزدوجةً معلَنة؛ HC13 يمنعه بين طابقين ولو أُوقف HC5."""
    m = ctx.m
    floors = ctx.opt.band_floor
    code = "HC5" if hc5 else None
    if code is None and floors:
        # HC13 وحدَه: خاناتُ نطاقين بطابقين مختلفين فقط.
        for a in ca:
            for c in cb:
                fa = floors.get(ctx.inp.class_band.get(ctx.rows[a.i].cls, ""))
                fb = floors.get(ctx.inp.class_band.get(ctx.rows[c.i].cls, ""))
                if fa is not None and fb is not None and fa != fb:
                    m.Add(a.var + c.var <= 1)
                    ctx.count("HC13")
        return
    if code is None:
        return
    ys = {(a.var.Index(), c.var.Index()): _pair(ctx, a.var, c.var) for a in ca for c in cb}
    if not any(y is not None for y in ys.values()):
        m.Add(oa + ob <= 1)  # لا كتلةَ بين الفاصلين: قيدٌ واحدٌ على الإشغال
        ctx.count(code)
        return
    for a in ca:
        for c in cb:
            y = ys[a.var.Index(), c.var.Index()]
            m.Add(a.var + c.var <= (1 if y is None else 1 + y))
            ctx.count(code)


def _max_gap(ctx: _Ctx, t: str, day: int, by_key, occ, max_gap: int) -> None:
    """HC10: الفجواتُ بين أوّل حصّةٍ وآخرِها في اليوم ≤ سقفِ المعلّم (تُعدّ بالفواصل الزمنيّة)."""
    m = ctx.m
    keys = sorted(by_key)
    n = len(keys)
    if n <= max_gap + 1:
        return
    f = m.NewIntVar(0, n, "")
    l = m.NewIntVar(0, n, "")
    any_occ = m.NewBoolVar("")
    m.AddMaxEquality(any_occ, list(occ.values()))
    for idx, k in enumerate(keys):
        m.Add(f <= idx).OnlyEnforceIf(occ[k])
        m.Add(l >= idx).OnlyEnforceIf(occ[k])
    m.Add(l - f + 1 - sum(occ.values()) <= max_gap).OnlyEnforceIf(any_occ)
    ctx.count("HC10")


def _edge_caps(ctx: _Ctx, t, edges: _Edges, hc22: bool, hc8: bool) -> None:
    m, b = ctx.m, ctx.b
    if edges.first:
        f = m.NewIntVar(0, 5, "")
        m.Add(f == sum(edges.first.values()))
        b.vars[("first", t)] = f
        if hc22:
            cap = dict(ctx.opt.first_cap_override).get(t, ctx.opt.first_cap)
            m.Add(f <= cap)
            if cap != ctx.opt.first_cap:
                b.relaxations.append(
                    {
                        "teacher": t,
                        "code": "HC22",
                        "original": f"first_cap_{ctx.opt.first_cap}",
                        "relaxed": f"first_cap_{cap}",
                        "decision": "قرار المالك 2026-10-09",
                    }
                )
            ctx.count("HC22")
    if edges.last:
        l = m.NewIntVar(0, 5, "")
        m.Add(l == sum(edges.last.values()))
        b.vars[("last", t)] = l
        if hc8:
            m.Add(l <= ctx.opt.last_cap)
            ctx.count("HC8")
            # الشرطُ الثاني المستقلّ في HC8: الطرفان لا يقعان على شعبةٍ واحدة.
            for vs in edges.last_by_cls.values() if ctx.opt.last_distinct_class else ():
                if len(vs) > 1:
                    m.Add(sum(vs) <= 1)
                    ctx.count("HC8")


# ───────────────────────── HC9 و HC11: الموارد ─────────────────────────


def _resources(ctx: _Ctx) -> None:
    m, x = ctx.m, ctx.b.x
    for rid, cap in ctx.inp.res_cap.items():
        subs = ctx.inp.res_subjects.get(rid, frozenset())
        if not subs:
            continue
        rows = [i for i, r in enumerate(ctx.rows) if r.subj in subs]
        for day in DAYS:
            cells = []  # (start, end, var, level)
            for i in rows:
                r = ctx.rows[i]
                for p in ctx.inp.periods(r.cls, day):
                    v = x.get((i, day, p))
                    if v is None:
                        continue
                    tm = ctx.time_of(r.cls, day, p) or (p * 1000, p * 1000 + 1)
                    cells.append((tm[0], tm[1], v, ctx.inp.class_level.get(r.cls, ""), p))
            if not cells:
                continue
            if ctx.opt.resource_by == "period":
                groups = defaultdict(list)
                for c in cells:
                    groups[c[4]].append(c)
                points = list(groups.values())
            else:
                # أقصى تزامنٍ يقع عند بدايةِ فاصلٍ ما: يُفحص كلُّ بدايةٍ فريدة.
                points = [
                    [c for c in cells if c[0] <= s < c[1]] for s in sorted({c[0] for c in cells})
                ]
            seen = set()
            for grp in points:
                sig = tuple(sorted(id(c[2]) for c in grp))
                if sig in seen:
                    continue
                seen.add(sig)
                if len(grp) > cap:
                    m.Add(sum(c[2] for c in grp) <= cap)
                    ctx.count("HC9")
            # HC11 نصُّها ∀ r,d,p: بالحصّة لا بالساعة (قرارُ 2026-09-03)؛ مرحلتان في الخانة الرقميّة نفسِها ممنوعتان.
            if ctx.opt.enabled("HC11"):
                by_period = defaultdict(list)
                for c in cells:
                    by_period[c[4]].append(c)
                for grp in by_period.values():
                    levels = defaultdict(list)
                    for c in grp:
                        levels[c[3]].append(c[2])
                    if len(levels) > 1:
                        marks = []
                        for vs in levels.values():
                            mk = ctx.m.NewBoolVar("")
                            for v in vs:
                                m.Add(v <= mk)
                            marks.append(mk)
                        m.Add(sum(marks) <= 1)
                        ctx.count("HC11")


def add_all(built: BuiltModel) -> None:
    ctx = _Ctx(built)
    _create_vars(ctx)
    _demand_totals(ctx)
    rep_of = _joint(ctx)
    _class_conflict(ctx, rep_of)
    _per_row(ctx)
    _same_subject_rules(ctx)
    _teachers(ctx)
    _resources(ctx)


# ───────────────────────── AS-1..AS-5: فحصُ الإسناد قبل التوليد ─────────────────────────

#: AS-6 منهجيّ لا يُرمَّز: رسالةُ النجاح «لم يُكتشف مانع» لا «الإسنادُ صالح» — فحصُ الجدوى يُثبت الاستحالة لا الإمكان.
AS6_SUCCESS_MESSAGE = "لم يُكتشف مانع"

REJECT, WARN = "reject", "warn"


@dataclass(frozen=True)
class AssignmentFinding:
    """نتيجةُ فحصٍ واحد — معرّفاتٌ لا أسماء. `governing` يُسمّي أيَّ السقفين حكم (AS-4/AS-5)."""

    code: str
    severity: str
    teacher_id: str = ""
    class_id: str = ""
    detail: dict | None = None


def max_independent_slots(intervals: list[tuple[int, int]], gap: int = 10) -> int:
    """أقصى مجموعةِ فواصلَ لا يتلاصق فيها عنصران (فجوةٌ > الحدّ) — جشعٌ بنهاية الفاصل (أمثلُ لفواصل زمنيّة)."""
    count, last_end = 0, None
    for s, e in sorted(set(intervals), key=lambda iv: (iv[1], iv[0])):
        if last_end is None or s - last_end > gap:
            count += 1
            last_end = e
    return count


def check_assignment(
    inputs: CpSatInputs, *, margin: int = 2, joinable_gap: int = 10
) -> list[AssignmentFinding]:
    """AS-1 (نطاقاتٌ متعدّدة بسعةٍ محسوبة) · AS-2 (متوازياتٌ بمعلّمين مختلفين) · AS-4/AS-5 (سقفٌ شخصيّ وبنيويّ، هامشٌ ≥ 2).

    AS-3 مسحوبٌ (أثرُ نموذج). AS-6 منهجيّ: عدمُ وجود نتائجَ يعني «لم يُكتشف مانع» لا «الإسنادُ صالح».
    """
    out: list[AssignmentFinding] = []
    rows = inputs.demand

    # AS-2: متوازيةٌ أو مهمّةٌ منقسمةٌ بمعلّمٍ مكرَّر (خرقٌ صامتٌ لا يراه HC1: التضاربُ داخل المهمّة).
    by_group: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_joint: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.elec:
            by_group[(r.cls, r.elec)].append(r.teacher)
        if r.joint:
            by_joint[r.joint].append(r.teacher)
    for (cls, _g), teachers in by_group.items():
        if len(set(teachers)) != len(teachers):
            out.append(AssignmentFinding("AS-2", REJECT, class_id=cls, detail={"scope": "group"}))
    for joint, teachers in by_joint.items():
        if len(set(teachers)) != len(teachers):
            cls = joint.split("|", 1)[0]
            out.append(AssignmentFinding("AS-2", REJECT, class_id=cls, detail={"scope": "joint"}))

    by_t: dict[str, list[DemandRow]] = defaultdict(list)
    for r in rows:
        by_t[r.teacher].append(r)
    for t, trows in by_t.items():
        load = sum(r.n for r in trows)
        bands = {inputs.class_band.get(r.cls, "") for r in trows}
        caps: list[int] = []
        for day in DAYS:
            if (t, day) in inputs.ex_full:
                caps.append(0)
                continue
            ivs = []
            for r in trows:
                for p in inputs.periods(r.cls, day):
                    if (t, day, p) in inputs.ex_period:
                        continue
                    key = f"{inputs.class_band.get(r.cls, '')}|{'thursday' if day == 4 else 'regular'}"
                    tm = inputs.times.get(key, {}).get(p)
                    if tm:
                        ivs.append(tm)
            caps.append(max_independent_slots(ivs, joinable_gap))
        structural = sum(caps)
        pref = inputs.prefs.get(t)
        personal = pref.max_daily_periods if pref and pref.max_daily_periods else None
        if personal is not None:
            personal_total = sum(min(personal, c) for c in caps)
        else:
            personal_total = structural
        effective = min(structural, personal_total)
        governing = "AS-4" if personal is not None and personal_total < structural else "AS-5"
        if load > effective:
            code = governing
            if governing == "AS-5" and len(bands) > 1:
                code = "AS-1"
            out.append(
                AssignmentFinding(
                    code,
                    REJECT,
                    teacher_id=t,
                    detail={
                        "load": load,
                        "structural_cap": structural,
                        "personal_cap": personal_total if personal is not None else None,
                        "bands": len(bands),
                        "governing": governing,
                    },
                )
            )
        elif load > effective - margin:
            out.append(
                AssignmentFinding(
                    "AS-5",
                    WARN,
                    teacher_id=t,
                    detail={"load": load, "effective_cap": effective, "margin": effective - load},
                )
            )
    return out


__all__ = [
    "AS6_SUCCESS_MESSAGE",
    "AssignmentFinding",
    "add_all",
    "check_assignment",
    "max_independent_slots",
]
