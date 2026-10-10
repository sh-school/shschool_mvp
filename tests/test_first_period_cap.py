"""[SCHEDULE] سقفُ الحصّة الأولى لكلّ معلّم (HC22): ≤ ٢ أسبوعيّاً، صلبٌ قابلٌ للضبط (W-20261003-043، D-166م وD-183م).

توأمُ HC8 (السابعة). كان مرمَّزاً في V2 وحدَه؛ فسُجّل في السجلّ وأُدخل في المدقّق الرسميّ (فيراه المُقيِّمُ المستقلّ)
وفي فحص الجدوى. وهنا الجزءُ الذي لا يحتاج قاعدة: السجلّ والفحصُ على الشبكة والتكافؤ مع V2.
"""

from operations import constraint_registry as cr
from operations.scheduler import ScheduleGrid
from operations.scheduler_audit import grid_breaches
from operations.scheduler_constraints import (
    FIRST_PERIOD,
    MAX_FIRST_PERIODS,
    MAX_LAST_PERIODS,
    check_first_period_share,
    slot_violations,
)
from operations.scheduler_v2.model import ModelOptions
from tests.test_scheduler_audit import lesson


def first(grid, teacher, klass, day):
    grid.place(day, FIRST_PERIOD, lesson(klass, f"s-{klass}", teacher, weekly=1))


def two_firsts():
    grid = ScheduleGrid()
    first(grid, "t-1", "c-1", 0)
    first(grid, "t-1", "c-2", 1)
    return grid


def test_the_cap_is_two_and_matches_the_last_period_cap_and_v2():
    assert MAX_FIRST_PERIODS == 2
    assert MAX_FIRST_PERIODS == MAX_LAST_PERIODS
    opt = ModelOptions()
    assert (opt.first_cap, opt.last_cap) == (MAX_FIRST_PERIODS, MAX_LAST_PERIODS)


def test_the_third_first_period_is_refused_and_two_are_admitted():
    grid = ScheduleGrid()
    assert check_first_period_share(grid, FIRST_PERIOD, lesson("c-1", "s-x", "t-1", weekly=1))
    first(grid, "t-1", "c-1", 0)
    assert check_first_period_share(grid, FIRST_PERIOD, lesson("c-2", "s-x", "t-1", weekly=1))

    assert (
        check_first_period_share(two_firsts(), FIRST_PERIOD, lesson("c-3", "s-x", "t-1", weekly=1))
        is False
    )


def test_only_the_first_period_is_judged():
    grid = two_firsts()

    for period in range(2, 8):
        assert check_first_period_share(grid, period, lesson("c-3", "s-x", "t-1", weekly=1))


def test_another_teachers_firsts_do_not_count():
    assert check_first_period_share(
        two_firsts(), FIRST_PERIOD, lesson("c-3", "s-x", "t-2", weekly=1)
    )


def test_a_declared_first_cap_raises_one_teacher_alone():
    """تخفيفُ المالك المعلَن (first_cap_override في V2) يصل المدقّقَ على عضو المهمّة؛ وغيابُه يعني العامّ."""
    grid = two_firsts()
    third = lesson("c-3", "s-x", "t-1", weekly=1)
    third.members[0].first_cap = 4

    assert check_first_period_share(grid, FIRST_PERIOD, third) is True
    third.members[0].first_cap = 0
    assert check_first_period_share(grid, FIRST_PERIOD, third) is False


def test_slot_violations_names_hc22_for_the_third_first():
    third = lesson("c-3", "s-x", "t-1", weekly=1)

    assert "HC22" in slot_violations(two_firsts(), 2, FIRST_PERIOD, third)
    assert "HC22" not in slot_violations(two_firsts(), 2, 2, third)


def test_the_official_audit_counts_one_breach_per_teacher_not_per_lesson():
    grid = ScheduleGrid()
    tasks = [lesson(f"c-{k}", f"s-{k}", "t-1", weekly=1) for k in range(4)]
    for day, task in enumerate(tasks):
        grid.place(day, FIRST_PERIOD, task)

    keys = [b.key for b in grid_breaches(grid, tasks) if b.code == "HC22"]

    assert keys == [("HC22", ("t-1",))]


def test_hc22_is_registered_as_a_hard_constraint_with_its_decision_source():
    spec = cr.REGISTRY["HC22"]

    assert spec in cr.HARD_CONSTRAINTS
    assert spec.break_at == cr.NEVER, "كأخيه HC8: لا رخصةَ جولة"
    assert spec.source.startswith("قرار:") and "D-166م" in spec.source and "D-183م" in spec.source
    assert cr.default_policy().break_at("HC22") == cr.NEVER
