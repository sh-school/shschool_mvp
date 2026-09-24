"""[SCHEDULE] سدادُ الجدول الحيّ بأقلّ اضطراب (SCH-06): مسودّةٌ جديدةٌ، والحيُّ لا يُمَسّ.

الجدولُ المعتمد في 2026-09-24 فيه حصّتا رياضيات يومَ الأحد ولا شيءَ يومَ الخميس في
شعبةٍ نصابُها خمس — مخالفةٌ لقسمة HC6 وضعتها رخصةُ الكثافة ولم يسدّها أحد. والأمرُ
`settle_schedule` يبني الشبكةَ من الحصص الحيّة ويسدّدها ويكتب الناتجَ مسودّةً:

    --dry-run   الفرقُ والمخالفاتُ قبل وبعد، ولا صفَّ يُكتب
    بلاه        مسودّةٌ حصصُها مطفأة، والاعتمادُ طريقُه المعتاد

والحالةُ هنا أصغرُ ما يحمل المخالفة: شعبةٌ واحدة، ومادّةٌ بخمس حصص، ومعلّمٌ واحد.
"""

from datetime import time
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from operations.models import ScheduleGeneration, ScheduleSlot, Subject, SubjectClassAssignment
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUNDAY, THURSDAY = 0, 4
#: خمسُ حصصٍ في أربعة أيّام: الأحدُ مرّتين (متباعدتين فلا تلاصق)، والخميسُ فارغ.
DENSE_WEEK = [(SUNDAY, 1), (SUNDAY, 3), (1, 2), (2, 4), (3, 5)]


@pytest.fixture
def dense(school):
    """جدولٌ معتمَدٌ حيٌّ بمخالفة قسمة: رياضياتُ الشعبة حصّتان يومَ الأحد."""
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=maths,
        weekly_periods=5,
        is_active=True,
    )
    approved = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="approved"
    )
    for day, period in DENSE_WEEK:
        ScheduleSlot.objects.create(
            school=school,
            teacher=teacher,
            class_group=group,
            subject=maths,
            day_of_week=day,
            period_number=period,
            start_time=time(7, 30),
            end_time=time(8, 15),
            academic_year=YEAR,
            is_active=True,
            generation=approved,
        )
    return {"school": school, "group": group, "approved": approved}


def _run(school, *extra):
    out = StringIO()
    args = ["--school", school.code, "--year", YEAR, "--budget", "20", *extra]
    call_command("settle_schedule", *args, stdout=out)
    return out.getvalue()


def _live(school):
    return sorted(
        ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True).values_list(
            "id", "day_of_week", "period_number", "generation_id"
        )
    )


def test_a_dry_run_shows_the_breach_and_writes_nothing(dense):
    school = dense["school"]
    live, generations = _live(school), ScheduleGeneration.objects.count()

    output = _run(school, "--dry-run")

    assert "HC6" in output, "المخالفةُ تُسمّى برمزها قبل السداد"
    assert "عرضٌ فقط" in output
    assert ScheduleGeneration.objects.count() == generations, "العرضُ لا يكتب توليداً"
    assert _live(school) == live, "ولا يمسّ حصّةً حيّة"


def test_settling_writes_a_draft_with_fewer_breaches(dense):
    school, approved = dense["school"], dense["approved"]
    live = _live(school)

    _run(school)

    draft = ScheduleGeneration.objects.exclude(pk=approved.pk).get()
    snapshot = draft.config_snapshot
    assert draft.status == "draft"
    assert snapshot["mode"] == "settle"
    assert snapshot["source_generation"] == str(approved.pk)
    assert snapshot["breaches"]["count"] < snapshot["breaches_before"]["count"]
    assert "HC6" in snapshot["breaches_before"]["by_code"]
    assert "HC6" not in snapshot["breaches"]["by_code"], "القسمةُ سُدِّدت"
    assert draft.hard_violations == snapshot["breaches"]["count"]
    assert snapshot["changed_cells"] >= 2, "خانةٌ فرغت وخانةٌ امتلأت"

    slots = ScheduleSlot.objects.filter(generation=draft)
    assert slots.count() == len(DENSE_WEEK), "المسودّةُ الجدولُ كلُّه لا الفرقُ وحده"
    assert not slots.filter(is_active=True).exists(), "حصصُ المسودّة مطفأة"
    days = sorted(slots.values_list("day_of_week", flat=True))
    assert days == [0, 1, 2, 3, 4], "حصّةٌ كلَّ يوم"

    assert _live(school) == live, "الحيُّ كما هو حتّى يُعتمد"
    approved.refresh_from_db()
    assert approved.status == "approved"


def test_a_settled_timetable_writes_no_second_draft(dense):
    """لا فرقَ فلا مسودّة — التشغيلُ الثاني على جدولٍ سليمٍ لا يكتب نسخةً منه."""
    school, approved = dense["school"], dense["approved"]
    ScheduleSlot.objects.filter(generation=approved, day_of_week=SUNDAY, period_number=1).update(
        day_of_week=THURSDAY
    )
    generations = ScheduleGeneration.objects.count()

    output = _run(school)

    assert "لم تُكتب مسودّة" in output
    assert ScheduleGeneration.objects.count() == generations


def test_a_live_cell_without_an_assignment_aborts_loudly(dense):
    """خانةٌ لا إسنادَ لها كانت ستسقط من المسودّة صامتة — فيُرفض السدادُ باسمها."""
    school, group = dense["school"], dense["group"]
    science = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    teacher = ScheduleSlot.objects.filter(school=school).first().teacher
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=group,
        subject=science,
        day_of_week=THURSDAY,
        period_number=2,
        start_time=time(8, 0),
        end_time=time(8, 45),
        academic_year=YEAR,
        is_active=True,
        generation=dense["approved"],
    )
    generations = ScheduleGeneration.objects.count()

    with pytest.raises(CommandError, match="بلا إسناد"):
        _run(school)

    assert ScheduleGeneration.objects.count() == generations
