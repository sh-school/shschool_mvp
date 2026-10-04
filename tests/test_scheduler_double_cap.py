"""[SCHEDULE] سقفُ المادّة في اليوم بالكتل لا بالحصص — مزدوجاتٌ بنصابٍ ستٍّ فأكثر (W-20260930-003).

    perDayCap = ⌈W / D⌉        daysAtCap = W mod D        (W بالكتل: كتلةٌ لكلّ `span` حصص)

`ScheduleGrid` يعدّ المهمّةَ الموضوعةَ كتلةً واحدةً مهما طالت، فلو قُسمت **الحصصُ** على الأيّام كان السقفُ
بوحدةٍ غيرِ وحدة العدّاد: صحيحاً بالمصادفة لنصابٍ أربعٍ فأقلّ، وخاطئاً عند ستٍّ — ⌈6/5⌉ = كتلتان = أربعُ حصصٍ
في يومٍ واحد، والمطلوب كتلةٌ لكلّ يوم (حصّتان). وكان الخللُ صامتاً: لا خطأ، تُوضَع أربعُ حصصٍ في يومٍ وتُترك
أيّامٌ فارغة. وهذه الاختباراتُ تُثبت السقفَ بمزدوجاتٍ على الدالّة نفسِها وعلى توليدٍ حقيقيّ.
"""

from datetime import time

import pytest

from operations.models import ScheduleSlot, Subject, SubjectClassAssignment, TimeSlotConfig
from operations.scheduler import ScheduleGrid, Task, generate_schedule
from operations.scheduler_constraints import check_subject_distribution
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


def double_task(*, weekly, days=5, teacher="t1", klass="c1", subject="art"):
    return Task(
        teacher_id=teacher,
        class_id=klass,
        subject_id=subject,
        subject_code="",
        subject_name="الفنون",
        class_name="7/1",
        teacher_name="معلّم",
        weekly_periods=weekly,
        level_type="prep",
        span=2,
        available_days=days,
    )


# ── الدالّةُ نفسُها: السقفُ وأيّامُ بلوغه بالكتل ───────────────────────────


@pytest.mark.parametrize(
    ("weekly", "days", "cap", "days_at_cap"),
    [
        (2, 5, 1, 1),  # كتلةٌ واحدة
        (4, 5, 1, 2),  # كتلتان: يومان
        (6, 5, 1, 3),  # ثلاثُ كتل: كانت تُحسب 2 فتجمع كتلتين في يومٍ (أربعَ حصص)
        (8, 5, 1, 4),
        (10, 5, 1, 5),  # خمسُ كتلٍ على خمسة أيّام: كتلةٌ لكلّ يوم
        (12, 5, 2, 1),  # ستُّ كتل: يومٌ واحدٌ بكتلتين (أربعُ حصص)
        (6, 4, 1, 3),  # معلّمٌ مفرَّغٌ يوماً: ثلاثُ كتلٍ في أربعة أيّام
        (12, 4, 2, 2),
    ],
)
def test_the_cap_and_days_at_cap_count_blocks_not_periods(weekly, days, cap, days_at_cap):
    task = double_task(weekly=weekly, days=days)

    assert task.per_day_cap == cap
    assert task.days_allowed_at_cap == days_at_cap


def test_six_double_periods_never_put_two_blocks_in_one_day():
    """ستُّ حصصٍ مزدوجة = ثلاثُ كتل: الثانيةُ ترفضها القسمةُ على اليوم نفسِه، وتقبلها الأيّامُ الأخرى."""
    grid = ScheduleGrid()
    grid.place(0, 1, double_task(weekly=6))

    second = double_task(weekly=6)

    assert not check_subject_distribution(
        grid, 0, second
    ), "كتلتان في اليوم = أربعُ حصصٍ — خطأ القسمة بالحصص"
    assert check_subject_distribution(grid, 1, second)


