"""[SCHEDULE] توزيعُ المادّة على الأسبوع: حصّةٌ كلَّ يوم، والفائضُ يومٌ مزدوج.

القاعدةُ التربويّةُ كما قرّرها صاحبُ الشأن:

    مادّةٌ بستّ حصصٍ في أسبوعٍ خماسيّ  →  خمسةُ أيّامٍ بحصّة، ويومٌ واحدٌ بحصّتين
    فإن كان معلّمُها مفرَّغاً يوماً      →  أربعةُ أيّام، فيومان بحصّتين

وصيغتُها العامّة قسمةٌ لا استثناء:

    perDayCap   = ⌈W / D⌉
    daysAtCap   = W mod D        (وإن قسمت بلا باقٍ فالأيّامُ كلُّها سواء)

حيث `D` أيّامُ المعلّم المتاحةُ بعد تفريغاته. فليست «حصّتان في اليوم» مخالفةً
ولا استثناءً، بل هي ما تقتضيه القسمةُ حين لا يقبل النصابُ التوزيعَ المتساوي.

وكان الوزنُ المرنُ `subject_spread` يعاقب **كلَّ** حصّةٍ ثانيةٍ في اليوم، فسجّل
٧٩٢ «مخالفة» في جدولٍ صحيح — لأنّ كلَّ مادّةٍ سداسيّةٍ يلزمها يومٌ مزدوجٌ
بالضرورة. فكان المقياسُ يعاقب الصوابَ ويسمّيه خطأً.
"""

import math
from collections import Counter

import pytest

from operations.scheduler import DAYS, ScheduleGrid, Task
from operations.scheduler_constraints import is_slot_valid

pytestmark = pytest.mark.django_db

CLASS = "c-1"
SUBJECT = "s-1"


def task(*, weekly=6, days=5, teacher="t-1", subject=SUBJECT, klass=CLASS, code="MAT"):
    return Task(
        class_id=klass,
        class_name="شعبة",
        subject_id=subject,
        subject_name="مادّة",
        subject_code=code,
        teacher_id=teacher,
        teacher_name="معلّم",
        weekly_periods=weekly,
        level_type="prep",
        available_days=days,
    )


def fill(grid, *, weekly, days, per_day):
    """يضع حصصاً بحسب خريطةٍ {يوم: عدد} — للتهيئة لا للاختبار."""
    period = 1
    for day, count in per_day.items():
        for _ in range(count):
            grid.place(day, period, task(weekly=weekly, days=days))
            period += 1


# ── الصيغةُ نفسُها ───────────────────────────────────────────────────


def test_the_cap_is_the_ceiling_of_the_share():
    """ستٌّ على خمسةٍ سقفُها حصّتان، وعلى أربعةٍ سقفُها حصّتان أيضاً."""
    assert math.ceil(6 / 5) == 2
    assert math.ceil(6 / 4) == 2
    assert math.ceil(5 / 5) == 1


# ── حصّةٌ كلَّ يومٍ ويومٌ مزدوجٌ واحد ─────────────────────────────────


def test_a_sixth_period_forces_exactly_one_doubled_day():
    """أربعةُ أيّامٍ بحصّةٍ ويومٌ بحصّتين — والثاني المزدوجُ مرفوض."""
    grid = ScheduleGrid()
    fill(grid, weekly=6, days=5, per_day={0: 1, 1: 1, 2: 1, 3: 1, 4: 2})

    # اليومُ الرابعُ بلغ سقفَه، ولا يوم ثانٍ يجوز أن يبلغه.
    assert not is_slot_valid(grid, 4, 6, task()), "لا ثالثةَ في اليوم المزدوج"
    for day in (0, 1, 2, 3):
        assert not is_slot_valid(grid, day, 6, task()), "ولا يومَ مزدوجٌ ثانٍ"


def test_the_second_period_of_a_day_is_allowed_while_the_quota_stands():
    """اليومُ المزدوجُ الأوّلُ مسموح — فهو ما تقتضيه القسمة."""
    grid = ScheduleGrid()
    fill(grid, weekly=6, days=5, per_day={0: 1, 1: 1, 2: 1, 3: 1, 4: 1})

    assert is_slot_valid(grid, 4, 6, task()), "السادسةُ تقع في يومٍ يصير مزدوجاً"


def test_no_day_ever_takes_three():
    grid = ScheduleGrid()
    fill(grid, weekly=6, days=5, per_day={0: 2})

    assert not is_slot_valid(grid, 0, 6, task())


# ── المعلّمُ المفرَّغُ يوماً: يومان مزدوجان ───────────────────────────


def test_an_exempt_teacher_gets_two_doubled_days():
    """ستُّ حصصٍ في أربعة أيّام: 2 + 2 + 1 + 1 — ويومان يبلغان السقف."""
    grid = ScheduleGrid()
    four_days = {"weekly": 6, "days": 4}
    fill(grid, **four_days, per_day={1: 2, 2: 1, 3: 1})

    assert is_slot_valid(grid, 2, 6, task(weekly=6, days=4)), "اليومُ المزدوجُ الثاني مسموح"

    fill(grid, **four_days, per_day={2: 1})
    assert not is_slot_valid(grid, 3, 6, task(weekly=6, days=4)), "ولا ثالثَ"


def test_the_evenly_divisible_case_puts_one_a_day():
    """خمسٌ على خمسةٍ: حصّةٌ لكلّ يومٍ ولا مزدوجَ البتّة."""
    grid = ScheduleGrid()
    fill(grid, weekly=5, days=5, per_day={0: 1})

    assert not is_slot_valid(grid, 0, 6, task(weekly=5)), "لا حاجةَ ليومٍ مزدوج"
    assert is_slot_valid(grid, 1, 6, task(weekly=5))


def test_a_light_subject_spreads_before_it_doubles():
    """حصّتان في الأسبوع: يومان مختلفان، لا يومٌ واحدٌ بحصّتين."""
    grid = ScheduleGrid()
    fill(grid, weekly=2, days=5, per_day={0: 1})

    assert not is_slot_valid(grid, 0, 6, task(weekly=2))
    assert is_slot_valid(grid, 1, 6, task(weekly=2))


# ── القاعدةُ تخصّ الشعبةَ والمادّة، لا الشعبةَ وحدَها ────────────────


def test_another_subject_is_not_constrained_by_this_one():
    grid = ScheduleGrid()
    fill(grid, weekly=6, days=5, per_day={0: 2})

    other = task(subject="s-2", teacher="t-2")

    assert is_slot_valid(grid, 0, 6, other), "لكلّ مادّةٍ توزيعُها"


# ── على مولّدٍ كامل ──────────────────────────────────────────────────


def test_a_generated_week_follows_the_rule(school):
    """ستُّ حصصٍ لمادّةٍ في شعبة: أربعةُ آحادٍ ويومٌ مزدوجٌ واحد."""
    from operations.models import Subject, SubjectClassAssignment
    from operations.scheduler import generate_schedule
    from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year="2026-2027")
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year="2026-2027",
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=6,
        is_active=True,
    )

    result = generate_schedule(school, "2026-2027")

    assert result["success"], result["errors"][:3]
    per_day = Counter(e["day"] for e in result["grid"].all_entries())
    assert sorted(per_day.values()) == [1, 1, 1, 1, 2], f"التوزيع {dict(per_day)}"
    assert len(per_day) == len(DAYS)
