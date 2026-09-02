"""[SCHEDULE] المكانُ مورد: ملعبان وخمسةُ معلّمي بدنيّة، ومعملا حاسبٍ لا أكثر.

القيدُ هنا ليس على المعلّم ولا على الشعبة بل على **المكان**: خمسةُ معلّمي
بدنيّةٍ قد يكونون فارغين جميعاً في التوقيت نفسه، ولا يسع الملعبانِ إلّا
حصّتين. وكذلك المعملان.

    TeacherFree ∧ ClassFree ⇏ Schedulable

ولا يُحلّ هذا بسقفٍ على المادّة وحدَها: المعملانِ يتقاسمهما «علوم الحاسب»
و«تكنولوجيا المعلومات» معاً، فالسعةُ على المورد لا على كلّ مادّةٍ بمفردها.
وهذا هو الفرقُ الذي فرض كياناً مستقلّاً: `SchedulingResource`.
"""

from collections import Counter

import pytest

from operations.models import (
    SchedulingResource,
    Subject,
    SubjectClassAssignment,
)
from operations.scheduler import build_tasks, generate_schedule
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def teacher(school, name):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


def assign(school, group, user, subject, *, periods):
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=user,
        class_group=group,
        subject=subject,
        weekly_periods=periods,
        is_active=True,
    )


@pytest.fixture
def gym(school):
    """أربعُ شعبٍ وأربعةُ معلّمي بدنيّة — وملعبان."""
    pe = Subject.objects.create(school=school, name_ar="التربية البدنية", code="PE")
    resource = SchedulingResource.objects.create(school=school, name="الملاعب", capacity=2)
    resource.subjects.set([pe])
    for index in range(4):
        group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
        assign(school, group, teacher(school, f"معلّم بدنيّة {index}"), pe, periods=2)
    return pe


# ── السعةُ تُحترَم ───────────────────────────────────────────────────


def test_no_more_lessons_than_the_place_can_hold(school, gym):
    """أربعُ شعبٍ ومعلّمون فارغون — ولا تقع ثالثةٌ في التوقيت الواحد."""
    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    load = Counter(
        (entry["day"], slot)
        for entry in result["grid"].all_entries()
        for slot in entry["task"].slots(entry["period"])
    )
    assert max(load.values()) <= 2, f"تجاوزَ سعةَ الملعب: {load}"


def test_the_tasks_know_which_resource_they_consume(school, gym):
    tasks = build_tasks(school, YEAR)

    assert all(len(t.resources) == 1 for t in tasks)
    assert {capacity for _, capacity in tasks[0].resources} == {2}


def test_a_subject_outside_the_resource_is_unconstrained(school, gym):
    """والمادّةُ التي لا تستعمل المورد لا يُقيّدها سقفُه."""
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    assign(school, group, teacher(school, "معلّمُ الرياضيات"), maths, periods=4)

    tasks = build_tasks(school, YEAR)
    plain = [t for t in tasks if t.subject_code == "MAT"]

    assert plain and all(t.resources == () for t in plain)


# ── موردٌ تتقاسمه مادّتان ────────────────────────────────────────────


def test_two_subjects_share_one_pair_of_labs(school):
    """المعملانِ سقفٌ على المادّتين مجتمعتين، لا على كلٍّ بمفردها.

    ولو كان السقفُ على المادّة وحدَها لجاز أن يقع حاسبانِ وتقنيّتانِ معاً —
    أربعُ حصصٍ في معملين.
    """
    computing = Subject.objects.create(school=school, name_ar="علوم الحاسب", code="CS")
    info = Subject.objects.create(school=school, name_ar="تكنولوجيا المعلومات", code="IT")
    labs = SchedulingResource.objects.create(school=school, name="معامل الحاسب", capacity=2)
    labs.subjects.set([computing, info])

    for index, subject in enumerate((computing, computing, info, info)):
        group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
        assign(school, group, teacher(school, f"معلّمُ حاسب {index}"), subject, periods=2)

    result = generate_schedule(school, YEAR)

    assert result["errors"] == []
    load = Counter(
        (entry["day"], slot)
        for entry in result["grid"].all_entries()
        for slot in entry["task"].slots(entry["period"])
    )
    assert max(load.values()) <= 2, "المعملانِ لا يسعان أكثرَ من حصّتين"


# ── قيدٌ في حقّ معلّمٍ بعينه ─────────────────────────────────────────


