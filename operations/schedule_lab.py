"""مختبرُ جودة الجدول: ستّةَ عشرَ مؤشراً تقيس المعلّمَ والشعبةَ والمادّةَ والموارد.

رقمُ الجودة الواحد (`quality_score`) يقول «96» ولا يقول لماذا. فهنا كلُّ مؤشرٍ
باسمٍ وتعريفٍ ووحدةٍ واتّجاه، يُحسب من الحصص نفسها (يومٌ، رقمٌ، معلّمٌ، شعبةٌ،
مادّةٌ، نطاق) مع التفريغات والتفضيلات والموارد — لمسودّةٍ أو للجدول الحيّ —
ويُقارَن بأساسٍ مرجعيٍّ محفوظ. القائمةُ اعتُمدت في 2026-09-04.

    lab = ScheduleLab.for_generation(generation)     # أو .for_live(school, year)
    metrics = lab.compute()
    rows = compare(metrics, baseline_metrics)

المؤشرات (المعرّفات ثابتةٌ لأنّها تُخزَّن):
  validity.hard_conflicts / completeness / uncovered_days
  teacher.gap_weighted_avg / gap_weighted_max / compactness / run_avg /
          run_breaches / weekly_imbalance / transitions_avg / transitions_max
  fairness.edge_cv / stress_top / preference_satisfaction
  subject.pattern_match / same_period_max / heavy_morning / activity_afternoon
  class.heavy_streak_days / math_late
  resources.utilization / saturated_slots
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, pstdev

DAYS = (0, 1, 2, 3, 4)
LAST_PERIOD = 7
WEEK_SLOTS = len(DAYS) * LAST_PERIOD
#: النصفُ الأوّل من اليوم — للتوقيت التربويّ.
MORNING_LAST = 4
#: «متأخّرة» — السادسةُ والسابعة.
LATE_FROM = 6
#: أقلُّ نصابٍ يدخل به المعلّمُ مقاييسَ العدالة والتغطية.
MIN_LOAD = 5


@dataclass(frozen=True)
class Slot:
    teacher_id: str
    teacher_name: str
    class_id: str
    class_name: str
    subject_id: str
    subject_code: str
    pedagogy: str
    requires_double: bool
    day: int
    period: int
    band_id: str
    elective_group: str


@dataclass
class Context:
    """ما يُحتاج مع الحصص: التفريغات والتفضيلات والتوزيعات والموارد والجرس."""

    #: (معلّم، يوم، حصّة) المحجوبة — واليومُ الكاملُ سبعُ حصص.
    blocked: set = field(default_factory=set)
    #: معلّم ← أيّامُه المفرَّغةُ كاملاً.
    full_days: dict = field(default_factory=lambda: defaultdict(set))
    #: معلّم ← {max_daily, max_consecutive, max_gap, free_day}.
    preferences: dict = field(default_factory=dict)
    #: مجموعُ حصص التوزيعات (المطلوب).
    required_periods: int = 0
    #: (شعبة، مادّة) ← حصصُها الأسبوعيّة المطلوبة.
    weekly: dict = field(default_factory=dict)
    #: مورد ← (اسم، سعة، {مواد}).
    resources: dict = field(default_factory=dict)
    #: (نطاق، يوم، حصّة) ← (بداية، نهاية) — من `load_band_times`.
    bells: dict = field(default_factory=dict)
    #: السقفُ العامُّ للتتابع حين لا سقفَ شخصيّ.
    general_run_cap: int = 1
    #: مادّة ← طبيعتُها — لقياس الشبكة في الذاكرة حيث لا صفوفَ من القاعدة.
    subject_pedagogy: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# التحميل من القاعدة
# ══════════════════════════════════════════════════════════════════


def load_slots(queryset) -> list[Slot]:
    rows = queryset.select_related("teacher", "class_group", "subject").order_by(
        "day_of_week", "period_number"
    )
    return [
        Slot(
            teacher_id=str(r.teacher_id),
            teacher_name=r.teacher.full_name if r.teacher else "—",
            class_id=str(r.class_group_id),
            class_name=str(r.class_group),
            subject_id=str(r.subject_id or ""),
            subject_code=(r.subject.code or "") if r.subject else "",
            pedagogy=(r.subject.pedagogy or "regular") if r.subject else "regular",
            requires_double=bool(r.subject and r.subject.requires_double_period),
            day=r.day_of_week,
            period=r.period_number,
            band_id=str(r.class_group.time_band_id or ""),
            elective_group=(r.elective_group or ""),
        )
        for r in rows
    ]


def load_context(school, academic_year) -> Context:
    from operations.models import (
        SchedulingResource,
        SubjectClassAssignment,
        TeacherExemption,
        TeacherPreference,
    )
    from operations.scheduler import load_band_times
    from operations.scheduler_constraints import MAX_CONSECUTIVE

    ctx = Context(general_run_cap=MAX_CONSECUTIVE)
    for ex in TeacherExemption.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ):
        tid = str(ex.teacher_id)
        if ex.exemption_type == "full_day":
            ctx.full_days[tid].add(ex.day_of_week)
            for p in range(1, LAST_PERIOD + 1):
                ctx.blocked.add((tid, ex.day_of_week, p))
        elif ex.period_number:
            ctx.blocked.add((tid, ex.day_of_week, ex.period_number))
    for pref in TeacherPreference.objects.filter(school=school, academic_year=academic_year):
        ctx.preferences[str(pref.teacher_id)] = {
            "max_daily": pref.max_daily_periods,
            "max_consecutive": pref.max_consecutive,
            "max_gap": pref.max_gap,
            "free_day": pref.free_day,
        }
    for a in SubjectClassAssignment.objects.filter(
        school=school, academic_year=academic_year, is_active=True
    ):
        ctx.required_periods += a.weekly_periods
        ctx.weekly[(str(a.class_group_id), str(a.subject_id))] = a.weekly_periods
    for res in SchedulingResource.objects.filter(school=school, is_active=True).prefetch_related(
        "subjects"
    ):
        ctx.resources[str(res.id)] = (
            res.name,
            res.capacity,
            {str(s.id) for s in res.subjects.all()},
        )
    from operations.models import Subject

    ctx.subject_pedagogy = {
        str(sid): pedagogy or "regular"
        for sid, pedagogy in Subject.objects.filter(school=school).values_list("id", "pedagogy")
    }
    table = load_band_times(school)
    for (band, day_type), periods in table.items():
        for period, (start, end) in periods.items():
            ctx.bells[(band, day_type, period)] = (start, end)
    return ctx


def _interval(ctx: Context, band_id: str, day: int, period: int):
    day_type = "thursday" if day == 4 else "regular"
    for key in ((band_id, day_type), ("", day_type), (band_id, "regular"), ("", "regular")):
        hit = ctx.bells.get((key[0], key[1], period))
        if hit:
            return hit
    return None


def _same_bell(ctx: Context, a: str, b: str, day: int) -> bool:
    if a == b or not ctx.bells:
        return True
    return all(
        _interval(ctx, a, day, p) == _interval(ctx, b, day, p) for p in range(1, LAST_PERIOD + 1)
    )


# ══════════════════════════════════════════════════════════════════
# أدواتٌ صغيرة
# ══════════════════════════════════════════════════════════════════


def _gaps(periods: list[int]) -> list[int]:
    """أطوالُ الفراغات بين حصصٍ مرتّبة — بعدد الحصص الفارغة."""
    ordered = sorted(set(periods))
    return [later - earlier - 1 for earlier, later in zip(ordered, ordered[1:], strict=False)]


#: سياسةُ المدرسة (قرار الإدارة 2026-09-04): لا تلاصقَ بين حصّتين لمعلّم — راحتُه
#: مهمّة — والتجاورُ رخصةُ الضرورة القصوى. فالفراغُ الواحدُ بين حصّتين استراحةٌ
#: مقصودةٌ لا عيب، وما زاد عليه هو الفراغُ الذي يُعَدّ.
REST_GAP = 1


def excess_gap_weight(periods: list[int]) -> float:
    """Σ (طول الفراغ − استراحة)² لما فوق الاستراحة، ÷ عدد حصص اليوم."""
    distinct = set(periods)
    if not distinct:
        return 0.0
    return sum((g - REST_GAP) ** 2 for g in _gaps(periods) if g > REST_GAP) / len(distinct)


def alternating_compactness(periods: list[int]) -> float:
    """طولُ اليوم مقابل النمط المتناوب المثاليّ (1، 3، 5): 1.0 مثاليّ، ولا يُكافأ التلاصق."""
    distinct = sorted(set(periods))
    if len(distinct) < 2:
        return 1.0
    ideal_span = 2 * len(distinct) - 1
    return max(1.0, (distinct[-1] - distinct[0] + 1) / ideal_span)


def _longest_run(periods: list[int]) -> int:
    ordered = sorted(set(periods))
    best = run = 1 if ordered else 0
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        run = run + 1 if later == earlier + 1 else 1
        best = max(best, run)
    return best


def _cv(values: list[float]) -> float:
    if not values or mean(values) == 0:
        return 0.0
    return round(pstdev(values) / mean(values), 3)


def _round(x: float | None, digits: int = 2):
    return None if x is None else round(x, digits)


def ideal_pattern(weekly: int, requires_double: bool, days: int = 5) -> list[int]:
    """نمطُ الأيّام المثاليُّ لمادّةٍ في شعبة — مرتّباً تنازليّاً.

    5 = 1-1-1-1-1، و6 = 2-1-1-1-1، و7 = 2-2-1-1-1 (قرار 2026-09-04). والمزدوجةُ
    المطلوبةُ حصّتان في يومٍ واحد: 2 = [2]، و4 = [2, 2].
    """
    if weekly <= 0:
        return []
    if requires_double and weekly % 2 == 0:
        return [2] * (weekly // 2)
    base, extra = divmod(weekly, days)
    pattern = [base + 1] * extra + [base] * (days - extra)
    return [n for n in pattern if n > 0]


# ══════════════════════════════════════════════════════════════════
# الحساب
# ══════════════════════════════════════════════════════════════════


class ScheduleLab:
    def __init__(self, slots: list[Slot], ctx: Context):
        self.slots = slots
        self.ctx = ctx
        self.by_teacher_day: dict[str, dict[int, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.by_teacher_day_bands: dict[str, dict[int, list[tuple[int, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.names: dict[str, str] = {}
        self.load: dict[str, int] = defaultdict(int)
        self.placements: dict[str, float] = defaultdict(float)
        for s in slots:
            self.by_teacher_day[s.teacher_id][s.day].append(s.period)
            self.by_teacher_day_bands[s.teacher_id][s.day].append((s.period, s.band_id))
            self.names[s.teacher_id] = s.teacher_name
            self.load[s.teacher_id] += 1
            self.placements[s.teacher_id] += 0.5 if s.requires_double else 1.0

    # ── مصانع ──
    @classmethod
    def for_generation(cls, generation) -> ScheduleLab:
        from operations.models import ScheduleSlot

        return cls(
            load_slots(ScheduleSlot.objects.filter(generation=generation)),
            load_context(generation.school, generation.academic_year),
        )

    @classmethod
    def for_live(cls, school, academic_year) -> ScheduleLab:
        from operations.models import ScheduleSlot

        return cls(
            load_slots(
                ScheduleSlot.objects.filter(
                    school=school, academic_year=academic_year, is_active=True
                )
            ),
            load_context(school, academic_year),
        )

    def available_days(self, tid: str) -> list[int]:
        return [d for d in DAYS if d not in self.ctx.full_days.get(tid, ())]

    def run_cap(self, tid: str) -> int:
        pref = self.ctx.preferences.get(tid)
        return (pref or {}).get("max_consecutive") or self.ctx.general_run_cap

    # ── أ. الصلاحية ──
    def hard_conflicts(self) -> dict:
        teacher_at: dict[tuple[str, int, int], int] = defaultdict(int)
        class_at: dict[tuple[str, int, int], list[str]] = defaultdict(list)
        resource_at: dict[tuple[str, int, int], int] = defaultdict(int)
        exemption_hits = 0
        for s in self.slots:
            teacher_at[(s.teacher_id, s.day, s.period)] += 1
            class_at[(s.class_id, s.day, s.period)].append(s.elective_group)
            if (s.teacher_id, s.day, s.period) in self.ctx.blocked:
                exemption_hits += 1
            for rid, (_name, _cap, subjects) in self.ctx.resources.items():
                if s.subject_id in subjects:
                    resource_at[(rid, s.day, s.period)] += 1
        teacher_double = sum(1 for n in teacher_at.values() if n > 1)
        class_double = sum(
            1 for groups in class_at.values() if len(groups) > 1 and any(g == "" for g in groups)
        )
        overlaps = touches = 0
        for tid, days in self.by_teacher_day_bands.items():
            for day, items in days.items():
                spans = []
                for period, band in items:
                    iv = _interval(self.ctx, band, day, period)
                    if iv:
                        spans.append((iv[0], iv[1], band))
                spans.sort()
                for (s1, e1, b1), (s2, e2, b2) in zip(spans, spans[1:], strict=False):
                    if (s1, e1) == (s2, e2):
                        continue
                    if s2 < e1:
                        overlaps += 1
                    elif s2 == e1 and b1 != b2 and not _same_bell(self.ctx, b1, b2, day):
                        touches += 1
        resource_over = sum(
            1 for (rid, _d, _p), n in resource_at.items() if n > self.ctx.resources[rid][1]
        )
        parts = {
            "teacher_double_booked": teacher_double,
            "class_double_booked": class_double,
            "clock_overlaps": overlaps,
            "cross_floor_touches": touches,
            "exemption_breaches": exemption_hits,
            "resource_over_capacity": resource_over,
        }
        return {"value": sum(parts.values()), "detail": parts}

    def completeness(self) -> dict:
        required = self.ctx.required_periods or len(self.slots)
        return {
            "value": _round(100 * len(self.slots) / required, 1) if required else 100.0,
            "detail": {"placed": len(self.slots), "required": required},
        }

    def uncovered_days(self) -> dict:
        found = []
        for tid, days in self.by_teacher_day.items():
            available = self.available_days(tid)
            if self.placements[tid] < len(available):
                continue
            empty = [d for d in available if not days.get(d)]
            if empty:
                found.append((self.names[tid], empty))
        return {"value": len(found), "detail": dict(found[:10])}

    # ── ب. يوم المعلّم ──
    def gaps(self) -> tuple[dict, dict]:
        per_teacher: dict[str, list[float]] = defaultdict(list)
        worst = (0.0, "", -1)
        for tid, days in self.by_teacher_day.items():
            for day, periods in days.items():
                weighted = excess_gap_weight(periods)
                per_teacher[tid].append(weighted)
                if weighted > worst[0]:
                    worst = (weighted, self.names[tid], day)
        averages = {tid: mean(v) for tid, v in per_teacher.items() if v}
        top = sorted(averages.items(), key=lambda kv: -kv[1])[:3]
        avg = {
            "value": _round(mean(averages.values()) if averages else 0.0),
            "detail": {self.names[t]: _round(v) for t, v in top},
        }
        mx = {"value": _round(worst[0]), "detail": {"teacher": worst[1], "day": worst[2]}}
        return avg, mx

    def compactness(self) -> dict:
        ratios = []
        for days in self.by_teacher_day.values():
            for periods in days.values():
                if len(set(periods)) >= 2:
                    ratios.append(alternating_compactness(periods))
        return {"value": _round(mean(ratios) if ratios else 1.0), "detail": {"days": len(ratios)}}

    def runs(self) -> tuple[dict, dict]:
        longest, breaches = [], []
        for tid, days in self.by_teacher_day.items():
            cap = self.run_cap(tid)
            for day, periods in days.items():
                run = _longest_run(periods)
                longest.append(run)
                if run > cap:
                    breaches.append((self.names[tid], day, run))
        return (
            {"value": _round(mean(longest) if longest else 0.0), "detail": {}},
            {"value": len(breaches), "detail": {f"{n} — يوم {d}": r for n, d, r in breaches[:10]}},
        )

    def weekly_imbalance(self) -> dict:
        devs = {}
        for tid, days in self.by_teacher_day.items():
            if self.load[tid] < MIN_LOAD:
                continue
            counts = [len(set(days.get(d, []))) for d in self.available_days(tid)]
            if len(counts) >= 2:
                devs[tid] = pstdev(counts)
        top = sorted(devs.items(), key=lambda kv: -kv[1])[:3]
        return {
            "value": _round(mean(devs.values()) if devs else 0.0),
            "detail": {self.names[t]: _round(v) for t, v in top},
        }

    def transitions(self) -> tuple[dict, dict]:
        per_day = []
        worst = (0, "", -1)
        for tid, days in self.by_teacher_day_bands.items():
            for day, items in days.items():
                ordered = sorted(items)
                count = 0
                for (_p1, b1), (_p2, b2) in zip(ordered, ordered[1:], strict=False):
                    if b1 != b2 and not _same_bell(self.ctx, b1, b2, day):
                        count += 1
                per_day.append(count)
                if count > worst[0]:
                    worst = (count, self.names[tid], day)
        return (
            {"value": _round(mean(per_day) if per_day else 0.0), "detail": {}},
            {"value": worst[0], "detail": {"teacher": worst[1], "day": worst[2]}},
        )

    # ── ج. العدالة ──
    def edge_fairness(self) -> dict:
        ratios = {}
        for tid, days in self.by_teacher_day.items():
            if self.load[tid] < MIN_LOAD:
                continue
            edges = sum(1 for ps in days.values() for p in ps if p in (1, LAST_PERIOD))
            ratios[tid] = edges / self.load[tid]
        top = sorted(ratios.items(), key=lambda kv: -kv[1])[:3]
        return {
            "value": _cv(list(ratios.values())),
            "detail": {self.names[t]: _round(v) for t, v in top},
        }

    def stress(self) -> dict:
        scores = {}
        for tid, days in self.by_teacher_day.items():
            if self.load[tid] < MIN_LOAD:
                continue
            cap = self.run_cap(tid)
            gap_w = sum(excess_gap_weight(ps) for ps in days.values() if ps)
            edges = sum(1 for ps in days.values() for p in ps if p in (1, LAST_PERIOD))
            breaches = sum(1 for ps in days.values() if _longest_run(ps) > cap)
            counts = [len(set(days.get(d, []))) for d in self.available_days(tid)]
            imbalance = pstdev(counts) if len(counts) >= 2 else 0.0
            scores[tid] = (gap_w + edges + breaches + imbalance) / self.load[tid]
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:5]
        return {
            "value": _round(mean(scores.values()) if scores else 0.0, 3),
            "detail": {self.names[t]: _round(v, 3) for t, v in top},
        }

    def preference_satisfaction(self) -> dict:
        checks = met = 0
        misses: dict[str, list[str]] = defaultdict(list)
        for tid, pref in self.ctx.preferences.items():
            days = self.by_teacher_day.get(tid, {})
            if not days:
                continue
            name = self.names.get(tid, tid)
            checks += 1
            if all(len(set(ps)) <= pref["max_daily"] for ps in days.values()):
                met += 1
            else:
                misses[name].append("السقف اليومي")
            checks += 1
            if all(_longest_run(ps) <= (pref["max_consecutive"] or 99) for ps in days.values()):
                met += 1
            else:
                misses[name].append("التتالي")
            if pref["max_gap"] is not None:
                checks += 1
                if all(max(_gaps(ps), default=0) <= pref["max_gap"] for ps in days.values()):
                    met += 1
                else:
                    misses[name].append("الفراغ")
            if pref["free_day"] is not None:
                checks += 1
                if not days.get(pref["free_day"]):
                    met += 1
                else:
                    misses[name].append("يوم التفريغ المفضّل")
        return {
            "value": _round(100 * met / checks, 1) if checks else None,
            "detail": {n: "، ".join(m) for n, m in list(misses.items())[:10]},
        }

    # ── د. الشعبة والمادّة ──
    def subject_patterns(self) -> tuple[dict, dict]:
        by_pair: dict[tuple[str, str], dict[int, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        doubles: dict[tuple[str, str], bool] = {}
        for s in self.slots:
            by_pair[(s.class_id, s.subject_id)][s.day].append(s.period)
            doubles[(s.class_id, s.subject_id)] = s.requires_double
        matches, worst_same, same_max = [], [], []
        for pair, days in by_pair.items():
            weekly = sum(len(ps) for ps in days.values())
            ideal = ideal_pattern(weekly, doubles[pair])
            actual = sorted((len(ps) for ps in days.values()), reverse=True)
            actual += [0] * (len(ideal) - len(actual))
            ideal += [0] * (len(actual) - len(ideal))
            deviation = sum(abs(a - i) for a, i in zip(actual, ideal, strict=True)) / 2
            matches.append(1 - deviation / weekly if weekly else 1.0)
            counts = defaultdict(int)
            for ps in days.values():
                for p in ps:
                    counts[p] += 1
            top = max(counts.values()) if counts else 0
            same_max.append(top)
            if top >= 3:
                worst_same.append((pair, top))
        return (
            {"value": _round(100 * mean(matches), 1) if matches else 100.0, "detail": {}},
            {
                "value": _round(mean(same_max)) if same_max else 0.0,
                "detail": {"pairs_at_3_or_more": len(worst_same)},
            },
        )

    def doubles_on_thursday(self) -> dict:
        """(شعبة، مادّة) لها حصّتان أو أكثر يومَ الخميس — والمزدوجةُ المطلوبةُ مستثناة (HC15)."""
        counts: dict[tuple[str, str], int] = defaultdict(int)
        doubles: dict[tuple[str, str], bool] = {}
        names: dict[tuple[str, str], str] = {}
        for s in self.slots:
            if s.day != 4:
                continue
            key = (s.class_id, s.subject_id)
            counts[key] += 1
            doubles[key] = s.requires_double
            names[key] = f"{s.class_name} — {s.subject_code or s.subject_id[:6]}"
        hits = [names[k] for k, n in counts.items() if n >= 2 and not doubles[k]]
        return {"value": len(hits), "detail": {h: 2 for h in hits[:10]}}

    def pedagogy_timing(self) -> tuple[dict, dict]:
        heavy = [s for s in self.slots if s.pedagogy == "heavy"]
        activity = [s for s in self.slots if s.pedagogy == "activity"]
        heavy_morning = (
            _round(100 * sum(1 for s in heavy if s.period <= MORNING_LAST) / len(heavy), 1)
            if heavy
            else None
        )
        activity_pm = (
            _round(100 * sum(1 for s in activity if s.period > MORNING_LAST) / len(activity), 1)
            if activity
            else None
        )
        return (
            {"value": heavy_morning, "detail": {"heavy_periods": len(heavy)}},
            {"value": activity_pm, "detail": {"activity_periods": len(activity)}},
        )

    def class_pressure(self) -> tuple[dict, dict]:
        by_class_day: dict[tuple[str, int], dict[int, str]] = defaultdict(dict)
        maths_total = maths_late = 0
        for s in self.slots:
            by_class_day[(s.class_id, s.day)][s.period] = s.pedagogy
            if s.subject_code == "MAT":
                maths_total += 1
                maths_late += s.period >= LATE_FROM
        streak_days = 0
        for cells in by_class_day.values():
            run = 0
            hit = False
            for p in range(1, LAST_PERIOD + 1):
                run = run + 1 if cells.get(p) == "heavy" else 0
                if run >= 3:
                    hit = True
            streak_days += hit
        return (
            {"value": streak_days, "detail": {}},
            {
                "value": _round(100 * maths_late / maths_total, 1) if maths_total else None,
                "detail": {"maths_periods": maths_total},
            },
        )

    # ── هـ. الموارد ──
    def resources(self) -> tuple[dict, dict]:
        usage: dict[str, dict[tuple[int, int], int]] = defaultdict(lambda: defaultdict(int))
        for s in self.slots:
            for rid, (_n, _c, subjects) in self.ctx.resources.items():
                if s.subject_id in subjects:
                    usage[rid][(s.day, s.period)] += 1
        util, saturated = {}, 0
        for rid, (name, capacity, _s) in self.ctx.resources.items():
            used = sum(usage[rid].values())
            util[name] = _round(100 * used / (capacity * WEEK_SLOTS), 1) if capacity else None
            saturated += sum(1 for n in usage[rid].values() if n >= capacity)
        return (
            {
                "value": _round(mean(v for v in util.values() if v is not None), 1)
                if util
                else None,
                "detail": util,
            },
            {"value": saturated, "detail": {}},
        )

    # ── الكلّ ──
    def compute(self) -> dict:
        gap_avg, gap_max = self.gaps()
        run_avg, run_breaches = self.runs()
        tr_avg, tr_max = self.transitions()
        pattern, same_period = self.subject_patterns()
        heavy_am, activity_pm = self.pedagogy_timing()
        streaks, maths_late = self.class_pressure()
        res_util, res_sat = self.resources()
        metrics = {
            "validity.hard_conflicts": self.hard_conflicts(),
            "validity.completeness": self.completeness(),
            "validity.uncovered_days": self.uncovered_days(),
            "teacher.gap_weighted_avg": gap_avg,
            "teacher.gap_weighted_max": gap_max,
            "teacher.compactness": self.compactness(),
            "teacher.run_avg": run_avg,
            "teacher.run_breaches": run_breaches,
            "teacher.weekly_imbalance": self.weekly_imbalance(),
            "teacher.transitions_avg": tr_avg,
            "teacher.transitions_max": tr_max,
            "fairness.edge_cv": self.edge_fairness(),
            "fairness.stress": self.stress(),
            "fairness.preference_satisfaction": self.preference_satisfaction(),
            "subject.pattern_match": pattern,
            "subject.same_period_max": same_period,
            "subject.double_on_thursday": self.doubles_on_thursday(),
            "subject.heavy_morning": heavy_am,
            "subject.activity_afternoon": activity_pm,
            "class.heavy_streak_days": streaks,
            "class.maths_late": maths_late,
            "resources.utilization": res_util,
            "resources.saturated_slots": res_sat,
        }
        metrics["_meta"] = {"slots": len(self.slots), "teachers": len(self.by_teacher_day)}
        return metrics


# ══════════════════════════════════════════════════════════════════
# التعريفات والمقارنة
# ══════════════════════════════════════════════════════════════════

#: معرّف ← (الاسم، الوحدة، الاتّجاه الأفضل: low/high/zero)
CATALOG: dict[str, tuple[str, str, str]] = {
    "validity.hard_conflicts": ("تعارضات صلبة", "عدد", "zero"),
    "validity.completeness": ("اكتمال النصاب", "%", "high"),
    "validity.uncovered_days": ("معلّمون لهم يوم فارغ بلا تفريغ", "عدد", "zero"),
    "teacher.gap_weighted_avg": ("الفراغ الزائد عن الاستراحة (متوسّط)", "رقم", "low"),
    "teacher.gap_weighted_max": ("الفراغ الزائد عن الاستراحة (أقصى يوم)", "رقم", "low"),
    "teacher.compactness": ("تراصّ اليوم مقابل التناوب", "نسبة", "low"),
    "teacher.run_avg": ("أطول تتابع (متوسّط)", "حصص", "low"),
    "teacher.run_breaches": ("أيام فيها تلاصق مخالف", "عدد", "low"),
    "teacher.weekly_imbalance": ("تفاوت حصص الأيام (انحراف)", "رقم", "low"),
    "teacher.transitions_avg": ("انتقالات الطابقين (متوسّط اليوم)", "عدد", "low"),
    "teacher.transitions_max": ("انتقالات الطابقين (أقصى يوم)", "عدد", "low"),
    "fairness.edge_cv": ("عدالة الأولى والسابعة (معامل اختلاف)", "نسبة", "low"),
    "fairness.stress": ("ضغط المعلّم (متوسّط)", "رقم", "low"),
    "fairness.preference_satisfaction": ("تلبية التفضيلات", "%", "high"),
    "subject.pattern_match": ("توزيع المادّة على الأسبوع", "% مطابقة", "high"),
    "subject.same_period_max": ("تكرار الحصّة نفسها للمادّة (متوسّط الأقصى)", "عدد", "low"),
    "subject.double_on_thursday": ("موادّ لها حصّتان يوم الخميس", "عدد", "zero"),
    "subject.heavy_morning": ("الموادّ الثقيلة في النصف الأوّل", "%", "high"),
    "subject.activity_afternoon": ("موادّ النشاط في النصف الثاني", "%", "high"),
    "class.heavy_streak_days": ("أيام فيها ثلاث ثقيلات متتالية", "عدد", "low"),
    "class.maths_late": ("الرياضيات في السادسة والسابعة", "%", "low"),
    "resources.utilization": ("إشغال الموارد", "%", "info"),
    "resources.saturated_slots": ("خانات بلغت فيها الموارد سعتها", "عدد", "low"),
}


def compare(current: dict, baseline: dict | None) -> list[dict]:
    """صفوفٌ للعرض: كلُّ مؤشرٍ بقيمته وقيمة الأساس والفرق وحكمِ الاتّجاه."""
    rows = []
    for key, (label, unit, better) in CATALOG.items():
        cur = (current or {}).get(key, {}).get("value")
        base = (baseline or {}).get(key, {}).get("value") if baseline else None
        delta = None
        if isinstance(cur, int | float) and isinstance(base, int | float):
            delta = round(cur - base, 3)
        verdict = ""
        if delta is not None and delta != 0 and better != "info":
            improved = delta < 0 if better in ("low", "zero") else delta > 0
            verdict = "better" if improved else "worse"
        rows.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "value": cur,
                "baseline": base,
                "delta": delta,
                "verdict": verdict,
                "detail": (current or {}).get(key, {}).get("detail") or {},
            }
        )
    return rows


def store_metrics(generation) -> dict:
    """يحسب مؤشرات توليدٍ ويحفظها فيه — يُستدعى بعد التوليد وعند الاعتماد."""
    metrics = ScheduleLab.for_generation(generation).compute()
    generation.metrics = metrics
    generation.save(update_fields=["metrics"])
    return metrics


def latest_baseline(school, academic_year):
    from operations.models import ScheduleBaseline

    return (
        ScheduleBaseline.objects.filter(school=school, academic_year=academic_year)
        .order_by("-created_at")
        .first()
    )


def is_finite(value) -> bool:
    return isinstance(value, int | float) and not math.isnan(value)


# ══════════════════════════════════════════════════════════════════
# العرض: مجموعاتٌ ودرجاتٌ مشتقّة (للرادار والبطاقات — لا للحكم)
# ══════════════════════════════════════════════════════════════════

SECTIONS: dict[str, str] = {
    "validity": "الصلاحية",
    "teacher": "يوم المعلّم",
    "fairness": "العدالة",
    "subject": "المادّة",
    "class": "الشعبة",
    "resources": "الموارد",
}


def metric_score(key: str, value) -> float | None:
    """درجةٌ من 0 إلى 100 تُشتقّ من المؤشر لعرضه على مقياسٍ واحد.

    التحويلُ رتيبٌ (الأفضلُ أعلى دائماً) ولا يدخل في أيّ حكمٍ أو توليد: هو
    لغةُ الرادار والبطاقات وحدَها، والقيمةُ الأصليّةُ تبقى بجانبه.
    """
    if not isinstance(value, int | float):
        return None
    better = CATALOG.get(key, ("", "", "info"))[2]
    if better == "info":
        return None
    if better == "high":
        return max(0.0, min(100.0, float(value)))
    if better == "zero":
        return 100.0 if value == 0 else max(0.0, 100.0 - 10.0 * value)
    if key == "fairness.edge_cv":
        return max(0.0, 100.0 * (1.0 - float(value)))
    if key == "teacher.compactness":
        return max(0.0, min(100.0, 100.0 / max(float(value), 1.0)))
    if key in ("subject.same_period_max", "teacher.run_avg"):
        return max(0.0, min(100.0, 100.0 * 2.0 / (1.0 + float(value))))
    if key in (
        "teacher.run_breaches",
        "resources.saturated_slots",
        "class.heavy_streak_days",
        "class.maths_late",
    ):
        return max(0.0, 100.0 - float(value))
    return 100.0 / (1.0 + float(value))


def section_scores(metrics: dict) -> dict[str, float | None]:
    """متوسّطُ درجات كلّ مجموعة — للرادار."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for key in CATALOG:
        score = metric_score(key, (metrics or {}).get(key, {}).get("value"))
        if score is not None:
            buckets[key.split(".")[0]].append(score)
    return {
        section: (round(mean(buckets[section]), 1) if buckets.get(section) else None)
        for section in SECTIONS
    }


