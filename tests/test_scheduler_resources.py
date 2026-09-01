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
        group = ClassGroupFactory(
            school=school, grade="G7", level_type="prep", academic_year=YEAR
        )
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
        group = ClassGroupFactory(
            school=school, grade="G9", level_type="prep", academic_year=YEAR
        )
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


def test_a_teacher_without_a_preference_follows_the_general_cap(school):
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    assign(school, group, teacher(school, "معلّمٌ عاديّ"), maths, periods=4)

    tasks = build_tasks(school, YEAR)

    assert all(t.consecutive_cap == 0 for t in tasks), "صفرٌ يعني: خُذ العامّ"


def test_an_inactive_resource_stops_constraining(school, gym):
    """موردٌ عُطِّل لا يُقيّد — فالمدرسةُ قد تفتح ملعباً ثالثاً."""
    SchedulingResource.objects.filter(school=school).update(is_active=False)

    tasks = build_tasks(school, YEAR)

    assert all(t.resources == () for t in tasks)