def test_a_personal_consecutive_cap_is_never_relaxed(school):
    """قرارٌ في حقّ معلّمٍ أثقلُ من سقفٍ عامٍّ وُضع ليُقارَب.

    فالسقفُ العامُّ يُرفع درجةً في جولة الاسترخاء لتنزل حصّةٌ لا مكانَ لها.
    أمّا من مُنع من التجاور بقرارٍ في حقّه فيبقى ممنوعاً ولو بقيت حصّةٌ.
    """
    from operations.models import TeacherPreference
    from operations.scheduler_constraints import check_max_consecutive

    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    strict = teacher(school, "معلّمٌ ممنوعُ التجاور")
    assign(school, group, strict, maths, periods=4)
    TeacherPreference.objects.create(
        teacher=strict, school=school, academic_year=YEAR, max_consecutive=1
    )

    tasks = build_tasks(school, YEAR)
    assert all(t.consecutive_cap == 1 for t in tasks)

    from operations.scheduler import ScheduleGrid

    grid = ScheduleGrid()
    grid.place(0, 1, tasks[0])

    assert not check_max_consecutive(grid, 0, 2, tasks[1]), "ممنوعٌ في الأصل"
    assert not check_max_consecutive(
        grid, 0, 2, tasks[1], allow_adjacent=True
    ), "وممنوعٌ في الاسترخاء أيضاً"


def test_a_personal_gap_cap_is_measured_over_the_whole_day(school):
    """فراغُ المعلّم قيدٌ صلبٌ لمن قُرِّر في حقّه سقفٌ — والقياسُ على اليوم كلِّه.

    فمن سقفُه فراغٌ واحدٌ تتباعد حصصُه حصّةً حصّة: الثانيةُ فالرابعة، لا
    الثانيةُ فالخامسة. والخانةُ الواقعةُ **بين** حصّتين متباعدتين تُضيّق
    الفراغَ فتُقبل — إذ القياسُ على اليوم بعد الوضع لا على الجارِ وحدَه.
    """
    from operations.models import TeacherPreference
    from operations.scheduler import ScheduleGrid
    from operations.scheduler_constraints import check_max_gap

    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    spaced = teacher(school, "معلّمٌ فراغُه واحد")
    assign(school, group, spaced, maths, periods=4)
    TeacherPreference.objects.create(teacher=spaced, school=school, academic_year=YEAR, max_gap=1)

    tasks = build_tasks(school, YEAR)
    assert all(t.gap_cap == 1 for t in tasks)

    grid = ScheduleGrid()
    grid.place(0, 2, tasks[0])

    assert check_max_gap(grid, 0, 4, tasks[1]), "فراغٌ واحدٌ — مقبول"
    assert not check_max_gap(grid, 0, 5, tasks[1]), "فراغان — ممنوع"

    grid.place(0, 6, tasks[1])
    assert check_max_gap(grid, 0, 4, tasks[2]), "الواقعةُ بينهما تُضيّق الفراغَ لا توسّعه"


def test_a_teacher_without_a_gap_preference_keeps_the_soft_weight(school):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    assign(school, group, teacher(school, "معلّمٌ بلا سقفِ فراغ"), maths, periods=4)

    tasks = build_tasks(school, YEAR)

    assert all(t.gap_cap is None for t in tasks), "لا قيدَ شخصيّ — الفراغُ ترجيحٌ مرن"


def test_a_teacher_without_a_preference_follows_the_general_cap(school):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    assign(school, group, teacher(school, "معلّمٌ عاديّ"), maths, periods=4)

    tasks = build_tasks(school, YEAR)

    assert all(t.consecutive_cap == 0 for t in tasks), "صفرٌ يعني: خُذ العامّ"


def test_a_double_period_consumes_the_room_for_both_slots(school):
    """الفنّيّةُ حالةٌ مركّبة: مزدوجةٌ متلاصقةٌ تشغل المرسمَ خانتين لا خانة.

    فلو حُسب المورد على المهمّة لا على خاناتها لظنّ النظامُ أنّ المرسمَ شاغرٌ
    في الخانة الثانية — وهو مشغولٌ بها بعينها.
    """
    from operations.scheduler import ScheduleGrid
    from operations.scheduler_constraints import check_resource_capacity

    art = Subject.objects.create(
        school=school, name_ar="الفنون البصرية", code="", requires_double_period=True
    )
    rooms = SchedulingResource.objects.create(school=school, name="مرسما الفنّيّة", capacity=2)
    rooms.subjects.set([art])
    for index in range(3):
        group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
        assign(school, group, teacher(school, f"معلّمُ فنون {index}"), art, periods=2)

    tasks = build_tasks(school, YEAR)
    assert all(t.span == 2 for t in tasks), "مزدوجةٌ لا مفردة"

    grid = ScheduleGrid()
    grid.place(0, 1, tasks[0])
    grid.place(0, 1, tasks[1])

    assert not check_resource_capacity(grid, 0, 1, tasks[2]), "المرسمانِ مشغولان في الأولى"
    assert not check_resource_capacity(grid, 0, 2, tasks[2]), "وفي الثانية كذلك — المزدوجةُ خانتان"
    assert check_resource_capacity(grid, 1, 1, tasks[2]), "ويومٌ آخرُ شاغر"


