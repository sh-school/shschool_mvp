"""توزيعُ حصص المادّة على الأيّام — بالقسمة لا بالوسم، وبلا تلاصق.

حلَّ هذا الملفُّ محلَّ `test_scheduler_spread_days.py`. كان هناك وسمٌ يُكتب على
المادّة («أيّامٌ مختلفة»، HC18) فيمنع اجتماعَ حصّتين في يوم. وقد سقط: التباعدُ
**نتيجةٌ** تحسبها القسمةُ في HC6 لا **قرارٌ** يُتَّخذ.

    perDayCap = ⌈W ÷ D⌉        daysAtCap = W mod D

فمادّةُ خمسِ حصصٍ فأقلَّ سقفُها في اليوم واحدةٌ من نفسها، ومادّةُ ستٍّ يومٌ
واحدٌ بحصّتين وأربعةٌ بحصّة. ولم يكن الوسمُ يضيف شيئاً حيث يسع النصابُ الأيّام،
وكان يعطي استحالةً مطلقةً حيث لا يسعها.

وبقي سؤالٌ واحدٌ لا تجيبه القسمة: ذلك اليومُ الواحدُ بحصّتين — أتقعان
متلاصقتين؟ وذاك HC20.
"""

import pytest

from operations.scheduler import ScheduleGrid, Task
from operations.scheduler_constraints import (
    check_subject_distribution,
    check_subject_not_adjacent,
    is_slot_valid,
)

pytestmark = pytest.mark.django_db


def task(**kw):
    fields = {
        "class_id": "c1",
        "class_name": "c1",
        "subject_id": "math",
        "subject_name": "الرياضيات",
        "subject_code": "MATH",
        "teacher_id": "t1",
        "teacher_name": "t1",
        "weekly_periods": 6,
        "level_type": "sec",
        "grade": "G11",
        "available_days": 5,
    }
    fields.update(kw)
    return Task(**fields)


class TestTheDivisionDecides:
    """السقفُ والأيّامُ البالغةُ السقف — من القسمة وحدَها."""

    @pytest.mark.parametrize(
        ("weekly", "days", "cap", "at_cap"),
        [
            (2, 5, 1, 2),  # حصّتان: يومان مختلفان
            (3, 5, 1, 3),
            (4, 5, 1, 4),
            (5, 5, 1, 5),  # خمسٌ: حصّةٌ في كلّ يوم، ولا مزدوج
            (6, 5, 2, 1),  # ستٌّ: يومٌ **واحدٌ** بحصّتين وأربعةٌ بحصّة
            (6, 4, 2, 2),  # ومعلّمٌ مفرَّغٌ يوماً: يومان بحصّتين
            (5, 4, 2, 1),  # خمسٌ على أربعةٍ: يومٌ واحدٌ بحصّتين
            (10, 5, 2, 5),  # القسمةُ بلا باقٍ: الأيّامُ كلُّها عند السقف
        ],
    )
    def test_the_cap_and_the_days_at_cap_come_from_the_division(self, weekly, days, cap, at_cap):
        subject = task(weekly_periods=weekly, available_days=days)

        assert (subject.per_day_cap, subject.days_allowed_at_cap) == (cap, at_cap)

    def test_five_periods_take_five_different_days(self):
        """ولا يحتاج وسماً: السقفُ واحدٌ من القسمة نفسِها."""
        grid = ScheduleGrid()
        five = task(weekly_periods=5)
        grid.place(1, 2, five)

        assert check_subject_distribution(grid, 1, five) is False, "اليومُ بلغ سقفَه"
        assert check_subject_distribution(grid, 2, five) is True, "واليومُ التالي مفتوح"

    def test_six_periods_are_not_impossible_in_five_days(self):
        """كان الوسمُ يجعلها مستحيلةً مطلقاً — وهي يومٌ بحصّتين وأربعةٌ بحصّة."""
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)

        assert check_subject_distribution(grid, 1, six) is True, "ثانيةٌ في اليوم تجوز"

    def test_a_second_crowded_day_is_refused(self):
        """يومٌ واحدٌ بحصّتين لا يومان — وذاك `days_allowed_at_cap`."""
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)
        grid.place(1, 4, six)
        grid.place(2, 2, six)

        assert check_subject_distribution(grid, 2, six) is False