def test_three_blocks_spread_over_three_days_and_a_fourth_day_is_refused():
    """القسمةُ شرطان: لا يومَ فوق السقف، ولا عددَ أيّامٍ عند السقف فوق حصّته (3 كتلٍ = 3 أيّام)."""
    grid = ScheduleGrid()
    for day in (0, 1, 2):
        task = double_task(weekly=6)
        assert check_subject_distribution(grid, day, task), f"اليوم {day}"
        grid.place(day, 1, task)

    assert not check_subject_distribution(grid, 3, double_task(weekly=6)), "الرابعةُ فوق حصّة المادّة"


def test_the_last_round_license_allows_one_extra_block_in_a_day():
    """رخصةُ الجولة الأخيرة (`allow_dense`): كتلةٌ زائدةٌ في يومٍ — لا أكثر."""
    grid = ScheduleGrid()
    grid.place(0, 1, double_task(weekly=6))

    assert check_subject_distribution(grid, 0, double_task(weekly=6), allow_dense=True)
    grid.place(0, 3, double_task(weekly=6))
    assert not check_subject_distribution(grid, 0, double_task(weekly=6), allow_dense=True)


def test_the_grid_counts_one_block_per_double_not_one_per_period():
    """الأصلُ الذي بُني عليه السقف: عدّادُ المادّة في اليوم بالكتل — فمزدوجةٌ واحدةٌ = 1 لا 2."""
    grid = ScheduleGrid()
    task = double_task(weekly=12)

    grid.place(0, 1, task)
    assert grid.subject_on_day("c1", "art", 0) == 1

    grid.remove("c1", 0, 2)  # من نصفها الثاني: تُرفع المزدوجةُ كلُّها
    assert grid.subject_on_day("c1", "art", 0) == 0


def test_twelve_double_periods_fill_five_days_then_double_one_day():
    """ستُّ كتل: خمسةُ أيّامٍ بكتلةٍ ويومٌ بكتلتين — لا كتلةَ سادسة تضيع صامتةً لأنّ السقفَ نصّفه العدّ بالخانات."""
    grid = ScheduleGrid()
    for day in range(5):
        task = double_task(weekly=12)
        assert check_subject_distribution(grid, day, task), f"اليوم {day}"
        grid.place(day, 1, task)

    sixth = double_task(weekly=12)

    assert check_subject_distribution(grid, 0, sixth), "اليومُ الواحد المسموح بكتلتين (السقفُ 2)"
    grid.place(0, 3, sixth)
    assert not check_subject_distribution(grid, 1, double_task(weekly=12)), "ولا يومٌ ثانٍ بكتلتين"


# ── توليدٌ حقيقيّ ───────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("weekly", "expected"),
    [(6, [2, 2, 2]), (8, [2, 2, 2, 2]), (12, [2, 2, 2, 2, 4])],
)
def test_a_generated_double_lands_by_blocks_per_day(school, weekly, expected):
    for period, (start, end) in enumerate(
        [("07:10", "07:55"), ("08:00", "08:45"), ("08:50", "09:35"), ("09:55", "10:40"),
         ("10:45", "11:30"), ("11:45", "12:30"), ("12:35", "13:20")],
        start=1,
    ):  # fmt: skip
        for day_type in ("regular", "thursday"):
            TimeSlotConfig.objects.create(
                school=school,
                period_number=period,
                start_time=time(*map(int, start.split(":"))),
                end_time=time(*map(int, end.split(":"))),
                day_type=day_type,
            )
    teacher = UserFactory(full_name="معلّمُ الفنون")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    art = Subject.objects.create(
        school=school, name_ar="الفنون البصرية", code="", requires_double_period=True
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=art,
        weekly_periods=weekly,
        is_active=True,
    )

    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    per_day: dict[int, int] = {}
    for row in ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True):
        per_day[row.day_of_week] = per_day.get(row.day_of_week, 0) + 1
    assert sum(per_day.values()) == weekly
    assert sorted(per_day.values()) == expected, f"توزيعُ الكتل على الأيّام: {per_day}"