def grouped_rows(current: dict, baseline: dict | None) -> list[dict]:
    """صفوفُ المقارنة مجمَّعةً بالأقسام، وكلُّ صفٍّ بدرجته ودرجة مرجعه."""
    rows = compare(current, baseline)
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["score"] = metric_score(r["key"], r["value"])
        r["baseline_score"] = metric_score(r["key"], r["baseline"])
        groups[r["key"].split(".")[0]].append(r)
    return [
        {"code": code, "label": label, "rows": groups.get(code, [])}
        for code, label in SECTIONS.items()
        if groups.get(code)
    ]


# ══════════════════════════════════════════════════════════════════
# قياسُ شبكةٍ في الذاكرة — لمفاضلة محاولات التوليد قبل أن تُكتب
# ══════════════════════════════════════════════════════════════════


def slots_from_grid(grid, ctx: Context) -> list[Slot]:
    """حصصُ الشبكة صفوفاً كصفوف القاعدة — الحصّةُ المزدوجةُ صفّان، والمنقسمةُ صفٌّ لكلّ معلّم."""
    out = []
    for entry in grid.all_entries():
        task, day, period = entry["task"], entry["day"], entry["period"]
        for slot in task.slots(period):
            for member in task.members:
                out.append(
                    Slot(
                        teacher_id=member.teacher_id,
                        teacher_name=member.teacher_name,
                        class_id=task.class_id,
                        class_name=task.class_name,
                        subject_id=member.subject_id,
                        subject_code=member.subject_code,
                        pedagogy=ctx.subject_pedagogy.get(member.subject_id, "regular"),
                        requires_double=bool(getattr(task, "prefers_double", False)),
                        day=day,
                        period=slot,
                        band_id=getattr(task, "band_id", "") or "",
                        elective_group=member.subject_name
                        if getattr(task, "is_split", False)
                        else "",
                    )
                )
    return out


def overall_score(metrics: dict) -> float:
    """درجةٌ واحدةٌ من 100: متوسّطُ درجات المجموعات المتاحة."""
    scores = [v for v in section_scores(metrics).values() if v is not None]
    return round(mean(scores), 2) if scores else 0.0


def grid_lab_score(grid, ctx: Context) -> tuple[float, dict]:
    """(الدرجةُ الكلّية، المؤشرات) لشبكةٍ في الذاكرة — بالمختبر نفسِه الذي يقيس الجدولَ الحيّ."""
    metrics = ScheduleLab(slots_from_grid(grid, ctx), ctx).compute()
    return overall_score(metrics), metrics
