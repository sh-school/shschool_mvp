"""لا يومَ فارغاً لمعلّم — إلّا بتفريغٍ من الإعدادات (HC14).

قرارُ الإدارة 2026-09-04: حصصُ المعلّم على الأيّام الخمسة كلِّها بنسبٍ
متقاربة، ولا يومَ بلا حصّةٍ إلّا من فُرّغ يومَه في إعدادات الجدول. ومن نصابُه
دون عدد أيّامه (منسّقٌ بأربع حصص) مستثنىً بالضرورة.
"""

import pytest

from operations.models import Subject, SubjectClassAssignment, TeacherExemption
from operations.scheduler import DAYS, ScheduleGrid, Task, generate_schedule
from operations.scheduler_constraints import check_day_coverage
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"
ALL_DAYS = frozenset(DAYS)


def task(teacher="t1", klass="c1", n=0):
    return Task(
        class_id=klass,
        class_name=klass,
        subject_id="s",
        subject_name="مادّة",
        subject_code="S",
        teacher_id=teacher,
        teacher_name=teacher,
        weekly_periods=5,
    )


def test_a_period_is_reserved_for_every_empty_day():
    """نصابٌ خمسٌ على خمسة أيّام: الثانيةُ في يومٍ عامرٍ تسرق يوماً فارغاً."""
    grid = ScheduleGrid(coverage={"t1": (5, 5, ALL_DAYS)})
    grid.place(0, 1, task())

    assert check_day_coverage(grid, 0, 3, task()) is False, "الأحدُ عامرٌ وأربعةُ أيّامٍ فارغة"
    assert check_day_coverage(grid, 1, 3, task()) is True


def test_surplus_periods_may_double_a_day():
    """نصابٌ سبعٌ: بعد تغطية الأيّام الخمسة تبقى اثنتان حرّتان."""
    grid = ScheduleGrid(coverage={"t1": (7, 7, ALL_DAYS)})
    grid.place(0, 1, task())

    assert check_day_coverage(grid, 0, 3, task()) is True, "الباقي 5 يكفي أربعةَ أيّامٍ فارغة"
    grid.place(0, 3, task())
    assert check_day_coverage(grid, 0, 5, task()) is True, "الباقي 4 يكفي أربعةً بالضبط"
    grid.place(0, 5, task())
    assert check_day_coverage(grid, 0, 7, task()) is False, "الباقي 3 لا يكفي أربعةً"


def test_a_light_load_is_exempt_from_the_rule():
    grid = ScheduleGrid(coverage={"t1": (3, 3, ALL_DAYS)})
    grid.place(0, 1, task())

    assert check_day_coverage(grid, 0, 3, task()) is True


def test_a_released_day_is_not_counted():
    """يومُ تفريغٍ من الإعدادات ليس من أيّامه — فلا يُطلب ملؤه."""
    grid = ScheduleGrid(coverage={"t1": (4, 4, frozenset({0, 1, 2, 3}))})
    grid.place(0, 1, task())

    assert check_day_coverage(grid, 0, 3, task()) is False, "ثلاثةٌ لثلاثة أيّامٍ فارغة"
    assert check_day_coverage(grid, 4, 3, task()) is True, "الخميسُ مفرَّغٌ فلا يحكمه القيد"


def test_three_double_blocks_cannot_cover_five_days_so_the_rule_steps_aside():
    """ستُّ حصصٍ في ثلاث مزدوجات: ثلاثةُ مواضعَ لا تغطّي خمسةَ أيّام — كقليل الحصص."""
    grid = ScheduleGrid(coverage={"t1": (3, 6, ALL_DAYS)})
    double = task()
    double.span = 2
    grid.place(0, 1, double)

    assert grid.teacher_placed("t1") == 1, "موضعٌ واحدٌ وإن شغل خانتين"
    assert check_day_coverage(grid, 0, 4, task()) is True


def test_without_coverage_the_rule_is_silent():
    grid = ScheduleGrid()
    grid.place(0, 1, task())
    assert check_day_coverage(grid, 0, 3, task()) is True


# ── توليدٌ كامل ────────────────────────────────────────────────────


def _teacher(school, name, role="teacher"):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _assign(school, group, user, subject, periods):
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=user,
        class_group=group,
        subject=subject,
        weekly_periods=periods,
        is_active=True,
    )


def test_generated_schedule_covers_every_day_for_full_load_teachers(school):
    """معلّمٌ بستّ حصصٍ في شعبةٍ واحدة: حصّةٌ كلَّ يوم — لا خميسَ فارغاً."""
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    subjects = {
        code: Subject.objects.create(school=school, name_ar=name, code=code)
        for code, name in (("MAT", "الرياضيات"), ("ARA", "اللغة العربية"), ("SCI", "العلوم"))
    }
    heavy = _teacher(school, "منير")
    light = _teacher(school, "منسّقٌ بأربع", role="coordinator")
    _assign(school, group, heavy, subjects["MAT"], 6)
    _assign(school, group, _teacher(school, "عربيّ"), subjects["ARA"], 6)
    _assign(school, group, light, subjects["SCI"], 4)
    TeacherExemption.objects.create(
        school=school,
        teacher=heavy,
        academic_year=YEAR,
        exemption_type="full_day",
        day_of_week=2,
        reason="دورة",
        source="school",
    )

    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    grid = result["grid"]
    heavy_days = [grid.teacher_periods_on_day(str(heavy.id), d) for d in DAYS]
    assert heavy_days[2] == 0, "الثلاثاءُ مفرَّغٌ من الإعدادات"
    assert all(n >= 1 for d, n in enumerate(heavy_days) if d != 2), heavy_days
    assert max(heavy_days) <= 2, "بنسبٍ متقاربة: ستٌّ على أربعة أيّام = 2،2،1،1"
