"""[SCHEDULE] سقفُ الفراغ حقُّ صاحبه لا شريكِه في الحصّة المشتركة (W-20261012-024).

كان `Task.gap_cap = min(سقوف الأعضاء)` فيُفرض سقفُ معلّمٍ على شريكه في المهمّة المنقسمة. والآن لكلّ عضوٍ
سقفُه (`Member.gap_cap`)، و`check_max_gap` يقيس كلَّ عضوٍ بسقفه ويتجاهل من لا سقفَ له. والاختباراتُ في
الذاكرة بلا قاعدةٍ ولا توليد، وببياناتٍ مصنّعةٍ بلا أسماءٍ ولا هويّات (PDPPL).
"""

import pytest

from operations.models import Subject, SubjectClassAssignment, TeacherPreference
from operations.scheduler import Member, ScheduleGrid, Task, build_tasks
from operations.scheduler_constraints import check_max_gap
from tests.conftest import ClassGroupFactory
from tests.test_scheduler_resources import YEAR, teacher


def lesson(klass, subject, teacher, members=None, gap=None):
    members = members or [Member(teacher, teacher, subject, subject, subject.upper())]
    return Task(
        class_id=klass,
        class_name=klass,
        subject_id=subject,
        subject_name=subject,
        subject_code=subject.upper(),
        teacher_id=teacher,
        teacher_name=teacher,
        weekly_periods=2,
        gap_cap=gap,
        members=list(members),
    )


def member(teacher, subject, gap=None):
    return Member(teacher, teacher, subject, subject, subject.upper(), gap_cap=gap)


def shared(a_gap, b_gap):
    """شعبةٌ منقسمةٌ: معلّمان في الخانة نفسها، لكلٍّ سقفُه (أو لا سقف)."""
    members = [member("t-a", "s-a", a_gap), member("t-b", "s-b", b_gap)]
    return lesson("c-sh", "s-a", "t-a", members=members)


def own(teacher, klass):
    return lesson(klass, f"s-{klass}", teacher)


def place(grid, day, period, task):
    grid.place(day, period, task)
    return task


def test_a_cap_is_not_imposed_on_the_partner_who_has_none():
    grid = ScheduleGrid()
    # t-b حصّتاه الخاصّتان ح1 وح6؛ والمشتركةُ ح3 فيصير أوسعُ فراغٍ له اثنتين (ح4 وح5).
    place(grid, 0, 1, own("t-b", "c-1"))
    place(grid, 0, 6, own("t-b", "c-2"))
    task = shared(a_gap=1, b_gap=None)
    # t-a صاحبُ السقف 1 وحصّتُه الوحيدة المشتركة ← فراغُه صفر؛ وt-b بلا سقفٍ ← لا يُقاس.
    assert check_max_gap(grid, 0, 3, task), "سقفُ t-a لا يُفرض على t-b"


def test_each_member_is_measured_by_his_own_cap():
    grid = ScheduleGrid()
    place(grid, 0, 1, own("t-a", "c-1"))
    task = shared(a_gap=1, b_gap=None)
    # t-a: ح1 ثم المشتركة في ح5 ← فراغ ثلاث حصص > 1 ← ممنوع، ولو كان شريكُه بلا سقف.
    assert not check_max_gap(grid, 0, 5, task)
    assert check_max_gap(grid, 0, 3, task), "فراغٌ واحدٌ — مقبول"


def test_the_partner_with_a_tighter_cap_is_still_bound_by_it():
    grid = ScheduleGrid()
    place(grid, 0, 1, own("t-b", "c-1"))
    task = shared(a_gap=None, b_gap=0)
    # t-b سقفُه صفر: ح1 ثم ح3 ← فراغ واحد > 0 ← ممنوع؛ وt-a بلا سقف.
    assert not check_max_gap(grid, 0, 3, task)
    assert check_max_gap(grid, 0, 2, task), "متلاصقتان بلا فراغ — مقبول"


def test_members_without_any_cap_are_never_blocked():
    grid = ScheduleGrid()
    place(grid, 0, 1, own("t-a", "c-1"))
    place(grid, 0, 1, own("t-b", "c-2"))
    assert check_max_gap(grid, 0, 7, shared(None, None))


def test_the_task_level_field_stays_as_a_derived_compatibility_value_and_is_not_read():
    grid = ScheduleGrid()
    place(grid, 0, 1, own("t-b", "c-1"))
    place(grid, 0, 6, own("t-b", "c-2"))
    # حقلُ المهمّة 0 (أضيق) لكنّ الأعضاءَ بلا سقف: لا يُستعمل الأضيق في أيّ فحص.
    task = shared(None, None)
    task.gap_cap = 0
    assert check_max_gap(grid, 0, 3, task)


@pytest.mark.django_db
def test_the_builder_gives_each_member_his_own_cap_and_the_task_the_narrowest(school, settings):
    settings.PREF_MAX_GAP_ACTIVE = True  # الراية مطفأةٌ افتراضاً (W-20261012-023)
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    capped, free = teacher(school, "معلّمٌ بسقف"), teacher(school, "معلّمٌ بلا سقف")
    for user, code in ((capped, "MAT"), (free, "SCI")):
        subject = Subject.objects.create(school=school, name_ar=code, code=code)
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=user,
            class_group=group,
            subject=subject,
            weekly_periods=2,
            is_active=True,
            parallel_group="G1",
        )
    TeacherPreference.objects.create(teacher=capped, school=school, academic_year=YEAR, max_gap=1)

    tasks = build_tasks(school, YEAR)

    assert tasks
    for task in tasks:
        assert {m.teacher_id: m.gap_cap for m in task.members} == {
            str(capped.id): 1,
            str(free.id): None,
        }
        assert task.gap_cap == 1, "حقلٌ مشتقٌّ للتوافق: الأضيق"
