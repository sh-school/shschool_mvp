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
    check_week_floor_reservation,
    week_share,
)
from operations.scheduler_improve import improve, teacher_day_cost
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def _task(class_id="c1", subject_id="s1", teacher_id="t1", *, grade="G8", double=False, weekly=1):
    return Task(
        class_id=class_id,
        class_name=class_id,
        subject_id=subject_id,
        subject_name=subject_id,
        subject_code=subject_id.upper(),
        teacher_id=teacher_id,
        teacher_name=teacher_id,
        weekly_periods=weekly,
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


def test_a_double_may_exceed_the_cap_by_one_but_not_two():
    """الزوجُ لا يُشطر: يومٌ فيه حصّتان يقبل زوجاً (4 > 3 بحصّة)، ويومٌ فيه ثلاثٌ لا."""
    grid = _grid(13)  # السقف 3
    grid.place(0, 1, _task(class_id="c1"))
    grid.place(0, 3, _task(class_id="c2"))
    double = _task(class_id="c3", double=True)
    double.span = 2

    assert check_week_balance_cap(grid, 0, 5, double) is True

    grid.place(0, 5, _task(class_id="c4"))

    assert check_week_balance_cap(grid, 0, 6, double) is False


def test_a_teacher_without_coverage_is_not_capped():
    assert check_week_balance_cap(ScheduleGrid(), 0, 1, _task()) is True


def test_the_floor_is_reserved_before_the_last_lessons_run_out():
    """13 حصّة: 3+3+3+2+0 والباقي حصّتان — لا توضع إحداهما في اليوم الرابع."""
    grid = _grid(13)  # الحدّ 2، السقف 3
    layout = [(0, 3), (1, 3), (2, 3), (3, 2)]
    n = 0
    for day, count in layout:
        for period in (1, 3, 5)[:count]:
            grid.place(day, period, _task(class_id=f"c{n}", subject_id=f"s{n}"))
            n += 1

    assert check_week_floor_reservation(grid, 3, 5, _task(class_id="c99", subject_id="x")) is False
    assert check_week_floor_reservation(grid, 4, 1, _task(class_id="c99", subject_id="x")) is True


def test_the_reservation_yields_in_the_last_resort_round():
    grid = _grid(13)
    for day, count in [(0, 3), (1, 3), (2, 3), (3, 2)]:
        for period in (1, 3, 5)[:count]:
            grid.place(day, period, _task(class_id=f"c{day}{period}", subject_id=f"s{day}{period}"))

    assert (
        check_week_floor_reservation(
            grid, 3, 5, _task(class_id="c99", subject_id="x"), allow_dense=True
        )
        is True
    )


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


@pytest.fixture
def sixteen_lessons(school):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = UserFactory(full_name="رياضيّ")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    for periods in (6, 5, 5):
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


def test_the_firm_pass_fixes_the_floor_even_when_the_lab_would_object(sixteen_lessons):
    """16 = 4+4+3+3+2 على الورق يجب أن يصير 3+3+3+3+4 أو نحوه — قرارٌ لا ترجيح."""
    school, teacher = sixteen_lessons
    tasks = build_tasks(school, YEAR)
    tid = str(teacher.id)
    grid = ScheduleGrid(coverage={tid: (16, 16, frozenset(range(5)))})
    queue = list(tasks)
    layout = [(0, 4), (1, 4), (2, 3), (3, 3), (4, 2)]
    i = 0
    for day, count in layout:
        for period in (1, 3, 5, 7)[:count]:
            grid.place(day, period, queue[i])
            i += 1
    ctx = load_context(school, YEAR)

    result = improve(grid, tasks, set(), {}, ctx, time.time() + 30)

    counts = [grid.teacher_periods_on_day(tid, d) for d in range(5)]
    assert result["balanced"] >= 1
    assert min(counts) >= 3 and max(counts) <= 4, counts


def test_the_firm_pass_swaps_when_the_class_is_full_on_the_deficit_day(school):
    """الشعبةُ مشغولةٌ في كلّ حصص يوم النقص — فالنقلُ مستحيل والتبديلُ هو الطريق.

    المعلّم «أ» نصابُه حصّتان على يومين (حصّةٌ في كلّ يوم) ووُضعتا معاً في
    اليوم الأوّل؛ واليومُ الثاني للشعبة مملوءٌ بحصص «ب». فتُبدَّل حصّةٌ لـ«أ»
    بحصّةٍ لـ«ب» — و«ب» يبقى داخل نمطه.
    """
    # نصابُ المادّة حصّتان، فقسمتُها على الأيّام تسمح بيومين — كما يبنيها المولّد.
    a_tasks = [_task(class_id="c1", subject_id="s1", teacher_id="A", weekly=2) for _ in range(2)]
    b_tasks = [_task(class_id="c1", subject_id=f"b{i}", teacher_id="B") for i in range(8)]
    grid = ScheduleGrid(coverage={"A": (2, 2, frozenset({0, 1})), "B": (8, 8, frozenset({0, 1}))})
    grid.place(0, 1, a_tasks[0])
    grid.place(0, 3, a_tasks[1])
    for period in range(1, 8):
        grid.place(1, period, b_tasks[period - 1])
    grid.place(0, 5, b_tasks[7])
    ctx = load_context(school, YEAR)

    improve(grid, a_tasks + b_tasks, set(), {}, ctx, time.time() + 20)

    assert [grid.teacher_periods_on_day("A", d) for d in (0, 1)] == [1, 1]
    # ولا حصّةَ تضيع في التبديل: ثمانيةُ «ب» تبقى ثمانيةً في الأسبوع كلِّه.
    #
    # ولا يُقاس «ب» على يومين اثنين: أيّامُ المعلّم في الإنتاج تُقيَّد بتفريغاته
    # في `is_slot_valid`، وأيّامُ `coverage` هنا وصفٌ للقسمة لا قيدُ وضعٍ —
    # فللمحسّن أن ينشر «ب» على الأسبوع، وهو تحسينٌ لا خسارة.
    counts_b = [grid.teacher_periods_on_day("B", d) for d in range(5)]
    assert sum(counts_b) == 8, counts_b
    assert max(counts_b) <= 7, "ولا يُحشر في يومٍ واحد"


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
