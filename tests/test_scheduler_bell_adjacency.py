"""[SCHEDULE] التلاصقُ بالساعة — الفسحةُ والصلاةُ تفصلان (SCH-18، قرارُ المالك 2026-09-24).

كان المولّدُ والمختبرُ والمحسّنُ والمدقّقُ يحكمون بالتلاصق برقم الحصّة: 13 من 46 «تلاصقاً»
في الجدول المعتمد تعبر فسحةً أو صلاةً، فتُعدّ مخالفةً وهي ليست كذلك، ويُحرَم المولّدُ
من خاناتٍ صالحةٍ خوفاً منها. والحكمُ الآن بالساعة: حصّتان متّصلتان إن كان الفاصلُ
بينهما عشرَ دقائق فأقلّ (تعريفُ المزدوجة)، ومن لا جرسَ له يُحكم برقم الحصّة كما كان.
"""

from datetime import time

from operations.scheduler import ScheduleGrid, Task
from operations.scheduler_bell import are_joined, cells_joined, grid_run, longest_run
from operations.scheduler_constraints import (
    _run_length,
    check_max_consecutive,
    check_subject_not_adjacent,
    is_slot_valid,
)

#: جرسُ الطابق الأرضيّ: الفسحةُ بعد الثالثة (عشرون دقيقة)، والصلاةُ بعد السادسة.
GROUND = {
    1: (time(7, 10), time(7, 55)),
    2: (time(8, 0), time(8, 45)),
    3: (time(8, 50), time(9, 35)),
    4: (time(9, 55), time(10, 40)),
    5: (time(10, 45), time(11, 30)),
    6: (time(11, 35), time(12, 20)),
    7: (time(12, 40), time(13, 25)),
}
#: جرسُ الطابق العلويّ: الفسحةُ بعد الرابعة — فالثالثةُ والرابعةُ متّصلتان فيه.
UPPER = {
    1: (time(7, 10), time(7, 55)),
    2: (time(8, 0), time(8, 45)),
    3: (time(8, 50), time(9, 35)),
    4: (time(9, 40), time(10, 25)),
    5: (time(10, 45), time(11, 30)),
    6: (time(11, 35), time(12, 20)),
    7: (time(12, 25), time(13, 10)),
}


def bell(**bands):
    """{(نطاق، نوعُ اليوم): {رقم: (بداية، نهاية)}} كما تقرؤه الشبكة."""
    return {(name, "regular"): times for name, times in (bands or {"": GROUND}).items()}


def task(**kw):
    fields = {
        "class_id": "c1",
        "class_name": "c1",
        "subject_id": "s1",
        "subject_name": "الرياضيات",
        "subject_code": "MAT",
        "teacher_id": "t1",
        "teacher_name": "معلّم",
        "weekly_periods": 6,
        "level_type": "prep",
        "grade": "G8",
    }
    fields.update(kw)
    return Task(**fields)


def other_class(**kw):
    """حصّةٌ لمعلّمٍ في شعبةٍ ومادّةٍ أخرى — فالمانعُ تلاصقُه هو لا قسمةُ مادّة."""
    fields = {"class_id": "c2", "class_name": "c2", "subject_id": "s2", "subject_name": "العلوم"}
    fields.update(kw)
    return task(**fields)


# ── الحكمُ نفسُه ─────────────────────────────────────────────────────


def test_a_break_separates_two_lessons_and_a_bell_gap_does_not():
    assert are_joined(GROUND[2], GROUND[3]) is True, "خمسُ دقائقَ انتقالٌ لا استراحة"
    assert are_joined(GROUND[3], GROUND[4]) is False, "فسحةٌ عشرون دقيقة"
    assert are_joined(GROUND[6], GROUND[7]) is False, "صلاة"
    assert are_joined(None, GROUND[4]) is True, "بلا جرسٍ يُحكم بالرقم"


def test_the_longest_run_stops_at_a_break():
    interval_of = lambda _band, period: GROUND[period]  # noqa: E731

    assert longest_run([(2, ""), (3, "")], interval_of) == 2
    assert longest_run([(3, ""), (4, "")], interval_of) == 1, "الفسحة"
    assert longest_run([(2, ""), (3, ""), (4, ""), (5, "")], interval_of) == 2
    assert longest_run([(6, ""), (7, "")], interval_of) == 1, "الصلاة"
    assert longest_run([], interval_of) == 0


def test_without_a_bell_the_number_decides_as_before():
    silent = lambda _band, _period: None  # noqa: E731

    assert longest_run([(3, ""), (4, "")], silent) == 2


