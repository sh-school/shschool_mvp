"""نمطُ القسمة — النصابُ على الأيّام بفرقِ حصّةٍ على الأكثر، وخميسُ الثانويّ.

قرارُ الإدارة 2026-09-06:
    18 = 3+4+4+4+3 · 17 = 3+3+3+4+4 · 16 = 3+3+3+3+4 · 15 = 3+3+3+3+3
    14 = 3+3+3+3+2 · 13 = 3+3+3+2+2 · 12 = 3+3+2+2+2 · 11 = 3+2+2+2+2
    10 = 2+2+2+2+2 …  4 = 1+1+1+1+0

السقفُ قيدٌ صلبٌ عند الوضع، والحدُّ الأدنى يُصلحه التحسينُ ويُبلّغ عنه
المختبرُ بالاسم. ويومَ الخميس لا حصّتان لمادّةٍ في الحادي عشر والثاني عشر —
قيدٌ صلبٌ لا يسقط. والتفضيلُ الذي لا يتماشى مع النصاب يُردّ.
"""

import time
from datetime import time as clock

import pytest
from django.urls import reverse

from operations.models import ScheduleSlot, Subject, SubjectClassAssignment, TeacherPreference
from operations.schedule_lab import ScheduleLab, load_context
from operations.scheduler import ScheduleGrid, Task, build_tasks
from operations.scheduler_constraints import (
    THURSDAY,
    check_thursday_secondary_pair,
    check_week_balance_cap,
    week_share,
)
from operations.scheduler_improve import improve, teacher_day_cost
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def _task(class_id="c1", subject_id="s1", teacher_id="t1", *, grade="G8", double=False):
    return Task(
        class_id=class_id,
        class_name=class_id,
        subject_id=subject_id,
        subject_name=subject_id,
        subject_code=subject_id.upper(),
        teacher_id=teacher_id,
        teacher_name=teacher_id,
        weekly_periods=1,
        grade=grade,
        prefers_double=double,
    )


def _grid(load, days=5, teacher="t1"):
    return ScheduleGrid(coverage={teacher: (load, load, frozenset(range(days)))})


# ══════════════════════ نصيبُ اليوم ═══════════════════════════════


@pytest.mark.parametrize(
    ("load", "floor", "cap"),
    [
        (18, 3, 4),
        (17, 3, 4),
        (16, 3, 4),
        (15, 3, 3),
        (14, 2, 3),
        (13, 2, 3),
        (12, 2, 3),
        (11, 2, 3),
        (10, 2, 2),
        (5, 1, 1),
        (4, 0, 1),
        (3, 0, 1),
    ],
)
def test_the_share_matches_the_agreed_table(load, floor, cap):
    assert week_share(_grid(load), "t1") == (floor, cap)


def test_a_free_day_shrinks_the_week_and_raises_the_cap():
    """ثماني عشرةَ على أربعة أيّام: يومان بخمس."""
    assert week_share(_grid(18, days=4), "t1") == (4, 5)


# ══════════════════════ السقف صلب ═════════════════════════════════


def test_the_cap_refuses_a_lesson_above_the_share():
    grid = _grid(13)  # السقف 3
    tasks = [_task(class_id=f"c{i}") for i in range(3)]
    for period, task in zip((1, 3, 5), tasks, strict=False):
        grid.place(0, period, task)

    assert check_week_balance_cap(grid, 0, 7, _task(class_id="c9")) is False
    assert check_week_balance_cap(grid, 1, 1, _task(class_id="c9")) is True


def test_a_double_counts_two_against_the_cap():
    grid = _grid(13)  # السقف 3
    grid.place(0, 1, _task(class_id="c1"))
    grid.place(0, 3, _task(class_id="c2"))

    double = _task(class_id="c3", double=True)
    double.span = 2

    assert check_week_balance_cap(grid, 0, 5, double) is False


def test_a_teacher_without_coverage_is_not_capped():
    assert check_week_balance_cap(ScheduleGrid(), 0, 1, _task()) is True


# ══════════════════════ خميسُ الثانويّ ═════════════════════════════


def test_a_second_lesson_of_the_subject_on_thursday_is_refused_for_grade_12():
    grid = _grid(10)
    grid.place(THURSDAY, 1, _task(grade="G12"))

    assert check_thursday_secondary_pair(grid, THURSDAY, 3, _task(grade="G12")) is False
    assert check_thursday_secondary_pair(grid, 3, 3, _task(grade="G12")) is True


