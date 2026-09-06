"""التحسينُ المحلّيّ بعد الحلّ الكامل — المرحلةُ الثالثة من خطّة التجويد (2026-09-04).

الجدولُ الكاملُ ليس الأفضلَ بالضرورة: معلّمٌ حصّتاه الأولى والثالثة وبينهما
فراغٌ والثانيةُ شاغرةٌ لشعبته — نقلةٌ واحدةٌ تُغلق الفراغ ولا تكسر شيئاً.
فبعد أن يختار المولّدُ أفضلَ محاولة، يُبحث في أيّام المعلّمين التي فيها فراغٌ
أو تمدُّدٌ أو أطراف، وتُجرَّب على حصصها حركتان: نقلٌ إلى خانةٍ شاغرةٍ للشعبة،
أو تبديلٌ مع حصّة الشعبة الساكنةِ في الخانة المرغوبة. وتُقبل الحركةُ بشرطين:
لا تكسر قيداً صلباً (`is_slot_valid` كما في التوليد)، ولا تُنزل درجةَ المختبر
نفسِه الذي يقيس الجدولَ الحيّ.

والترشيحُ قبل المختبر بمقياسٍ محلّيٍّ هو مكوّناتُ المختبر نفسُها ليوم المعلّم
(الفراغُ الموزون، التراصّ، الأطراف، تجاوزُ التتابع) على الأيّام التي تمسّها
الحركةُ وحدَها — رخيصٌ، ومتّسقٌ مع الحكم النهائيّ فلا يقترح ما سيُرفض.
"""

from __future__ import annotations

import random
import time

from .scheduler_constraints import MAX_CONSECUTIVE, get_max_periods_for_day, is_slot_valid

DAYS = (0, 1, 2, 3, 4)
LAST_PERIOD = 7
#: ثقلُ الحصّة الزائدة عن نصيب اليوم في الكلفة المحلّيّة. وهو من رتبة كسر
#: التتابع (2.0) وفوق طرفِ اليوم (0.25): نقلةٌ تُنزل يوماً من أربعٍ إلى ثلاثٍ
#: تربح أكثرَ ممّا تخسره بفتح يومٍ خفيفٍ على حصّة.
OVERLOAD_WEIGHT = 1.5
#: جولاتٌ كاملةٌ بلا تحسّنٍ قبل التوقّف.
STALE_ROUNDS = 1


def _run_cap(preferences: dict | None, teacher_id: str) -> int:
    pref = (preferences or {}).get(teacher_id) or {}
    return pref.get("max_consecutive") or MAX_CONSECUTIVE


def _longest_run(periods: list[int]) -> int:
    ordered = sorted(set(periods))
    best = run = 1 if ordered else 0
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        run = run + 1 if later == earlier + 1 else 1
        best = max(best, run)
    return best


