"""السدادُ المعجميّ (SCH-03): توزيعُ المادّة أوّلاً، ولا يُشترى راحةُ معلّمٍ بكسره.

في الجدول المعتمد (2026-09-24) للرياضيات في 9/1 حصّتان الأحد ولا شيءَ الخميس.
وكان السدادُ يقبل كلَّ حركةٍ تُنقص **عددَ** المخالفات، فصرف وقتَه على التلاصق
وسدّد ثلاثاً من اثنتي عشرة. فصار الحكمُ برتب الخطورة: (التوزيع، أسبوعُ المعلّم،
راحتُه) — يُقارَن معجميّاً، والتوزيعُ يُبحث له أعمق.
"""

import time

import pytest

from operations.scheduler import ScheduleGrid, Task
from operations.scheduler_audit import grid_breaches
from operations.scheduler_settle import Settler, settle, standing, tier_of

pytestmark = pytest.mark.django_db


def lesson(subject="math", teacher="t1", klass="c1", weekly=5, **kw):
    fields = {
        "class_id": klass,
        "class_name": klass,
        "subject_id": subject,
        "subject_name": subject,
        "subject_code": subject.upper(),
        "teacher_id": teacher,
        "teacher_name": teacher,
        "weekly_periods": weekly,
        "level_type": "sec",
        "grade": "G10",
        "available_days": 5,
    }
    fields.update(kw)
    return Task(**fields)


def place(grid, tasks, cells):
    for task, (day, period) in zip(tasks, cells, strict=True):
        grid.place(day, period, task)


def codes(grid, tasks, blocked=None):
    return {b.code for b in grid_breaches(grid, tasks, blocked)}


def per_day(grid, subject="math", klass="c1"):
    return [grid.subject_on_day(klass, subject, day) for day in range(5)]


def rotation(exchange=()):
    """شعبةٌ ممتلئة: سبعُ موادّ خماسيّة، لكلٍّ معلّمُها، تدور على الحصص يوماً بيوم.

    المادّةُ k يومَ d في الحصّة ((k + d) mod 7) + 1 — فلا مادّةَ تتكرّر في يوم،
    ولا معلّمَ يُلاصق نفسَه، ولا حصّةَ تتكرّر في موضعها. و`exchange` زوجُ
    (مادّة، يوم) تتبادلان خانتيهما لإفساد التوزيع عمداً.
    """
    grid = ScheduleGrid()
    tasks = {(k, d): lesson(subject=f"s{k}", teacher=f"t{k}") for k in range(7) for d in range(5)}
    cells = {(k, d): (d, (k + d) % 7 + 1) for k in range(7) for d in range(5)}
    if exchange:
        first, second = exchange
        cells[first], cells[second] = cells[second], cells[first]
    for key, task in tasks.items():
        grid.place(*cells[key], task)
    return grid, list(tasks.values())


def test_the_tiers_put_the_students_week_first():
    assert [tier_of(c) for c in ("HC6", "HC17", "HC20")] == [0, 0, 0]
    assert [tier_of(c) for c in ("HC14", "HC16", "HC16B", "EX")] == [1, 1, 1, 1]
    assert [tier_of(c) for c in ("HC5", "HC10", "HC7")] == [2, 2, 2]


def test_a_crowded_day_is_moved_to_the_empty_one():
    """خماسيّةٌ حصّتين الأحد ولا شيءَ الخميس، والخميسُ شاغر — نقلةٌ واحدةٌ تسدّها."""
    grid = ScheduleGrid()
    maths = [lesson() for _ in range(5)]
    place(grid, maths, [(0, 2), (0, 4), (1, 3), (2, 5), (3, 1)])
    assert codes(grid, maths) == {"HC6"}

    result = settle(grid, maths, set(), {}, deadline=time.time() + 30)

    assert result["tiers_before"] == [1, 0, 0]
    assert result["tiers_after"] == [0, 0, 0]
    assert result["moves"]["move"] == 1
    assert per_day(grid) == [1, 1, 1, 1, 1]


def test_a_clean_timetable_is_left_as_it_is():
    grid, tasks = rotation()
    homes = {id(t): grid.home_of(t) for t in tasks}

    result = settle(grid, tasks, set(), {}, deadline=time.time() + 30)

    assert result["breaches_before"] == result["breaches_after"] == 0
    assert sum(result["moves"].values()) == 0
    assert {id(t): grid.home_of(t) for t in tasks} == homes