def test_the_thursday_rule_is_for_the_secondary_only_and_spares_doubles():
    grid = _grid(10)
    grid.place(THURSDAY, 1, _task(grade="G8"))
    grid.place(THURSDAY, 1, _task(class_id="c2", subject_id="s2", grade="G11"))

    assert check_thursday_secondary_pair(grid, THURSDAY, 3, _task(grade="G8")) is True
    assert (
        check_thursday_secondary_pair(
            grid, THURSDAY, 3, _task(class_id="c2", subject_id="s2", grade="G11", double=True)
        )
        is True
    )


# ══════════════════════ الحدُّ الأدنى يُصلحه التحسين ═══════════════


def test_a_day_below_the_floor_costs_even_when_empty():
    grid = _grid(13)  # الحدّ الأدنى 2

    assert teacher_day_cost(grid, "t1", 0, None) > 0


@pytest.fixture
def thirteen_lessons(school):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = UserFactory(full_name="رياضيّ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    for periods in (5, 4, 4):
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=ClassGroupFactory(
                school=school, grade="G8", level_type="prep", academic_year=YEAR
            ),
            subject=maths,
            weekly_periods=periods,
            is_active=True,
        )
    return school, teacher


def test_the_improver_lifts_a_day_below_the_floor(thirteen_lessons):
    """3+3+3+3+1 لثلاثَ عشرةَ: لا سقفَ مخالَف، والحدُّ الأدنى اثنتان."""
    school, teacher = thirteen_lessons
    tasks = build_tasks(school, YEAR)
    tid = str(teacher.id)
    grid = ScheduleGrid(coverage={tid: (13, 13, frozenset(range(5)))})
    by_class = {}
    for t in tasks:
        by_class.setdefault(t.class_id, []).append(t)
    queue = [t for group in by_class.values() for t in group]
    layout = [(0, 3), (1, 3), (2, 3), (3, 3), (4, 1)]
    i = 0
    for day, count in layout:
        for period in (1, 3, 5)[:count]:
            grid.place(day, period, queue[i])
            i += 1
    ctx = load_context(school, YEAR)

    improve(grid, tasks, set(), {}, ctx, time.time() + 30)

    counts = [grid.teacher_periods_on_day(tid, d) for d in range(5)]
    assert min(counts) >= 2 and max(counts) <= 3, counts


# ══════════════════════ المختبر يقول مَن ═══════════════════════════


def test_the_lab_names_who_is_off_the_pattern(school, teacher_user):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    for day, count in ((0, 4), (1, 2), (2, 3), (3, 2), (4, 4)):
        for period in range(1, count + 1):
            ScheduleSlot.objects.create(
                school=school,
                class_group=group,
                teacher=teacher_user,
                subject=maths,
                day_of_week=day,
                period_number=period,
                start_time=clock(7, 30),
                end_time=clock(8, 15),
                academic_year=YEAR,
                is_active=True,
            )

    metrics = ScheduleLab.for_live(school, YEAR).compute()

    assert metrics["teacher.pattern_breaches"]["value"] == 1
    assert metrics["teacher.pattern_breaches"]["detail"] == {teacher_user.full_name: "4+2+3+2+4"}


# ══════════════════════ التفضيلُ الذي لا يتماشى يُردّ ══════════════


def test_a_daily_cap_below_the_share_is_rejected(client, school, teacher_user):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    for periods in (6, 6, 6):
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher_user,
            class_group=ClassGroupFactory(
                school=school, grade="G8", level_type="prep", academic_year=YEAR
            ),
            subject=maths,
            weekly_periods=periods,
            is_active=True,
        )
    client.force_login(teacher_user)

    response = client.post(
        reverse("teacher_preferences") + f"?year={YEAR}",
        {"max_daily_periods": "3", "max_consecutive": "2", "max_gap": "", "free_day": ""},
        follow=True,
    )

    body = response.content.decode()
    assert "لا يتماشى" in body and "لم يُحفظ" in body
    assert (
        TeacherPreference.objects.get(teacher=teacher_user, academic_year=YEAR).max_daily_periods
        == 5
    )