def fair_share(grid, teacher_id: str, preferences: dict | None) -> int:
    """نصيبُ اليوم الواحد: النصابُ على أيّامه، ولا يتجاوز تفضيلَه المكتوب.

    المولّدُ يرجّح بالنصيب وقتَ الوضع (SC13)، وهذا يقيسه بعد اكتمال الجدول:
    فما استقرّ يومٌ على أربعٍ ويومٌ على اثنتين إلّا لأنّ الترجيحَ وحدَه لا يرى
    الأسبوعَ كاملاً.
    """
    info = (getattr(grid, "coverage", None) or {}).get(teacher_id)
    share = LAST_PERIOD
    if info:
        _placements, load, days = info
        share = -(-load // max(1, len(days)))
    cap = ((preferences or {}).get(teacher_id) or {}).get("max_daily")
    return min(share, cap) if cap else share


def teacher_day_cost(grid, teacher_id: str, day: int, preferences: dict | None) -> float:
    """كلفةُ يومٍ لمعلّم — مكوّناتُ المختبر نفسُها: فراغٌ موزون، تراصّ، أطراف، تتابع.

    ومعها الحملُ الزائد: يومٌ فوق نصيبه من القسمة يُكلّف، فتجد النقلةُ طريقَها
    من اليوم العامر إلى اليوم الخفيف بدل أن تُقاس بالفراغ وحده.
    """
    from .schedule_lab import alternating_compactness, excess_gap_weight

    periods = sorted(set(grid.teacher_periods_on(teacher_id, day)))
    if not periods:
        return 0.0
    gap_weighted = excess_gap_weight(periods)
    compactness = alternating_compactness(periods) - 1.0
    edges = sum(1 for p in periods if p in (1, LAST_PERIOD))
    # التلاصقُ أثقلُ ما يُصلَح: رخصةُ ضرورةٍ لا شكلٌ مقبول.
    breach = 2.0 if _longest_run(periods) > _run_cap(preferences, teacher_id) else 0.0
    overload = max(0, len(periods) - fair_share(grid, teacher_id, preferences))
    return gap_weighted + compactness + 0.25 * edges + breach + OVERLOAD_WEIGHT * overload


def _members_free(grid, task, blocked, day: int, period: int) -> bool:
    for member in task.members:
        if grid.teacher_busy(member.teacher_id, day, period):
            return False
        if blocked and (member.teacher_id, day, period) in blocked:
            return False
    return True


def _fits(grid, task, blocked, day: int, period: int) -> bool:
    return _members_free(grid, task, blocked, day, period) and is_slot_valid(
        grid, day, period, task
    )


class Improver:
    def __init__(self, grid, tasks, blocked, preferences, lab_ctx, deadline: float, rng=None):
        from .schedule_lab import grid_lab_score

        self.grid = grid
        self.tasks = [t for t in tasks if t.span == 1]
        self.blocked = blocked or set()
        self.preferences = preferences or {}
        self.lab_ctx = lab_ctx
        self.deadline = deadline
        self.rng = rng or random.Random(101)
        self._lab = grid_lab_score
        self.score, _ = grid_lab_score(grid, lab_ctx)
        self.started = self.score
        self.moves = 0
        self.evaluations = 0
        self.teachers = sorted({m.teacher_id for t in self.tasks for m in t.members})

    # ── الكلفةُ المحلّيّة ──
    def _cost(self, pairs: set[tuple[str, int]]) -> float:
        return sum(teacher_day_cost(self.grid, tid, day, self.preferences) for tid, day in pairs)

    def _touched(self, tasks_days: list[tuple]) -> set[tuple[str, int]]:
        pairs = set()
        for task, days in tasks_days:
            for member in task.members:
                for day in days:
                    pairs.add((member.teacher_id, day))
        return pairs

    # ── الحركتان (داخل إطارٍ مفتوح) ──
    def _try_move(self, task, day2: int, period2: int) -> float | None:
        day1, period1 = self.grid.home_of(task)
        touched = self._touched([(task, {day1, day2})])
        before = self._cost(touched)
        self.grid.remove(task.class_id, day1, period1)
        if not _fits(self.grid, task, self.blocked, day2, period2):
            return None
        self.grid.place(day2, period2, task)
        return before - self._cost(touched)

    def _try_swap(self, task, other) -> float | None:
        day1, period1 = self.grid.home_of(task)
        day2, period2 = self.grid.home_of(other)
        touched = self._touched([(task, {day1, day2}), (other, {day1, day2})])
        before = self._cost(touched)
        self.grid.remove(task.class_id, day1, period1)
        self.grid.remove(other.class_id, day2, period2)
        if not _fits(self.grid, task, self.blocked, day2, period2):
            return None
        self.grid.place(day2, period2, task)
        if not _fits(self.grid, other, self.blocked, day1, period1):
            return None
        self.grid.place(day1, period1, other)
        return before - self._cost(touched)

    def _judge(self, delta: float | None) -> bool:
        """يقبل الحركةَ إن حسّنت الكلفةَ المحلّيّة ولم تُنزل درجةَ المختبر — وإلّا يردّها."""
        if delta is None or delta <= 1e-9:
            self.grid.rollback()
            return False
        new_score, _ = self._lab(self.grid, self.lab_ctx)
        self.evaluations += 1
        if new_score + 1e-9 >= self.score:
            self.grid.commit()
            self.score = new_score
            self.moves += 1
            return True
        self.grid.rollback()
        return False

    # ── المرشَّحات: أيّامٌ فيها ما يُصلَح ──
    def _weak_days(self) -> list[tuple[str, int, float]]:
        found = []
        for tid in self.teachers:
            for day in DAYS:
                cost = teacher_day_cost(self.grid, tid, day, self.preferences)
                if cost > 0:
                    found.append((tid, day, cost))
        found.sort(key=lambda x: -x[2])
        return found

    def _wanted_cells(self, teacher_id: str, day: int) -> list[int]:
        """الخاناتُ التي لو انتقلت إليها حصّةٌ لصلح اليوم على سياسة التناوب.

        الفراغاتُ الزائدة تُقصَّر بخانةٍ تبعد حصّةً عن حصّةٍ قائمة، والتلاصقُ
        يُفَكّ بنقل إحدى المتلاصقتين إلى خانةٍ تبعد حصّةً عن الكتلة.
        """
        periods = sorted(set(self.grid.teacher_periods_on(teacher_id, day)))
        if not periods:
            return []
        wanted = []
        for p in range(1, LAST_PERIOD + 1):
            if p in periods or (p - 1) in periods or (p + 1) in periods:
                continue
            if any(abs(p - q) == 2 for q in periods):
                wanted.append(p)
        return wanted

    def _tasks_of(self, teacher_id: str, day: int) -> list:
        out = []
        for period in self.grid.teacher_periods_on(teacher_id, day):
            task = self.grid.teacher_task_at(teacher_id, day, period)
            if task is not None and task.span == 1 and task not in out:
                out.append(task)
        return out

    def _improve_day(self, teacher_id: str, day: int) -> bool:
        tasks = self._tasks_of(teacher_id, day)
        wanted = self._wanted_cells(teacher_id, day)
        self.rng.shuffle(tasks)
        for task in tasks:
            max_p = get_max_periods_for_day(day, task.level_type)
            for period in wanted:
                if time.time() >= self.deadline:
                    return False
                if period > max_p:
                    continue
                occupant = self.grid.get_task_at(task.class_id, day, period)
                self.grid.begin()
                if occupant is None:
                    accepted = self._judge(self._try_move(task, day, period))
                elif occupant.span == 1 and occupant is not task:
                    accepted = self._judge(self._try_swap(task, occupant))
                else:
                    self.grid.rollback()
                    accepted = False
                if accepted:
                    return True
            # وإن لم يُغلق الفراغُ من داخل اليوم: تُنقل الحصّةُ المعزولةُ إلى يومٍ آخر
            # بجانب كتلةٍ قائمةٍ لمعلّمها — إن كانت خانةُ الشعبة شاغرة.
            for other_day in DAYS:
                if other_day == day:
                    continue
                for period in self._wanted_cells(teacher_id, other_day):
                    if time.time() >= self.deadline:
                        return False
                    if period > get_max_periods_for_day(other_day, task.level_type):
                        continue
                    if self.grid.get_task_at(task.class_id, other_day, period) is not None:
                        continue
                    self.grid.begin()
                    if self._judge(self._try_move(task, other_day, period)):
                        return True
        return False

    def _thursday_pairs(self) -> list:
        """حصصٌ ثانيةٌ لمادّةٍ في شعبةٍ يومَ الخميس — تُنقل إلى يومٍ آخر (HC15)."""
        seen: dict[tuple[str, str], list] = {}
        for task in self.tasks:
            home = self.grid.home_of(task)
            if home is None or home[0] != 4 or getattr(task, "prefers_double", False):
                continue
            seen.setdefault((task.class_id, task.subject_id), []).append(task)
        return [group[1] for group in seen.values() if len(group) >= 2]

    def _move_off_thursday(self, task) -> bool:
        for day in (0, 1, 2, 3):
            for period in range(1, get_max_periods_for_day(day, task.level_type) + 1):
                if time.time() >= self.deadline:
                    return False
                if self.grid.get_task_at(task.class_id, day, period) is not None:
                    continue
                self.grid.begin()
                delta = self._try_move(task, day, period)
                # الخروجُ من الخميس مكسبٌ بذاته: يكفي ألّا تسوءَ كلفةُ الأيّام.
                if delta is not None and delta >= -1e-9:
                    new_score, _ = self._lab(self.grid, self.lab_ctx)
                    self.evaluations += 1
                    if new_score + 1e-9 >= self.score:
                        self.grid.commit()
                        self.score, self.moves = new_score, self.moves + 1
                        return True
                self.grid.rollback()
        return False

    def run(self) -> dict:
        stale = 0
        rounds = 0
        for task in self._thursday_pairs():
            if time.time() >= self.deadline:
                break
            self._move_off_thursday(task)
        while time.time() < self.deadline and stale < STALE_ROUNDS + 1:
            rounds += 1
            improved = False
            for teacher_id, day, _cost in self._weak_days():
                if time.time() >= self.deadline:
                    break
                improved = self._improve_day(teacher_id, day) or improved
            stale = 0 if improved else stale + 1
        return {
            "moves": self.moves,
            "lab_evaluations": self.evaluations,
            "rounds": rounds,
            "score_before": self.started,
            "score_after": self.score,
        }


def improve(grid, tasks, blocked, preferences, lab_ctx, deadline: float, rng=None) -> dict:
    """يُحسّن جدولاً كاملاً في الذاكرة حتّى الموعد — ويُعيد ما فعل بالأرقام."""
    return Improver(grid, tasks, blocked, preferences, lab_ctx, deadline, rng).run()
