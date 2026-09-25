"""scheduler_settle.py — مرحلةُ السداد: ما كُسر برخصةٍ يُعاد إليه قبل أن يُعتمد (SCH-03).

الرخصتان (`allow_adjacent`، `allow_dense`) ملاذٌ حين تبقى حصّةٌ بلا موضع، وهما
صحيحتان في وقتهما: الجدولُ ناقصٌ والطريقُ مسدود. لكنّ ما يُكسَر حينها يبقى
مكسوراً بعد أن يكتمل الجدولُ ويتّسع — ولا أحدَ يعود إليه. ففي التوليد المعتمد
(2026-09-24) اثنتا عشرةَ مخالفةً للقسمة، لعشرٍ منها تبديلٌ واحدٌ يُصلحها.

فهنا دَينٌ يُسدَّد: كلُّ حصّةٍ يرفضها المدقّقُ (`scheduler_audit`) في موضعها تُجرَّب
لها حركاتٌ بالقيود الصلبة كاملةً بلا رخصة — نقلةٌ إلى خانةٍ شاغرةٍ لشعبتها، ثمّ
تبديلٌ مع ساكن خانة، ثمّ (لمخالفة التوزيع) سلسلةُ تبديلٍ بخطوتين، ثمّ سلسلةُ إزاحة.

والقبولُ **معجميٌّ برتب الخطورة** (`TIER_OF`) لا بعدد المخالفات. كان السدادُ
يقبل كلَّ حركةٍ تُنقص العدد، فصرف وقتَه على تلاصق المعلّمين وسدّد ثلاثاً فقط من
اثنتي عشرةَ مخالفةَ توزيع (نسخةُ الإنتاج: 69 ← 42 في 139 ثانية) — ولم يكن يمنعه
شيءٌ أن يشتري تلاصقين بمخالفة توزيع. فالحركةُ تُقبل إن صغُر أثرُها فيما مسّته
رتبةً رتبة: لا تسوء رتبةٌ لتصلح ما دونها. ولا يُسأل المختبرُ عن درجته هنا — ذاك
شأنُ التحسين بعده.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from functools import partial
from typing import TYPE_CHECKING

from .scheduler import (
    DAYS,
    ScheduleGrid,
    Task,
    _blockers,
    _candidate_starts,
    get_available_slots,
    rank_slots,
)
from .scheduler_audit import EXEMPTION, breach_keys, task_breaches
from .scheduler_constraints import get_max_periods_for_day
from .scheduler_improve import _fits

if TYPE_CHECKING:
    from core.models import School

Cell = tuple[int, int]
#: حصّةٌ وخانتُها المقصودة — `None` يعني «تُرفع ولا تُوضع» (للاستطلاع وحده).
Step = tuple[Task, Cell | None]
Blocked = set[tuple[str, int, int | None]]

#: رتبُ الخطورة — يُقارَن بها أثرُ الحركة معجميّاً، والأدنى أثقل:
#:
#:   0  توزيعُ المادّة في أسبوع الشعبة: القسمةُ (HC6)، وخميسُ الثانويّ (HC17)،
#:      وتلاصقُ حصّتَي اليوم (HC20). هذا ما يراه الطالبُ في جدوله وما لاحظته
#:      المدرسة — الرياضياتُ حصّتين الأحد ولا شيءَ الخميس.
#:   1  أسبوعُ المعلّم بقرار الإدارة: التغطيةُ (HC14) والسقفُ (HC16) والحدُّ الأدنى
#:      (HC16B)، والتفريغُ (EX).
#:   2  راحةُ المعلّم في يومه — التلاصقُ (HC5) والفراغُ (HC10) — وما سواها.
TIER_OF: dict[str, int] = {
    "HC6": 0,
    "HC17": 0,
    "HC20": 0,
    "HC14": 1,
    "HC16": 1,
    "HC16B": 1,
    EXEMPTION: 1,
}
LAST_TIER = 2
#: عمقُ سلسلة الإزاحة — كعمق جولة الإصلاح (3)، وأربعٌ لمخالفة التوزيع وحدَها بعد
#: أن تعجز الثلاث: هي ما يراه الطالب، وفي غيرها يُقلّب الرابعُ أكثرَ ممّا يُصلح.
EJECT_DEPTH = 3
DEEP_EJECT_DEPTH = 4
MOVE_KINDS = ("move", "swap", "chain", "eject", "eject_deep")


def tier_of(code: str) -> int:
    return TIER_OF.get(code, LAST_TIER)


def profile(keys: Iterable[tuple]) -> tuple[int, int, int]:
    """عددُ المخالفات في كلّ رتبة — ومفتاحُ المخالفة أوّلُه رمزُ قيدها."""
    counts = [0] * (LAST_TIER + 1)
    for key in keys:
        counts[tier_of(key[0])] += 1
    return counts[0], counts[1], counts[2]


def standing(
    grid: ScheduleGrid, tasks: Iterable[Task], blocked: Blocked | None = None
) -> tuple[int, int, int]:
    """أثرُ مخالفات هذه الحصص في الجدول كما هو الآن، رتبةً رتبة."""
    return profile(breach_keys(grid, tasks, blocked))


class Settler:
    def __init__(
        self,
        grid: ScheduleGrid,
        tasks: Iterable[Task],
        blocked: Blocked | None,
        preferences: dict | None,
        school: School | None = None,
        deadline: float | None = None,
    ) -> None:
        self.grid = grid
        self.tasks = list(tasks)
        self.blocked: Blocked = blocked or set()
        self.preferences = preferences or {}
        self.school = school
        self.deadline = deadline if deadline is not None else time.time() + 60
        self.moves = dict.fromkeys(MOVE_KINDS, 0)
        self._by_class: dict[str, list[Task]] = {}
        self._by_teacher: dict[str, list[Task]] = {}
        for task in self.tasks:
            self._by_class.setdefault(task.class_id, []).append(task)
            for member in task.members:
                self._by_teacher.setdefault(member.teacher_id, []).append(task)
        #: مخالفاتُ كلّ حصّةٍ في الجدول القائم — تُحسب عند أوّل سؤالٍ وتُنسى كلُّها
        #: عند كلّ حركةٍ مقبولة، فلا يُحكم على الجدول بحالٍ مضى.
        self._known: dict[int, frozenset[tuple]] = {}
        #: كم حركةً قُبلت. وحصّةٌ فشل سدادُها لا تُعاد ما لم يتغيّر الجدولُ بعدها —
        #: وإلّا أعادت كلُّ رتبةٍ بحثَ التوزيع العميقَ كلَّه بلا جديد.
        self._version = 0
        self._failed: dict[int, int] = {}

    # ── الحكم ──
    def _affected(self, *moved: Task) -> list[Task]:
        """حصصُ الشُّعب والمعلّمين الذين مسّتهم الحركة — ففيها وحدَها يتغيّر الحكم."""
        seen: dict[int, Task] = {}
        for task in moved:
            for other in self._by_class.get(task.class_id, ()):
                seen[id(other)] = other
            for member in task.members:
                for other in self._by_teacher.get(member.teacher_id, ()):
                    seen[id(other)] = other
        return list(seen.values())

    def _keys(self, task: Task) -> frozenset[tuple]:
        """مخالفاتُ الحصّة في الجدول القائم — فلا يُسأل عنها داخل إطارٍ مفتوح."""
        found = self._known.get(id(task))
        if found is None:
            found = frozenset(b.key for b in task_breaches(self.grid, task, self.blocked))
            self._known[id(task)] = found
        return found

    def _standing(self, scope: Iterable[Task]) -> tuple[int, int, int]:
        keys: set[tuple] = set()
        for task in scope:
            keys |= self._keys(task)
        return profile(keys)

    def _worst(self, task: Task) -> int | None:
        """أثقلُ رتبةٍ تخالفها الحصّةُ في موضعها — `None` إن كانت سليمة."""
        return min((tier_of(key[0]) for key in self._keys(task)), default=None)

    def _expired(self) -> bool:
        return time.time() >= self.deadline

    # ── إطارُ التراجع: `ScheduleGrid.begin/commit/rollback` بلا أنواعٍ بعد (SCH-16)،
    # ونداؤها من شيفرةٍ مُنوَّعةٍ يُسقط سقّاطةَ mypy — فيُنادى من هنا وحدَه. ──
    def _begin(self) -> None:
        self.grid.begin()  # type: ignore[no-untyped-call]

    def _commit(self) -> None:
        self.grid.commit()  # type: ignore[no-untyped-call]

    def _rollback(self) -> None:
        self.grid.rollback()  # type: ignore[no-untyped-call]

    def attempt(self, action: Callable[[], bool], kind: str) -> bool:
        """يجري الحركةَ، ويقبلها إن صغُر أثرُها فيما مسّته معجميّاً — وإلّا يردّها.

        تُجرى في إطارٍ ويُقرأ من سجلّ الشبكة ما مسّته (`touched`) — فالسلسلةُ لا
        يُعرف مداها سلفاً — ثمّ تُردّ ليُقارَن ذلك النطاقُ بما كان عليه، وتُعاد إن
        صغُر. والإعادةُ حتميّة: الحالُ نفسُه والترتيبُ نفسُه ولا نردَ في الحركات.
        والحركةُ التي ترفضها القيودُ تُردّ قبل أن يُعدّ شيء.
        """
        self._begin()
        if not action():
            self._rollback()
            return False
        scope = self._affected(*self.grid.touched())
        after = standing(self.grid, scope, self.blocked)
        self._rollback()
        if not after < self._standing(scope):
            return False
        self._begin()
        if not action():
            self._rollback()
            return False
        self._commit()
        self._known.clear()
        self._version += 1
        self.moves[kind] += 1
        return True

    # ── الحركات (كلٌّ في إطارٍ مفتوحٍ يُغلقه `attempt`) ──
    def _lift(self, task: Task) -> None:
        home = self.grid.home_of(task)
        if home is not None:
            self.grid.remove(task.class_id, *home)

    def _shift(self, *steps: Step) -> bool:
        """تُرفع الحصصُ كلُّها ثمّ تُوضع بالترتيب، وكلُّ وضعٍ بالقيود الصلبة كاملةً
        بلا رخصةٍ على ما سبقه — فالنقلةُ خطوةٌ والتبديلُ خطوتان والسلسلةُ ثلاث."""
        for task, _cell in steps:
            self._lift(task)
        for task, cell in steps:
            if cell is None:
                continue
            day, period = cell
            if not all(_fits(self.grid, task, self.blocked, day, s) for s in task.slots(period)):
                return False
            self.grid.place(day, period, task)
        return True

    def _probe(self, *steps: Step) -> bool:
        """أتصحّ هذه الخطوات؟ — تُجرَّب وتُردّ، فيُقطع الفرعُ قبل أن يُبحث ما تحته."""
        self._begin()
        try:
            return self._shift(*steps)
        finally:
            self._rollback()

    def _aim(self, task: Task, cell: Cell, depth: int) -> bool:
        self._lift(task)
        return self._eject_into(task, cell, depth)

    def _eject_into(self, task: Task, cell: Cell, depth: int) -> bool:
        """سلسلةُ الإزاحة إلى خانةٍ بعينها: يُخرَج ساكنوها، وتنزل الحصّة، ويُعاد المُخرَجون.

        هي `scheduler._try_eject` بمنطقها وحارساتها، بفرقين: تُصوَّب إلى خانةٍ فتُوزن
        كلُّ خانةٍ على حدة لا أوّلُ سلسلةٍ تنجح أينما وقعت، وتحترم الموعدَ في كلّ
        مستوى — فالعمقُ الرابعُ بلا موعدٍ قد يستهلك الميزانيةَ كلَّها في حصّةٍ واحدة.
        """
        day, period = cell
        evicted: list[Task] | None = _blockers(  # type: ignore[no-untyped-call]
            self.grid, task, day, period, self.blocked
        )
        #: إزاحةُ أكثرَ من ساكنَين تُقلّب الجدولَ أكثرَ ممّا تُصلح.
        if not evicted or len(evicted) > 2:
            return False
        if any(self.grid.home_of(e) is None for e in evicted):
            return False
        self._begin()
        for occupant in evicted:
            self._lift(occupant)
        if all(_fits(self.grid, task, self.blocked, day, s) for s in task.slots(period)):
            self.grid.place(day, period, task)
            if self._rehome(evicted, depth):
                self._commit()
                return True
        self._rollback()
        return False

    def _rehome(self, evicted: list[Task], depth: int) -> bool:
        """يُعيد المُخرَجين إلى خاناتٍ صحيحة، أو يُزيح كلٌّ منهم غيرَه إن بقي في العمق سعة."""
        for task in evicted:
            if self._expired():
                return False
            free = get_available_slots(self.grid, task, self.blocked, self.school)
            ranked = rank_slots(self.grid, task, free, self.preferences)
            if ranked:
                self.grid.place(ranked[0][0], ranked[0][1], task)
                continue
            if depth > 1 and self._eject_anywhere(task, depth - 1):
                continue
            return False
        return True

    def _eject_anywhere(self, task: Task, depth: int) -> bool:
        for cell in self._starts(task):
            if self._expired():
                return False
            if self._eject_into(task, cell, depth):
                return True
        return False

    # ── الجوار ──
    def _starts(self, task: Task) -> list[Cell]:
        """مواضعُ البدء الممكنة: بلا تفريغٍ لساكنيها، وبكتلة المزدوجة من الجرس."""
        return list(
            _candidate_starts(  # type: ignore[no-untyped-call]
                self.grid, task, self.blocked, self.school
            )
        )

    def _cells(self, task: Task) -> list[Cell]:
        """خاناتُ شعبة الحصّة كلُّها في الأسبوع."""
        return [
            (day, period)
            for day in DAYS
            for period in range(1, get_max_periods_for_day(day, task.level_type) + 1)
        ]

    def _single(self, class_id: str, cell: Cell) -> Task | None:
        """ساكنُ خانة الشعبة إن كان حصّةً مفردة — فالمزدوجةُ لا تُبادَل بمفردة."""
        found = self.grid.get_task_at(class_id, *cell)
        return found if found is not None and found.span == 1 else None

    def _direct(self, task: Task, home: Cell, targets: list[Cell]) -> bool:
        """النقلةُ إلى خانةٍ شاغرة، أو التبديلُ مع ساكنها."""
        for target in targets:
            if self._expired():
                return False
            occupants = {
                id(o): o
                for s in task.slots(target[1])
                if (o := self.grid.get_task_at(task.class_id, target[0], s)) is not None
                and o is not task
            }
            if not occupants:
                if self.attempt(partial(self._shift, (task, target)), "move"):
                    return True
                continue
            other = next(iter(occupants.values()))
            if len(occupants) != 1 or task.span != 1 or other.span != 1:
                continue
            if self.attempt(partial(self._shift, (task, target), (other, home)), "swap"):
                return True
        return False

    def _two_step(self, task: Task, home: Cell, targets: list[Cell]) -> bool:
        """سلسلةُ تبديلٍ بخطوتين (جوارُ كِمبي محدود) — لمخالفة التوزيع حين يعجز التبديل.

        الحصّةُ إلى خانة ساكنٍ X في شعبتها، وX إلى خانةٍ شاغرة، أو إلى خانة ساكنٍ
        آخر Y ينتقل هو إلى شاغرة — ومنها الخانةُ التي أخلتها الحصّة، فتكون دورةً
        ثلاثيّة. والتبديلُ البسيط يعجز حين لا يقبل X موضعَ الحصّة (مادّتُه في ذلك
        اليوم، أو معلّمُه مشغولٌ أو مفرَّغ)، وفي مدرسةٍ إشغالُها ثمانيةٌ وتسعون بالمئة
        لا شاغرةَ تُنقل إليها الحصّةُ مباشرة. والمدى شعبةٌ واحدةٌ فالبحثُ محدود،
        ويُقطع كلُّ فرعٍ عند أوّل خطوةٍ لا تصحّ.
        """
        cells = self._cells(task)
        free = [c for c in cells if self.grid.get_task_at(task.class_id, *c) is None]
        for target in targets:
            if self._expired():
                return False
            x = self._single(task.class_id, target)
            if x is None or not self._probe((task, target), (x, None)):
                continue
            # X إلى شاغرة. وبيتُ الحصّة ليس منها هنا: ذاك التبديلُ البسيطُ وقد جُرِّب.
            for spot in free:
                if self._expired():
                    return False
                if self.attempt(partial(self._shift, (task, target), (x, spot)), "chain"):
                    return True
            for via in cells:
                y = self._single(task.class_id, via) if via not in (home, target) else None
                if y is None:
                    continue
                if self._expired():
                    return False
                if not self._probe((task, target), (x, via), (y, None)):
                    continue
                for spot in (*free, home):
                    step = partial(self._shift, (task, target), (x, via), (y, spot))
                    if self.attempt(step, "chain"):
                        return True
        return False

    def _eject(self, task: Task, targets: list[Cell], depth: int) -> bool:
        kind = "eject" if depth <= EJECT_DEPTH else "eject_deep"
        for target in targets:
            if self._expired():
                return False
            if self.attempt(partial(self._aim, task, target, depth), kind):
                return True
        return False

    def settle_task(self, task: Task, deep: bool = False) -> bool:
        """يسدّد مخالفاتِ حصّةٍ واحدة بأوّل حركةٍ يصغُر بها الأثر — والأرخصُ أوّلاً.

        و`deep` لمخالفة التوزيع: بعد النقلة والتبديل سلسلةُ الخطوتين، ثمّ الإزاحةُ
        بعمقٍ ثلاثٍ فأربع — كلُّ ذلك داخل الموعد.
        """
        home = self.grid.home_of(task)
        if home is None:
            return False
        targets = [c for c in self._starts(task) if c != home]
        if self._direct(task, home, targets):
            return True
        if deep and task.span == 1 and self._two_step(task, home, targets):
            return True
        depths = (EJECT_DEPTH, DEEP_EJECT_DEPTH) if deep else (EJECT_DEPTH,)
        return any(self._eject(task, targets, depth) for depth in depths)

    # ── الجولات ──
    def offenders(self, ceiling: int = LAST_TIER) -> list[tuple[int, Task]]:
        """حصصٌ يرفضها المدقّقُ في موضعها — أثقلُها رتبةً أوّلاً، ثمّ بشعبتها ليثبت الترتيب."""
        found: list[tuple[int, Task]] = []
        for task in self.tasks:
            worst = self._worst(task)
            if worst is not None and worst <= ceiling:
                found.append((worst, task))
        found.sort(
            key=lambda wt: (
                wt[0],
                wt[1].class_name,
                wt[1].subject_name,
                self.grid.home_of(wt[1]) or (9, 9),
            )
        )
        return found

    def _round(self, ceiling: int) -> bool:
        progressed = False
        for _tier, task in self.offenders(ceiling):
            if self._expired():
                break
            # حركةٌ سبقت في الجولة قد تكون سدّدت هذه أو غيّرت رتبتها.
            worst = self._worst(task)
            if worst is None or worst > ceiling or self._failed.get(id(task)) == self._version:
                continue
            if self.settle_task(task, deep=worst == 0):
                progressed = True
            else:
                self._failed[id(task)] = self._version
        return progressed

    def run(self) -> dict:
        """الرتبُ على التوالي: التوزيعُ وحدَه حتى لا يتقدّم، ثمّ يُضمّ أسبوعُ المعلّم،
        ثمّ الباقي — فلا يُصرف الموعدُ على التلاصق قبل أن يُسدَّد ما يراه الطالب."""
        before = self._standing(self.tasks)
        rounds = 0
        for ceiling in range(LAST_TIER + 1):
            while not self._expired():
                rounds += 1
                if not self._round(ceiling):
                    break
        after = self._standing(self.tasks)
        return {
            "breaches_before": sum(before),
            "breaches_after": sum(after),
            #: [توزيعُ المادّة، أسبوعُ المعلّم، راحتُه وما سواها] — انظر `TIER_OF`.
            "tiers_before": list(before),
            "tiers_after": list(after),
            "rounds": rounds,
            "moves": dict(self.moves),
            "timed_out": self._expired(),
        }


def settle(
    grid: ScheduleGrid,
    tasks: Iterable[Task],
    blocked: Blocked | None,
    preferences: dict | None,
    school: School | None = None,
    deadline: float | None = None,
) -> dict:
    """يسدّد ما كُسر برخصةٍ في جدولٍ كامل — ويُعيد ما فعل بالأرقام.

    وذاكرةُ أزواج الجرس (`joinable_pairs_cached`) على المُنادي كما في التوليد
    وسداد الجدول الحيّ: المزدوجةُ تسأل عنها في كلّ مرشَّحٍ من السلسلة.
    """
    return Settler(grid, tasks, blocked, preferences, school, deadline).run()


def settle_safely(
    grid: ScheduleGrid,
    tasks: Iterable[Task],
    blocked: Blocked | None,
    preferences: dict | None,
    school: School | None = None,
    deadline: float | None = None,
) -> dict:
    """السدادُ لا يُسقط توليداً: عطبٌ فيه يُسجَّل ويبقى الجدولُ كما وصل إليه.

    والسدادُ مرحلةٌ تُحسّن ولا تُنشئ: جدولٌ تامٌّ بمخالفاتٍ مذكورةٍ خيرٌ من توليدٍ فشل بعد
    دقيقتين من البحث. وما فُتح من أُطر التراجع في الشبكة قبل العطب يُطوى، فلا يبقى الجدولُ
    نصفَ منقول (وهو ما يُكتب بعدها في القاعدة).
    """
    try:
        return settle(grid, tasks, blocked, preferences, school, deadline)
    except Exception:  # noqa: BLE001 — يُسجَّل ولا يُبتلع
        logging.getLogger(__name__).exception("السداد: عطبٌ في مرحلة السداد — يُكمل التوليدُ بلا سداد")
        while grid._journal:
            grid.rollback()  # type: ignore[no-untyped-call]
        return {"failed": True}
