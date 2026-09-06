"""توزيعُ حصص المعلّم بنسبٍ متقاربة على الأسبوع — ورخصةُ التلاصق تُلغى.

القيدُ كان موجوداً ولا يُلزم. ثلاثةُ أسبابٍ متراكبة، قيست على الإنتاج
2026-09-06 حين جاء محمّد صبري 4·2·3·2·4 وتفضيلُه المكتوب ثلاثٌ في اليوم:

    ١ العقوبةُ مسطّحة: خمسُ نقاطٍ للرابعة كما للسابعة، فبعد أوّل تجاوزٍ
      يصير الإثقالُ مجّاناً.
    ٢ التفضيلُ المكتوب بيد الإدارة يُوزَن كالافتراض العامّ، ووزنُه (5) دون
      الفراغ (8) والتتابع (10) — فيسقط كلّما زاحمه أحدُهما.
    ٣ الترجيحُ وقتَ الوضع لا يرى الأسبوعَ كاملاً، فلا شيءَ يُصلح يوماً عامراً
      بجانبه يومٌ خفيفٌ بعد أن يكتمل الجدول.

ومعها قرارُ 2026-09-06: لا رخصةَ تلاصقٍ للعربيّة السداسيّة — التجاورُ ضرورةٌ
لا تفضيل.
"""

import time
from types import SimpleNamespace

import pytest

from operations.models import Subject, SubjectClassAssignment
from operations.schedule_lab import load_context
from operations.scheduler import ScheduleGrid, build_tasks, generate_schedule
from operations.scheduler_constraints import (
    DEFAULT_MAX_DAILY,
    EXPLICIT_PREFERENCE_FACTOR,
    WEIGHTS,
    daily_load_weight,
)
from operations.scheduler_improve import OVERLOAD_WEIGHT, fair_share, improve, teacher_day_cost
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


# ══════════════════════ ١ العقوبة تتصاعد ══════════════════════════


def test_no_penalty_below_the_cap():
    assert daily_load_weight(2, {"max_daily": 3}) == 0
    assert daily_load_weight(DEFAULT_MAX_DAILY - 1, None) == 0


def test_the_penalty_grows_with_the_excess():
    """الرابعةُ والسابعةُ كانتا سواءً — فبعد أوّل تجاوزٍ لا شيءَ يمنع المزيد."""
    pref = {"max_daily": 3}
    at_cap = daily_load_weight(3, pref)
    one_over = daily_load_weight(4, pref)
    two_over = daily_load_weight(5, pref)

    assert at_cap < one_over < two_over
    assert one_over == at_cap * 2 and two_over == at_cap * 3


# ══════════════════════ ٢ المكتوبُ أثقلُ من الافتراض ═══════════════


def test_a_written_preference_outweighs_the_default():
    written = daily_load_weight(DEFAULT_MAX_DAILY, {"max_daily": DEFAULT_MAX_DAILY})
    default = daily_load_weight(DEFAULT_MAX_DAILY, None)

    assert written == default * EXPLICIT_PREFERENCE_FACTOR


def test_a_written_preference_now_outranks_a_gap_and_ties_adjacency():
    """السببُ المباشرُ لسقوطه: وزنُه كان دون الفراغ، فيُفتح اليومُ لئلّا يُفتح فراغ."""
    written = daily_load_weight(3, {"max_daily": 3})

    assert written > WEIGHTS["gap"]
    assert written >= WEIGHTS["consecutive"]


# ══════════════════════ ٣ نصيبُ اليوم من القسمة ════════════════════


def _grid_stub(load, days, periods_by_day, teacher="t1"):
    return SimpleNamespace(
        coverage={teacher: (load, load, frozenset(days))},
        teacher_periods_on=lambda tid, day: periods_by_day.get(day, []),
    )


def test_the_share_is_the_load_divided_by_the_days():
    grid = _grid_stub(15, range(5), {})

    assert fair_share(grid, "t1", None) == 3


def test_a_written_cap_narrows_the_share_but_never_widens_it():
    grid = _grid_stub(15, range(5), {})

    assert fair_share(grid, "t1", {"t1": {"max_daily": 2}}) == 2
    assert fair_share(grid, "t1", {"t1": {"max_daily": 6}}) == 3


