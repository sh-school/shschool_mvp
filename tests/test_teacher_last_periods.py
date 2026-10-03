"""[SCHEDULE] سقفُ السابعة الشخصيّ (HC8): معلّمٌ نصابُه يفوق سعتَه بسابعتين لا يُسَع إلّا بثالثة (W-20261003-035، D-172م).

السقفُ العامّ اثنتان (`MAX_LAST_PERIODS`)، ومن كُتب له `TeacherPreference.max_last_periods` يحمله `Member.last_cap`
ويقرؤه `check_last_period_share`. والشرطُ الثاني — ألّا تتكرّر السابعةُ على الشعبة نفسِها — لا يلين بالسقف الشخصيّ.
"""

from operations.scheduler import ScheduleGrid
from operations.scheduler_constraints import LAST_PERIOD, check_last_period_share
from tests.test_scheduler_audit import lesson


def seventh(grid, teacher, klass, day):
    grid.place(day, LAST_PERIOD, lesson(klass, f"s-{klass}", teacher, weekly=1))


def two_sevenths():
    grid = ScheduleGrid()
    seventh(grid, "t-1", "c-1", 0)
    seventh(grid, "t-1", "c-2", 1)
    return grid


def test_the_default_cap_is_two_sevenths():
    grid = two_sevenths()

    assert (
        check_last_period_share(grid, LAST_PERIOD, lesson("c-3", "s-x", "t-1", weekly=1)) is False
    )


def test_a_personal_cap_of_three_admits_the_third_and_stops_at_it():
    grid = two_sevenths()
    third = lesson("c-3", "s-x", "t-1", weekly=1)
    third.members[0].last_cap = 3
    assert check_last_period_share(grid, LAST_PERIOD, third) is True

    grid.place(2, LAST_PERIOD, third)
    fourth = lesson("c-4", "s-y", "t-1", weekly=1)
    fourth.members[0].last_cap = 3
    assert check_last_period_share(grid, LAST_PERIOD, fourth) is False


def test_the_personal_cap_never_lets_a_class_carry_the_seventh_twice():
    grid = ScheduleGrid()
    seventh(grid, "t-1", "c-1", 0)
    again = lesson("c-1", "s-y", "t-1", weekly=1)
    again.members[0].last_cap = 3

    assert check_last_period_share(grid, LAST_PERIOD, again) is False


def test_another_teachers_cap_does_not_raise_mine():
    grid = two_sevenths()
    mine = lesson("c-3", "s-x", "t-1", weekly=1)  # بلا سقفٍ شخصيّ

    assert check_last_period_share(grid, LAST_PERIOD, mine) is False


def test_an_out_of_range_cap_is_read_as_absent_not_as_a_waiver():
    """شرطُ 0105: إدخالٌ مباشرٌ بالـORM (0 أو 99 أو سالب) لا يلغي HC8."""
    from operations.last_period_cap import personal_last_cap

    assert [personal_last_cap(v) for v in (None, 0, -1, 6, 99, True)] == [0] * 6
    assert [personal_last_cap(v) for v in (1, 3, 5)] == [1, 3, 5]

    grid = two_sevenths()
    task = lesson("c-3", "s-x", "t-1", weekly=1)
    task.members[0].last_cap = 99
    assert check_last_period_share(grid, LAST_PERIOD, task) is False


def test_only_the_seventh_period_is_judged():
    grid = two_sevenths()

    assert check_last_period_share(grid, 3, lesson("c-3", "s-x", "t-1", weekly=1)) is True
