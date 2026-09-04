"""التحسينُ المحلّيّ: نقلةٌ تُغلق فراغاً، وتبديلٌ لا يكسر قيداً، وموعدٌ يُحترم."""

import time

import pytest

from operations.models import Subject, SubjectClassAssignment
from operations.schedule_lab import grid_lab_score, load_context
from operations.scheduler import ScheduleGrid, build_tasks, generate_schedule
from operations.scheduler_improve import Improver, improve
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def two_subjects(school):
    """معلّمُ رياضياتٍ يدرّس شعبتين خمسَ حصصٍ لكلٍّ — ومعلّمُ عربيّةٍ لشعبةٍ واحدة."""
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    arabic = Subject.objects.create(school=school, name_ar="اللغة العربية", code="ARA")
    maths_teacher = _teacher(school, "رياضيّ")
    for _ in range(2):
        group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=maths_teacher,
            class_group=group,
            subject=maths,
            weekly_periods=5,
            is_active=True,
        )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=_teacher(school, "عربيّ"),
        class_group=group,
        subject=arabic,
        weekly_periods=5,
        is_active=True,
    )
    return school


def test_a_move_closes_a_gap_and_raises_the_lab_score(two_subjects):
    """الرياضيّ يومَ الأحد في الأولى (شعبة أ) والخامسة (شعبة ب) والثالثةُ شاغرةٌ لشعبة ب.

    فالنقلةُ من الخامسة إلى الثالثة تقصّر الفراغَ من ثلاثٍ إلى واحدة — ولا تُلاصق،
    فسياسةُ المدرسة لا تلاصقَ (HC5)، والفراغُ الواحدُ استراحةٌ لا عيب."""
    tasks = build_tasks(two_subjects, YEAR)
    by_class = {}
    for t in tasks:
        if t.subject_code == "MAT":
            by_class.setdefault(t.class_id, []).append(t)
    class_a, class_b = list(by_class.values())
    grid = ScheduleGrid()
    for day in range(5):
        grid.place(day, 1, class_a[day])
        grid.place(day, 5 if day == 0 else 3, class_b[day])
    ctx = load_context(two_subjects, YEAR)
    before, metrics_before = grid_lab_score(grid, ctx)
    assert metrics_before["teacher.gap_weighted_avg"]["value"] > 0

    result = improve(grid, tasks, set(), {}, ctx, time.time() + 20)

    after, metrics = grid_lab_score(grid, ctx)
    assert result["moves"] >= 1 and after > before
    assert (
        metrics["teacher.gap_weighted_avg"]["value"]
        < metrics_before["teacher.gap_weighted_avg"]["value"]
    )
    assert metrics["validity.hard_conflicts"]["value"] == 0


def test_a_past_deadline_makes_no_moves(two_subjects):
    tasks = build_tasks(two_subjects, YEAR)
    grid = ScheduleGrid()
    grid.place(0, 1, tasks[0])
    grid.place(0, 3, tasks[1])
    ctx = load_context(two_subjects, YEAR)

    result = improve(grid, tasks, set(), {}, ctx, time.time() - 1)

    assert result["moves"] == 0 and result["score_after"] == result["score_before"]


def test_a_rejected_move_leaves_the_grid_untouched(two_subjects):
    tasks = build_tasks(two_subjects, YEAR)
    grid = ScheduleGrid()
    grid.place(0, 1, tasks[0])
    ctx = load_context(two_subjects, YEAR)
    improver = Improver(grid, tasks, set(), {}, ctx, time.time() + 5)

    improver.grid.begin()
    accepted = improver._judge(None)

    assert accepted is False
    assert grid.home_of(tasks[0]) == (0, 1)
    assert grid.all_entries() and len(grid.all_entries()) == 1


def test_generation_records_the_improvement(two_subjects):
    result = generate_schedule(two_subjects, YEAR)
    snap = result["generation"].config_snapshot

    assert "improvement" in snap
    assert snap["improvement"]["score_after"] >= snap["improvement"]["score_before"]
    assert result["errors"] == []