class TestTheBlockIsTheUnit:
    """الشبكةُ تعدّ كتلاً، فالقسمةُ تقسم كتلاً — لا حصصاً."""

    def test_a_doubled_subject_is_measured_in_blocks_not_periods(self):
        """مزدوجةٌ نصابُها ستٌّ: ⌈6/5⌉ حصصاً = كتلتان = أربعُ حصصٍ في يوم."""
        doubled = task(weekly_periods=6, span=2, prefers_double=True)

        assert doubled.per_day_cap == 1, "ثلاثُ كتلٍ على خمسة أيّامٍ — كتلةٌ لليوم"

    def test_nothing_changes_for_a_single_period_task(self):
        single = task(weekly_periods=6, span=1)

        assert (single.per_day_cap, single.days_allowed_at_cap) == (2, 1)

    def test_a_four_period_double_takes_two_days(self):
        """تكنولوجيا المعلومات: كتلتان في يومين مختلفين."""
        doubled = task(weekly_periods=4, span=2, prefers_double=True)

        assert (doubled.per_day_cap, doubled.days_allowed_at_cap) == (1, 2)


class TestTheyDoNotTouch:
    """HC20 — حصّتا اليوم الواحد لا تتجاوران."""

    def test_the_neighbour_before_is_refused(self):
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)

        assert check_subject_not_adjacent(grid, 1, 3, six) is False

    def test_the_neighbour_after_is_refused(self):
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 3, six)

        assert check_subject_not_adjacent(grid, 1, 2, six) is False

    def test_a_gap_of_one_is_enough(self):
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)

        assert check_subject_not_adjacent(grid, 1, 4, six) is True

    def test_an_empty_day_never_refuses(self):
        grid = ScheduleGrid()

        assert check_subject_not_adjacent(grid, 3, 2, task()) is True

    def test_the_double_is_meant_to_touch(self):
        """تلاصقُ المزدوجة عينُ المقصود منها — فلا يُمنع."""
        grid = ScheduleGrid()
        doubled = task(weekly_periods=4, span=2, prefers_double=True)
        grid.place(1, 2, doubled)

        assert check_subject_not_adjacent(grid, 1, 4, doubled) is True

    def test_the_relaxed_licence_opens_it(self):
        """التشديدُ بلا كسرٍ جرّب فأنتج ثمانيةً وعشرين تلاصقاً وثلاثَ حصصٍ بلا موضع."""
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)

        assert check_subject_not_adjacent(grid, 1, 3, six, allow_adjacent=True) is True

    def test_another_subject_next_door_is_no_concern(self):
        grid = ScheduleGrid()
        grid.place(1, 2, task(subject_id="ar", subject_code="AR"))

        assert check_subject_not_adjacent(grid, 1, 3, task()) is True


class TestTheGateAgrees:
    """وما تقوله الدالّتان تقوله البوّابةُ الكاملة."""

    def test_the_slot_gate_refuses_the_adjacent_period(self):
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)

        assert is_slot_valid(grid, 1, 3, six) is False

    def test_the_slot_gate_accepts_a_separated_period_on_the_same_day(self):
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)

        assert is_slot_valid(grid, 1, 4, six) is True

    def test_the_slot_gate_refuses_a_third_period_in_the_day(self):
        grid = ScheduleGrid()
        six = task(weekly_periods=6)
        grid.place(1, 2, six)
        grid.place(1, 4, six)

        assert is_slot_valid(grid, 1, 6, six) is False, "السقفُ حصّتان"