def test_a_day_above_its_share_costs_more_than_the_same_day_at_its_share():
    """وبهذا تجد النقلةُ طريقَها من اليوم العامر إلى الخفيف بعد اكتمال الجدول."""
    heavy = _grid_stub(15, range(5), {0: [1, 3, 5, 7]})
    fair = _grid_stub(15, range(5), {0: [1, 3, 5]})

    over = teacher_day_cost(heavy, "t1", 0, None)
    at_share = teacher_day_cost(fair, "t1", 0, None)

    assert over - at_share >= OVERLOAD_WEIGHT


# ══════════════════════ التلاصقُ لا رخصةَ له ═══════════════════════


@pytest.fixture
def arabic_six(school):
    """معلّمُ عربيّةٍ نصابُه ستُّ حصصٍ في شعبةٍ واحدة — صاحبُ الرخصة الملغاة."""
    subject = Subject.objects.create(school=school, name_ar="اللغة العربية", code="ARA")
    teacher = UserFactory(full_name="معلّم العربيّة")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=ClassGroupFactory(
            school=school, grade="G8", level_type="prep", academic_year=YEAR
        ),
        subject=subject,
        weekly_periods=6,
        is_active=True,
    )
    return school


def test_the_task_no_longer_carries_an_adjacency_licence(arabic_six):
    tasks = build_tasks(arabic_six, YEAR)

    assert tasks, "لا مهامّ"
    assert not hasattr(tasks[0], "adjacency_allowance")


def test_arabic_six_is_not_placed_adjacent(arabic_six):
    """ستُّ حصصٍ في خمسة أيّامٍ تُفرَّق: يومٌ بحصّتين متباعدتين لا متلاصقتين."""
    result = generate_schedule(arabic_six, YEAR, publish=False)

    assert result["success"], result.get("errors")
    by_day = {}
    for slot in result["generation"].slots.all():
        by_day.setdefault(slot.day_of_week, []).append(slot.period_number)
    adjacent = [
        (day, sorted(periods))
        for day, periods in by_day.items()
        if any(
            later - earlier == 1
            for earlier, later in zip(sorted(periods), sorted(periods)[1:], strict=False)
        )
    ]

    assert not adjacent, f"تلاصقٌ باقٍ: {adjacent}"


# ══════════════════════ التحسينُ يوازن فعلاً ════════════════════════


@pytest.fixture
def one_teacher_eight_lessons(school):
    """ثمانِ حصصٍ في خمسة أيّام — نصيبُ اليوم اثنتان."""
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = UserFactory(full_name="رياضيّ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=ClassGroupFactory(
            school=school, grade="G8", level_type="prep", academic_year=YEAR
        ),
        subject=subject,
        weekly_periods=8,
        is_active=True,
    )
    return school, build_tasks(school, YEAR)


def test_the_improver_moves_a_lesson_off_an_overloaded_day(one_teacher_eight_lessons):
    """أربعٌ يومَ الأحد وواحدةٌ في كلِّ يومٍ بعده — ونصيبُ اليوم اثنتان.

    الأيّامُ كلُّها مأهولةٌ فلا يُكسر قيدُ التغطية، والفراغُ في الأحد فراغُ
    استراحةٍ لا عيب — فلولا كلفةُ الحمل الزائد لما تحرّك شيء.
    """
    school, tasks = one_teacher_eight_lessons
    teacher_id = tasks[0].members[0].teacher_id
    grid = ScheduleGrid(coverage={teacher_id: (8, 8, frozenset(range(5)))})
    for period, task in zip((1, 3, 5, 7), tasks[:4], strict=False):
        grid.place(0, period, task)
    for day, task in zip((1, 2, 3, 4), tasks[4:8], strict=False):
        grid.place(day, 1, task)
    ctx = load_context(school, YEAR)
    before = len(grid.teacher_periods_on(teacher_id, 0))

    improve(grid, tasks, set(), {}, ctx, time.time() + 30)

    after = len(grid.teacher_periods_on(teacher_id, 0))
    assert after < before, "اليومُ العامرُ بقي كما هو"