def test_a_teacher_comfort_fix_is_not_bought_with_a_distribution_breach():
    """نقلةٌ برخصة (بلا فحص القيود) تفكّ تلاصقَ المعلّم وتكرارَ الموضع — أربعٌ من الرتبة
    الثالثة — لكنّها تجعل الرياضياتِ حصّتين الاثنين. العددُ ينزل من أربعٍ إلى واحدة،
    والمعجمُ يرفضها: التوزيعُ لا يسوء ليصلح ما دونه."""
    grid = ScheduleGrid()
    maths = [lesson(teacher="tm") for _ in range(5)]
    # الرياضياتُ في الثانية ثلاثَ مرّات (HC7)، ومعلّمُها يُلاصق نفسَه الأحد (HC5).
    place(grid, maths, [(0, 2), (1, 4), (2, 6), (3, 2), (4, 2)])
    science = lesson(subject="sci", teacher="tm", klass="c2", weekly=1)
    grid.place(0, 3, science)
    tasks = [*maths, science]
    settler = Settler(grid, tasks, set(), {}, deadline=time.time() + 30)
    assert standing(grid, tasks) == (0, 0, 4)

    def licensed_move():
        grid.remove("c1", 0, 2)
        grid.place(1, 6, maths[0])
        return True

    grid.begin()
    licensed_move()
    assert standing(grid, tasks) == (1, 0, 0), "العددُ ينزل — والتوزيعُ يُكسَر"
    grid.rollback()

    assert settler.attempt(licensed_move, "move") is False
    assert grid.home_of(maths[0]) == (0, 2)
    assert standing(grid, tasks) == (0, 0, 4)

    # والسدادُ يجد الإصلاحَ الأمين: نقلةٌ داخل الأحد تفكّ التلاصقَ والتكرارَ معاً.
    result = settler.run()
    assert result["tiers_after"] == [0, 0, 0]
    assert per_day(grid) == [1, 1, 1, 1, 1]


def test_a_full_class_is_settled_by_swapping():
    """شعبةٌ لا شاغرةَ فيها: s0 حصّتين الأحد وs2 حصّتين الاثنين — والتبديلُ وحدَه يسدّهما."""
    grid, tasks = rotation(exchange=((0, 1), (2, 0)))
    assert codes(grid, tasks) == {"HC6"}

    result = settle(grid, tasks, set(), {}, deadline=time.time() + 30)

    assert result["tiers_before"] == [2, 0, 0]
    assert result["tiers_after"] == [0, 0, 0]
    assert result["moves"]["move"] == 0 and result["moves"]["swap"] >= 1
    assert per_day(grid, "s0") == per_day(grid, "s2") == [1, 1, 1, 1, 1]


def test_a_two_step_chain_when_neither_move_nor_swap_can():
    """الرياضياتُ حصّتين الأحد ولا شيءَ الاثنين، ومعلّمُها مفرَّغٌ الاثنين إلّا الرابعة
    وفيها الفنون، ومعلّمُ الفنون مفرَّغٌ في خانتَي الرياضيات الأحد. فلا نقلةَ تصحّ
    ولا تبديل — والسلسلةُ: الرياضياتُ إلى الرابعة، والفنونُ إلى شاغرة."""
    grid = ScheduleGrid()
    maths = [lesson(teacher="tm") for _ in range(5)]
    place(grid, maths, [(0, 1), (0, 3), (2, 5), (3, 5), (4, 1)])
    art = lesson(subject="art", teacher="ta", weekly=1)
    grid.place(1, 4, art)
    others = (1, 2, 3, 5, 6, 7)
    fillers = [lesson(subject=f"f{p}", teacher=f"tf{p}", weekly=1) for p in others]
    place(grid, fillers, [(1, p) for p in others])
    blocked = {("tm", 1, p) for p in others} | {("ta", 0, 1), ("ta", 0, 3)}
    tasks = [*maths, art, *fillers]
    assert codes(grid, tasks, blocked) == {"HC6"}

    result = settle(grid, tasks, blocked, {}, deadline=time.time() + 30)

    assert result["tiers_after"] == [0, 0, 0]
    assert result["moves"]["chain"] == 1
    assert result["moves"]["move"] == result["moves"]["swap"] == 0
    assert per_day(grid) == [1, 1, 1, 1, 1]
    assert grid.home_of(art) != (1, 4)