def test_each_band_is_judged_by_its_own_bell():
    """الثالثةُ في الأرضيّ والرابعةُ في العلويّ: 9:35 ثمّ 9:40 — متّصلتان."""
    grid = ScheduleGrid(band_times=bell(ground=GROUND, upper=UPPER))

    assert cells_joined(grid, 0, 3, "ground", 4, "ground") is False
    assert cells_joined(grid, 0, 3, "upper", 4, "upper") is True
    assert cells_joined(grid, 0, 3, "ground", 4, "upper") is True
    assert cells_joined(grid, 0, 4, "upper", 3, "ground") is True, "الترتيبُ لا يهمّ"


# ── القيدُ الصلب HC5 ─────────────────────────────────────────────────


def test_a_teacher_may_teach_either_side_of_the_break_but_not_two_joined_lessons():
    grid = ScheduleGrid(band_times=bell())
    grid.place(0, 3, other_class())

    assert _run_length(grid, "t1", 0, 4) == 0, "الفسحةُ تفصل"
    assert is_slot_valid(grid, 0, 4, task()) is True
    assert _run_length(grid, "t1", 0, 2) == 1, "خمسُ دقائقَ لا تفصل"
    assert is_slot_valid(grid, 0, 2, task()) is False


def test_the_prayer_separates_the_sixth_and_the_seventh():
    grid = ScheduleGrid(band_times=bell())
    grid.place(0, 6, other_class())

    assert check_max_consecutive(grid, 0, 7, task()) is True
    assert check_max_consecutive(grid, 0, 5, task()) is False


def test_a_chain_is_cut_at_the_break_not_only_at_the_first_step():
    """2-3 متّصلتان ثمّ فسحةٌ ثمّ 4: من وضع 4 لا يُعدّ خلفه رتلاً."""
    grid = ScheduleGrid(band_times=bell())
    grid.place(0, 2, other_class())
    grid.place(0, 3, other_class(class_id="c3", class_name="c3"))

    assert _run_length(grid, "t1", 0, 4) == 0
    assert _run_length(grid, "t1", 0, 1) == 2


def test_without_a_bell_the_hard_constraint_is_unchanged():
    grid = ScheduleGrid()
    grid.place(0, 3, other_class())

    assert _run_length(grid, "t1", 0, 4) == 1
    assert is_slot_valid(grid, 0, 4, task()) is False


# ── الترجيحُ والمحسّنُ والمدقّق ───────────────────────────────────────


def test_the_soft_counter_does_not_count_across_a_break():
    grid = ScheduleGrid(band_times=bell())
    grid.place(0, 3, other_class())

    assert grid.teacher_consecutive_counted("t1", 0, 4) == 0
    assert grid.teacher_consecutive_counted("t1", 0, 2) == 1


def test_the_optimizer_reads_the_run_by_the_clock():
    across = ScheduleGrid(band_times=bell())
    across.place(0, 3, task())
    across.place(0, 4, other_class())
    joined = ScheduleGrid(band_times=bell())
    joined.place(0, 2, task())
    joined.place(0, 3, other_class())

    assert grid_run(across, "t1", 0) == 1
    assert grid_run(joined, "t1", 0) == 2


def test_a_lesson_pair_across_the_break_is_not_a_breach_for_the_auditor():
    from operations.scheduler_audit import grid_breaches

    grid = ScheduleGrid(band_times=bell())
    first, second = task(), other_class()
    grid.place(0, 3, first)
    grid.place(0, 4, second)

    assert [b for b in grid_breaches(grid, [first, second]) if b.code == "HC5"] == []

    joined = ScheduleGrid(band_times=bell())
    third, fourth = task(), other_class()
    joined.place(0, 2, third)
    joined.place(0, 3, fourth)

    assert {b.code for b in grid_breaches(joined, [third, fourth])} >= {"HC5"}


# ── حصّتا المادّة في اليوم (HC20) ────────────────────────────────────


def test_two_lessons_of_a_subject_across_the_break_are_not_adjacent():
    grid = ScheduleGrid(band_times=bell())
    grid.place(0, 3, task())

    assert check_subject_not_adjacent(grid, 0, 4, task()) is True, "الفسحةُ تفصل"
    assert check_subject_not_adjacent(grid, 0, 2, task()) is False, "متّصلتان"


def test_the_subject_pair_is_judged_by_number_when_no_bell_is_known():
    grid = ScheduleGrid()
    grid.place(0, 3, task())

    assert check_subject_not_adjacent(grid, 0, 4, task()) is False
