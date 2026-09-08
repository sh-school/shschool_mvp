"""HC18: مادّةٌ موسومةٌ «أيّامٌ مختلفة» بنطاق مرحلة — لا حصّتان منها في يومٍ للشعبة.

الفنّيّةُ والتكنولوجيا في الحادي عشر والثاني عشر متباعدتان وجوباً (قرار 2026-09-08)،
والفنّيّةُ نفسُها مزدوجةٌ في الإعداديّ — فالنطاقُ يقول أين يسري القيد، وحيث سرى
بطل الازدواج. والوسمُ من القاعدة لا من اسمٍ محفور.
"""

import pytest

from operations.models import Subject, SubjectClassAssignment
from operations.scheduler import ScheduleGrid, Task, build_tasks
from operations.scheduler_constraints import check_spread_days, is_slot_valid
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def task(spread=True, **kw):
    fields = {
        "class_id": "c1",
        "class_name": "c1",
        "subject_id": "art",
        "subject_name": "الفنون البصرية",
        "subject_code": "ART",
        "teacher_id": "t1",
        "teacher_name": "t1",
        "weekly_periods": 2,
        "level_type": "sec",
        "grade": "G11",
        "spread_days": spread,
    }
    fields.update(kw)
    return Task(**fields)


def test_a_second_period_on_the_same_day_is_refused_for_a_spread_subject():
    grid = ScheduleGrid()
    grid.place(1, 2, task())
    assert check_spread_days(grid, 1, task()) is False, "اليومُ نفسُه — مرفوض"
    assert check_spread_days(grid, 3, task()) is True, "يومٌ آخر — مقبول"
    assert is_slot_valid(grid, 1, 5, task()) is False, "ولا ينقذه بُعدُ الحصّة: القيدُ يومٌ لا تجاور"
    assert is_slot_valid(grid, 3, 5, task()) is True


def test_an_unflagged_subject_is_untouched():
    grid = ScheduleGrid()
    grid.place(1, 2, task(spread=False))
    assert check_spread_days(grid, 1, task(spread=False)) is True


@pytest.fixture
def art_in_two_levels(school):
    """الفنّيّةُ مزدوجةٌ في الإعداديّ ومتباعدةٌ في الثانويّ — مادّةٌ واحدةٌ بحالين."""
    art = Subject.objects.create(
        school=school,
        name_ar="الفنون البصرية",
        code="ART",
        requires_double_period=True,
        spread_days_scope="sec",
    )
    teacher = UserFactory(full_name="فنّان")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    prep = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    sec = ClassGroupFactory(school=school, grade="G11", level_type="sec", academic_year=YEAR)
    for group in (prep, sec):
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=art,
            weekly_periods=2,
            is_active=True,
        )
    return school, prep, sec


def test_the_scope_decides_per_level_and_spread_beats_double(art_in_two_levels):
    school, prep, sec = art_in_two_levels
    tasks = build_tasks(school, YEAR)
    by_class = {}
    for t in tasks:
        by_class.setdefault(t.class_id, []).append(t)

    prep_tasks = by_class[str(prep.id)]
    assert len(prep_tasks) == 1 and prep_tasks[0].span == 2, "الإعداديّ: كتلةٌ مزدوجةٌ واحدة"
    assert prep_tasks[0].spread_days is False

    sec_tasks = by_class[str(sec.id)]
    assert len(sec_tasks) == 2 and all(t.span == 1 for t in sec_tasks), "الثانويّ: حصّتان مفردتان"
    assert all(t.spread_days for t in sec_tasks)
    assert not any(t.prefers_double for t in sec_tasks), "التباعدُ يعلو الازدواجَ حيث يسري"


def test_the_subject_says_where_it_spreads():
    subject = Subject(spread_days_scope="sec")
    assert subject.spreads_in("sec") and not subject.spreads_in("prep")
    assert Subject(spread_days_scope="all").spreads_in("prep")
    assert not Subject(spread_days_scope="none").spreads_in("sec")
    assert not Subject(spread_days_scope="sec").spreads_in("")