def test_an_inactive_resource_stops_constraining(school, gym):
    """موردٌ عُطِّل لا يُقيّد — فالمدرسةُ قد تفتح ملعباً ثالثاً."""
    SchedulingResource.objects.filter(school=school).update(is_active=False)

    tasks = build_tasks(school, YEAR)

    assert all(t.resources == () for t in tasks)


# ── الموارد المقرَّرة في المدرسة ────────────────────────────────────


def test_the_seed_command_declares_the_two_computer_labs(school):
    """معملان اثنان تتقاسمهما موادُّ الحاسب الثلاث — قرارُ المدرسة لا اجتهاد.

    والبنيةُ كانت قائمةً والقيدُ صامتاً: `SchedulingResource` موجودٌ و`HC9`
    يقرؤه، ولا سطرَ بياناتٍ لموادّ الحاسب — فمَن لم يُسجَّل مورده لم يُقيَّد.
    """
    from django.core.management import call_command

    names = ("التكنولوجيا", "علوم الحاسب", "تكنولوجيا المعلومات", "التربية البدنية")
    for name in names:
        Subject.objects.create(school=school, name_ar=name)

    call_command("seed_scheduling_resources", school=school.code, verbosity=0)

    labs = SchedulingResource.objects.get(school=school, name="معملا الحاسب")
    assert labs.capacity == 2
    assert {s.name_ar for s in labs.subjects.all()} == {
        "التكنولوجيا",
        "علوم الحاسب",
        "تكنولوجيا المعلومات",
    }
    assert SchedulingResource.objects.get(school=school, name="الملاعب").capacity == 2


def test_the_seed_command_is_idempotent(school):
    """يُعاد فلا يُراكم — والأمرُ مُعلِنٌ لحالٍ، لا مُضيفٌ في كلّ مرّة."""
    from django.core.management import call_command

    Subject.objects.create(school=school, name_ar="علوم الحاسب")

    call_command("seed_scheduling_resources", school=school.code, verbosity=0)
    call_command("seed_scheduling_resources", school=school.code, verbosity=0)

    assert SchedulingResource.objects.filter(school=school, name="معملا الحاسب").count() == 1


def test_the_labs_cap_three_computer_lessons_down_to_two(school):
    """ثلاثُ شعبٍ تطلب المعملَ في التوقيت نفسه — فلا تقع إلّا اثنتان."""
    from django.core.management import call_command

    from operations.scheduler import ScheduleGrid
    from operations.scheduler_constraints import check_resource_capacity

    tech = Subject.objects.create(school=school, name_ar="التكنولوجيا", code="TECH")
    computing = Subject.objects.create(school=school, name_ar="علوم الحاسب", code="CS")
    call_command("seed_scheduling_resources", school=school.code, verbosity=0)

    groups = []
    for index, subject in enumerate((tech, tech, computing)):
        group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
        groups.append(group)
        assign(school, group, teacher(school, f"معلّمُ معمل {index}"), subject, periods=2)

    tasks = build_tasks(school, YEAR)

    def lesson(group):
        return next(t for t in tasks if t.class_id == str(group.id))

    grid = ScheduleGrid()
    grid.place(0, 1, lesson(groups[0]))
    grid.place(0, 1, lesson(groups[1]))

    # المعلّمُ فارغٌ والشعبةُ فارغة — والمعملانِ مشغولان.
    assert not check_resource_capacity(grid, 0, 1, lesson(groups[2]))
    # والتكنولوجيا حصصٌ مفردةٌ لا مزدوجة، فالثانيةُ خاليةٌ لا تشغلها الأولى.
    assert all(t.span == 1 for t in tasks)
    assert check_resource_capacity(grid, 0, 2, lesson(groups[2]))
