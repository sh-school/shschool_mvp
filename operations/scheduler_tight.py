"""معلّمٌ بلا هامش يُوضع بالبحث الدقيق قبل الجشع — لا بالترجيح.

سفيان (2026-09-05): تفريغاتُه تترك له اثنتي عشرةَ خانةً بلا تلاصقٍ لاثنتي عشرةَ
حصّة. فالجشعُ يرتّب خاناته بالترجيح ويأخذ الأولى، وأيُّ اختيارٍ يُغلق مساراً لا
يعود عنه — فتبقى حصّةٌ بلا موضعٍ وإن وُجد حلّ. والتراجعُ على مهامّه وحدَها رخيص:
اثنتا عشرةَ مهمّةً في أربعَ عشرةَ خانةً، وقيودُه الصلبةُ هي القيودُ نفسُها
(`is_slot_valid`) لا نسخةٌ منها.

يُستدعى على الشبكة الفارغة في أوّل كلّ محاولة، لمعلّمين سعتُهم لا تزيد على
نصابهم إلّا بحصّةٍ — والباقون للجشع كما كانوا.
"""

from __future__ import annotations

from collections import defaultdict

from .preference_capacity import weekly_capacity
from .scheduler_constraints import get_max_periods_for_day, is_slot_valid

DAYS = (0, 1, 2, 3, 4)
LAST_PERIOD = 7
#: الهامشُ الذي دونه يُعَدّ المعلّمُ ضيّقاً.
TIGHT_SLACK = 1
#: أقلُّ نصابٍ يستحقّ البحثَ الدقيق — الصغيرُ يضعه الجشعُ بلا عناء.
MIN_LOAD = 6
#: سقفُ عقد البحث لكلّ معلّم — دون انفجارٍ على بياناتٍ غريبة.
NODE_BUDGET = 200_000


def tight_teachers(tasks, prefs, blocked) -> list[str]:
    """معلّمون سعتُهم − نصابُهم ≤ الهامش — بالحساب نفسِه الذي تُعرض به النصيحة."""
    load: dict[str, int] = defaultdict(int)
    for t in tasks:
        for m in t.members:
            load[m.teacher_id] += t.span
    blocked_per_day: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for teacher_id, day, _period in blocked:
        blocked_per_day[teacher_id][day] += 1
    found = []
    for pref in prefs:
        tid = str(pref.teacher_id)
        if load.get(tid, 0) < MIN_LOAD:
            continue
        free = {d: LAST_PERIOD - n for d, n in blocked_per_day[tid].items()}
        capacity = weekly_capacity(
            pref.max_daily_periods, pref.max_consecutive, pref.max_gap, pref.free_day, free
        )
        if capacity - load[tid] <= TIGHT_SLACK:
            found.append(tid)
    return found


def _cells(grid, task, blocked):
    for day in DAYS:
        for period in range(1, get_max_periods_for_day(day, task.level_type) - task.span + 2):
            slots = list(task.slots(period))
            if any((m.teacher_id, day, s) in blocked for m in task.members for s in slots):
                continue
            if any(grid.get_task_at(task.class_id, day, s) is not None for s in slots):
                continue
            if any(grid.teacher_busy(m.teacher_id, day, s) for m in task.members for s in slots):
                continue
            if all(is_slot_valid(grid, day, s, task) for s in slots):
                yield day, period


def _interleave(mine: list) -> list:
    """مهامُّ الشُّعب بالتناوب: شعبةٌ فشعبةٌ لا شعبةٌ كاملةٌ ثمّ أخرى — فالتوزيعُ على
    الأيّام (يومٌ واحدٌ بحصّتين) لا يُكتشف انسدادُه في آخر السلسلة."""
    by_class: dict[str, list] = defaultdict(list)
    for t in sorted(mine, key=lambda t: (-t.span, t.class_id)):
        by_class[t.class_id].append(t)
    out: list = []
    while any(by_class.values()):
        for cid in list(by_class):
            if by_class[cid]:
                out.append(by_class[cid].pop(0))
    return out


def _solve_teacher(grid, mine: list, blocked, rng) -> bool:
    """تراجعٌ على مهامّ معلّمٍ واحد — الشُّعبُ بالتناوب، والخاناتُ من الأيّام الأخفّ أوّلاً."""
    mine = _interleave(mine)
    budget = NODE_BUDGET

    def solve(index: int) -> bool:
        nonlocal budget
        if index == len(mine):
            return True
        task = mine[index]
        options = list(_cells(grid, task, blocked))
        if rng is not None:
            rng.shuffle(options)
        # اليومُ الذي لا حصّةَ فيه لهذه الشعبة أوّلاً — 1-1-1-1-1 قبل أن يُضاعَف يوم.
        options.sort(key=lambda dp: grid.subject_on_day(task.class_id, task.subject_id, dp[0]))
        for day, period in options:
            budget -= 1
            if budget <= 0:
                return False
            grid.begin()
            grid.place(day, period, task)
            if solve(index + 1):
                grid.commit()
                return True
            grid.rollback()
        return False

    return solve(0)


def place_tight(grid, tasks, blocked, prefs, rng=None) -> dict:
    """يضع مهامَّ المعلّمين الضيّقين بالتراجع؛ يُعيد {معلّم: أوُضعت كلُّها؟}."""
    outcome: dict[str, bool] = {}
    for tid in sorted(set(tight_teachers(tasks, prefs, blocked))):
        mine = [t for t in tasks if any(m.teacher_id == tid for m in t.members)]
        if not mine or any(grid.home_of(t) is not None for t in mine):
            continue
        # الخلطُ ينوّع المحاولات، وقد يقود إلى شجرةٍ ميّتةٍ تستهلك السقف —
        # فإن أخفق أُعيد البحثُ بترتيبه الثابت قبل أن يُسلَّم الأمرُ للجشع.
        outcome[tid] = _solve_teacher(grid, mine, blocked, rng) or (
            rng is not None and _solve_teacher(grid, mine, blocked, None)
        )
    return outcome
