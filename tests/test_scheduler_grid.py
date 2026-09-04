"""[SCHEDULE] الشبكةُ خانةٌ لكلّ شعبة، لا خانةٌ للمدرسة كلِّها.

    SchoolCapacity = Classes × SlotsPerWeek        (لا SlotsPerWeek وحدَها)

كانت `ScheduleGrid._grid[day][period]` تحمل مهمّةً واحدةً للمدرسة بأسرها، فمتى
وُضعت حصّةٌ في (الأحد · ح1) امتلأت الخانةُ في نظر الشُّعب الخمسٍ والعشرين
والمعلّمين الثلاثةِ والسبعين. وسقفُ المولّد حينها خمسٌ وثلاثون حصّةً مهما كانت
البيانات — والمطلوبُ 849.

ولم يكن العطبُ يُعلن نفسَه: يضع خمساً وثلاثين، ويتخطّى الباقيَ بوصفه «مخالفاتٍ
صلبة»، ويُعلن «جودة 85.1%» — لأنّ النقاطَ تقيس جمالَ ما وُضع لا نسبتَه من
المطلوب. فجدولٌ فيه 4% من الحصص يبدو ممتازاً.

وهذه الاختباراتُ تحرس الفرقَ بين التوازي والتعارض:

    شعبتان في التوقيت نفسه       ✓ توازٍ — هذا هو المعنى
    معلّمٌ في شعبتين في التوقيت     ✗ تعارضٌ حقيقيّ
    شعبةٌ بمادّتين في التوقيت       ✗ تعارضٌ حقيقيّ
"""

import pytest

from operations.scheduler import Member, ScheduleGrid, Task, build_tasks, get_available_slots
from operations.scheduler_constraints import check_class_conflict, check_teacher_conflict
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def task(*, teacher="t1", klass="c1", subject="s1", code="MAT", weekly=4, level="prep"):
    return Task(
        teacher_id=teacher,
        class_id=klass,
        subject_id=subject,
        subject_code=code,
        subject_name="مادّة",
        class_name="شعبة",
        teacher_name="معلّم",
        weekly_periods=weekly,
        level_type=level,
    )


# ── التوازي مسموح ────────────────────────────────────────────────────


def test_two_classes_may_share_the_same_slot(school):
    """خمسٌ وعشرون شعبةً تعمل في التوقيت نفسه — وهذا هو المدرسة، لا تعارضٌ فيها."""
    grid = ScheduleGrid()
    grid.place(0, 1, task(teacher="t1", klass="c1"))

    second = task(teacher="t2", klass="c2")

    assert check_class_conflict(grid, 0, 1, second.class_id)
    assert check_teacher_conflict(grid, 0, 1, second.teacher_id)
    assert (0, 1) in get_available_slots(grid, second)


def test_the_week_holds_a_slot_per_class_not_one_for_the_school(school):
    """السقفُ الحقيقيُّ: شعبٌ × خاناتُ الأسبوع — لا خاناتُ الأسبوع وحدَها."""
    grid = ScheduleGrid()
    for index in range(25):
        grid.place(0, 1, task(teacher=f"t{index}", klass=f"c{index}"))

    assert len(grid.all_entries()) == 25, "خمسٌ وعشرون شعبةً في خانةٍ واحدةٍ من الأسبوع"


# ── التعارضُ الحقيقيّ ممنوع ──────────────────────────────────────────


def test_one_teacher_cannot_be_in_two_classes_at_once(school):
    grid = ScheduleGrid()
    grid.place(0, 1, task(teacher="t1", klass="c1"))

    clash = task(teacher="t1", klass="c2")

    assert not check_teacher_conflict(grid, 0, 1, clash.teacher_id)
    assert (0, 1) not in get_available_slots(grid, clash)


def test_one_class_cannot_take_two_subjects_at_once(school):
    grid = ScheduleGrid()
    grid.place(0, 1, task(teacher="t1", klass="c1", subject="s1"))

    clash = task(teacher="t2", klass="c1", subject="s2")

    assert not check_class_conflict(grid, 0, 1, clash.class_id)
    assert (0, 1) not in get_available_slots(grid, clash)


def test_removing_frees_the_slot_for_that_class_only(school):
    """التراجعُ يُفرغ خانةَ شعبتها — ولا يمسّ جاراتِها في التوقيت نفسه."""
    grid = ScheduleGrid()
    keeper = task(teacher="t1", klass="c1")
    goer = task(teacher="t2", klass="c2")
    grid.place(0, 1, keeper)
    grid.place(0, 1, goer)

    grid.remove("c2", 0, 1)

    assert len(grid.all_entries()) == 1
    assert not check_class_conflict(grid, 0, 1, "c1"), "ما بقي في مكانه"
    assert check_class_conflict(grid, 0, 1, "c2"), "وما رُفع صار مكانُه شاغراً"


