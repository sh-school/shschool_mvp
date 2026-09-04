"""SC14: يومُ الحصّتين للمادّة أيُّ يومٍ عدا الخميس (قرار الإدارة 2026-09-04) — تفضيلٌ قويّ."""

import time

import pytest

from operations.models import Subject, SubjectClassAssignment
from operations.schedule_lab import Context, ScheduleLab, Slot, grid_lab_score, load_context
from operations.scheduler import ScheduleGrid, Task, build_tasks
from operations.scheduler_constraints import check_subject_distribution
from operations.scheduler_improve import improve
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def task(weekly=6, prefers_double=False):
    return Task(
        class_id="c1",
        class_name="c1",
        subject_id="s",
        subject_name="مادّة",
        subject_code="S",
        teacher_id="t1",
        teacher_name="t1",
        weekly_periods=weekly,
        prefers_double=prefers_double,
    )


def test_a_second_period_on_thursday_is_penalised_heavily_not_refused():
    """تفضيلٌ قويّ لا قيدٌ صلب: القيدُ الصلبُ أنتج تلاصقاً أكثرَ وحصصاً بلا موضع."""
    from operations.scheduler_constraints import WEIGHTS, evaluate_soft_constraints

    grid = ScheduleGrid()
    grid.place(4, 1, task())
    assert check_subject_distribution(grid, 4, task()) is True
    penalty = evaluate_soft_constraints(grid, 4, 3, task())
    assert "thursday_pair" in penalty.details
    assert penalty.total >= WEIGHTS["thursday_pair"]
    assert "thursday_pair" not in evaluate_soft_constraints(grid, 3, 3, task()).details


def test_a_required_double_subject_is_not_penalised_on_thursday():
    """الفنّيّة وتكنولوجيا المعلومات وعلوم الحاسب: كتلٌ بحكم المادّة."""
    from operations.scheduler_constraints import evaluate_soft_constraints

    grid = ScheduleGrid()
    grid.place(4, 1, task(weekly=10, prefers_double=True))
    penalty = evaluate_soft_constraints(grid, 4, 3, task(weekly=10, prefers_double=True))
    assert "thursday_pair" not in penalty.details


def test_the_lab_counts_thursday_pairs():
    def slot(day, period, double=False):
        return Slot("t1", "t1", "c1", "c1", "s", "S", "regular", double, day, period, "", "")

    lab = ScheduleLab([slot(4, 1), slot(4, 3), slot(0, 1)], Context())
    assert lab.doubles_on_thursday()["value"] == 1
    lab = ScheduleLab([slot(4, 1, True), slot(4, 2, True)], Context())
    assert lab.doubles_on_thursday()["value"] == 0, "المزدوجةُ المطلوبةُ مستثناة"


@pytest.fixture
def sixth(school):
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = UserFactory(full_name="رياضيّ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=maths,
        weekly_periods=6,
        is_active=True,
    )
    return school


def test_the_improver_moves_the_thursday_pair_away(sixth):
    tasks = build_tasks(sixth, YEAR)
    grid = ScheduleGrid()
    for day, t in zip((0, 1, 2, 3), tasks[:4], strict=False):
        grid.place(day, 1, t)
    grid.place(4, 1, tasks[4])
    grid.place(4, 3, tasks[5])
    ctx = load_context(sixth, YEAR)
    assert grid_lab_score(grid, ctx)[1]["subject.double_on_thursday"]["value"] == 1

    improve(grid, tasks, set(), {}, ctx, time.time() + 20)

    metrics = grid_lab_score(grid, ctx)[1]
    assert metrics["subject.double_on_thursday"]["value"] == 0
    assert metrics["validity.hard_conflicts"]["value"] == 0
