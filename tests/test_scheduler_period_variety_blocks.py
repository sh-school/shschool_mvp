"""[SCHEDULE] تنويعُ الحصّة (HC7) بالكتلة عند موضع بدايتها لا بكلّ خانةٍ تغطّيها (W-20261002-014).

`check_period_variety` يسأل عن **موضع بداية** الكتلة، بينما كان عدّادُه `_subject_period` يزيد لكلّ خانةٍ تغطّيها —
فالمزدوجةُ تُحسب على حصّتَيها وتضيق مواضعُ البدء الأربعةُ (ح1، ح2، ح4، ح6) فتتعذّر كتلةٌ من نصاب 12 مزدوجة برسالة «لا تُكدَّس
المادّةُ في حصّةٍ واحدةٍ من اليوم». صار العدّادُ بموضع البداية — وحدةٌ واحدةٌ مع السؤال، ومع عدّاد اليوم في W-20260930-003.
والمفردةُ بدايتُها هي خانتُها فلا يتغيّر حكمُها. وسقفُ المرّتين (`MAX_SAME_PERIOD`) باقٍ كما هو.
"""

from operations.scheduler import ScheduleGrid, Task
from operations.scheduler_constraints import MAX_SAME_PERIOD, check_period_variety


def block(*, span, klass="c1", subject="art"):
    return Task(
        teacher_id="t1",
        class_id=klass,
        subject_id=subject,
        subject_code="",
        subject_name="الفنون",
        class_name="7/1",
        teacher_name="معلّم",
        weekly_periods=12 if span == 2 else 4,
        level_type="prep",
        span=span,
    )


def test_a_double_counts_at_its_start_period_only():
    grid = ScheduleGrid()

    grid.place(0, 1, block(span=2))

    assert grid.subject_at_period("c1", "art", 1) == 1
    assert grid.subject_at_period("c1", "art", 2) == 0, "الحصّةُ الثانيةُ ليست موضعَ بداية"


def test_removing_a_double_from_its_second_half_restores_its_start_count():
    grid = ScheduleGrid()
    grid.place(0, 4, block(span=2))

    grid.remove("c1", 0, 5)  # من نصفها الثاني: تُرفع المزدوجةُ كلُّها

    assert grid.subject_at_period("c1", "art", 4) == 0
    assert grid.subject_at_period("c1", "art", 5) == 0


def test_two_doubles_starting_at_one_no_longer_block_a_double_starting_at_two():
    """قبلُ: (ح1،ح2) مرّتين ترفع عدّاد ح2 إلى 2 فتُرفض (ح2،ح3) ظلماً — والبدءان مختلفان."""
    grid = ScheduleGrid()
    grid.place(0, 1, block(span=2))
    grid.place(1, 1, block(span=2))

    assert check_period_variety(grid, 2, block(span=2))


def test_the_cap_of_two_per_start_period_still_holds_for_doubles():
    grid = ScheduleGrid()
    for day in range(MAX_SAME_PERIOD):
        grid.place(day, 4, block(span=2))

    assert not check_period_variety(grid, 4, block(span=2)), "الثالثةُ على البداية نفسِها مرفوضة"
    assert check_period_variety(grid, 6, block(span=2)), "وبدايةٌ أخرى متاحة"


def test_singles_are_unchanged_the_same_period_at_most_twice():
    grid = ScheduleGrid()
    for day in range(MAX_SAME_PERIOD):
        grid.place(day, 3, block(span=1))

    assert grid.subject_at_period("c1", "art", 3) == MAX_SAME_PERIOD
    assert not check_period_variety(grid, 3, block(span=1))
    assert check_period_variety(grid, 4, block(span=1))


def test_another_class_or_subject_does_not_share_the_count():
    grid = ScheduleGrid()
    grid.place(0, 4, block(span=2))
    grid.place(1, 4, block(span=2))

    assert check_period_variety(grid, 4, block(span=2, klass="c2"))
    assert check_period_variety(grid, 4, block(span=2, subject="sci"))