# ── ما تراه القيودُ المرنة ───────────────────────────────────────────


def test_a_teachers_run_is_counted_across_classes(school):
    """التتابعُ صفةُ معلّمٍ لا صفةُ شعبة: حصّتان متتاليتان في شعبتين تتابعٌ."""
    grid = ScheduleGrid()
    grid.place(0, 1, task(teacher="t1", klass="c1"))
    grid.place(0, 2, task(teacher="t1", klass="c2"))

    assert grid.teacher_consecutive_counted("t1", 0, 3) == 2


def test_a_subject_run_is_read_within_its_own_class(school):
    """أمّا «الحصّةُ المزدوجة» فصفةُ شعبةٍ ومادّة — تُقرأ داخل شعبتها وحدَها."""
    grid = ScheduleGrid()
    grid.place(0, 1, task(teacher="t1", klass="c1", subject="s1"))
    grid.place(0, 1, task(teacher="t2", klass="c2", subject="s2"))

    assert grid.get_task_at("c1", 0, 1).subject_id == "s1"
    assert grid.get_task_at("c2", 0, 1).subject_id == "s2"
    assert grid.get_task_at("c3", 0, 1) is None


# ── على بياناتٍ حقيقيّةٍ صغيرة ───────────────────────────────────────


@pytest.fixture
def teachers(school):
    role = RoleFactory(school=school, name="teacher")
    out = []
    for index in range(3):
        user = UserFactory(full_name=f"معلّم {index}")
        MembershipFactory(user=user, school=school, role=role)
        out.append(user)
    return out


@pytest.fixture
def subjects(school):
    from operations.models import Subject

    return [
        Subject.objects.create(school=school, name_ar=f"مادّة {i}", code=f"S{i}") for i in range(3)
    ]


def test_a_small_school_places_every_lesson(school, teachers, subjects):
    """ثلاثُ شعبٍ × ثلاثُ موادّ × أربعُ حصص = ستٌّ وثلاثون — تفوق سقفَ الشبكة القديم."""
    from operations.models import SubjectClassAssignment
    from operations.scheduler import generate_schedule

    groups = [
        ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
        for _ in range(3)
    ]
    for group in groups:
        for teacher, subject in zip(teachers, subjects, strict=True):
            SubjectClassAssignment.objects.create(
                school=school,
                academic_year=YEAR,
                teacher=teacher,
                class_group=group,
                subject=subject,
                weekly_periods=4,
                is_active=True,
            )

    tasks = build_tasks(school, YEAR)
    assert len(tasks) == 36

    result = generate_schedule(school, YEAR)

    assert result["quality"]["total_slots"] == 36, "لا حصّةَ متروكة"
    assert result["quality"]["placed_ratio"] == 100.0
    assert result["success"], result["errors"][:3]


def test_the_score_says_how_much_was_placed_not_only_how_pretty(school, teachers, subjects):
    """«جودة 85%» على 4% من الحصص رقمٌ يكذب — فالنسبةُ تُعلن مستقلّةً."""
    from operations.scheduler_constraints import calculate_quality_score

    grid = ScheduleGrid()
    grid.place(0, 1, task(teacher="t1", klass="c1"))

    quality = calculate_quality_score(grid, total_required=100)

    assert quality["total_slots"] == 1
    assert quality["placed_ratio"] == 1.0


def test_placed_and_required_share_one_unit(school, teachers, subjects):
    """«839/870» عن جدولٍ كامل: كان الموضوعُ يُعَدّ بخانات الشبكة والمطلوبُ
    بحصص التوزيعات — والخانةُ المنقسمةُ حصّتان. فالوحدةُ واحدة."""
    from operations.scheduler_constraints import calculate_quality_score

    grid = ScheduleGrid()
    split = task(teacher="t1", klass="c1")
    split.members = split.members + [
        Member(
            teacher_id="t2",
            teacher_name="t2",
            subject_id="s2",
            subject_name="فنون",
            subject_code="ART",
        )
    ]
    grid.place(0, 1, split)
    grid.place(0, 2, task(teacher="t3", klass="c1"))

    quality = calculate_quality_score(grid, total_required=3)

    assert quality["total_slots"] == 3, "حصّتان في الخانة المنقسمة وواحدةٌ في الأخرى"
    assert quality["placed_ratio"] == 100.0


def test_generation_time_reads_in_seconds_or_minutes():
    from core.templatetags.schedule_filters import duration_ms

    assert duration_ms(25554) == "25.6 ث"
    assert duration_ms(374379) == "6:14 د"
    assert duration_ms(820890) == "13:41 د"
    assert duration_ms(None) == ""
