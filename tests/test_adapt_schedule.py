"""[SCHEDULE] تكييفُ الجدول الحيّ بعد تغيير إسنادٍ بأقلّ اضطراب (SCH-14).

يتغيّر الإسنادُ بعد اعتماد الجدول، والتوليدُ الكاملُ يعيد ترتيبَ ثمانمئةٍ وتسعٍ وستّين حصّةً
ليتغيّر إسنادٌ واحد. فالتكييفُ يُثبّت ما لم يتغيّر ويضع الجديدَ وحدَه: معلّمٌ جديدٌ لمادّةٍ
يرث خاناتِ القديم، وحصّةٌ زائدةٌ تُوضع في أنسب خانةٍ فارغة، وما لا موضعَ له يُقال بسببه ولا
تُكتب مسودّةٌ ناقصة. والحيُّ لا يُمَسّ في كلّ الأحوال حتّى يُعتمد الناتج.
"""

from datetime import time
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from operations.models import ScheduleGeneration, ScheduleSlot, Subject, SubjectClassAssignment
from operations.scheduler_adapt import adapt_live
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture
def world(school):
    """شعبةٌ واحدة، رياضياتُها خمسُ حصصٍ عند معلّمٍ، حصّةً كلَّ يومٍ في موضعٍ مختلف — جدولٌ حيّ.

    ومواضعُها مختلفةٌ عمداً: تكرارُ الموضع نفسِه أكثرَ من مرّتين في الأسبوع يخالف HC7، فيرفض
    التكييفُ وراثتَه — وهو ما يفعله بجدولٍ سليم لا ما يفعله بهذا.
    """
    old, new = _teacher(school, "المعلّم القديم"), _teacher(school, "المعلّم الجديد")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    assignment = SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=old,
        class_group=group,
        subject=maths,
        weekly_periods=5,
        is_active=True,
    )
    approved = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="approved"
    )
    for day, period in enumerate((2, 4, 3, 5, 1)):
        ScheduleSlot.objects.create(
            school=school,
            teacher=old,
            class_group=group,
            subject=maths,
            day_of_week=day,
            period_number=period,
            start_time=time(8, 0),
            end_time=time(8, 45),
            academic_year=YEAR,
            is_active=True,
            generation=approved,
        )
    return {
        "school": school,
        "old": old,
        "new": new,
        "group": group,
        "maths": maths,
        "assignment": assignment,
        "approved": approved,
    }


def _live(school):
    return sorted(
        ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True).values_list(
            "id", "teacher_id", "day_of_week", "period_number"
        )
    )


def test_a_new_teacher_inherits_the_cells_of_the_old_one_and_nothing_else_moves(world):
    school = world["school"]
    SubjectClassAssignment.objects.filter(pk=world["assignment"].pk).update(teacher=world["new"])
    live = _live(school)

    outcome = adapt_live(school, YEAR, dry_run=False)

    assert outcome["orphan_tasks"] == 5 and outcome["orphan_cells"] == 5
    assert outcome["placed"] == 5 and outcome["unplaced"] == []
    assert outcome["settlement"]["moves"] == {"inherited": 5, "searched": 0}
    assert len(outcome["changes"]) == 5, "خمسُ خاناتٍ تغيّر معلّمُها — لا شيءَ سواها"
    assert sorted(row["period"] for row in outcome["changes"]) == [
        1,
        2,
        3,
        4,
        5,
    ], "في مواضعها نفسِها"
    draft = outcome["generation"]
    assert draft.status == "draft" and draft.config_snapshot["mode"] == "adapt"
    assert draft.config_snapshot["source_generation"] == str(world["approved"].pk)
    rows = ScheduleSlot.objects.filter(generation=draft)
    assert rows.count() == 5 and not rows.filter(is_active=True).exists()
    assert set(rows.values_list("teacher_id", flat=True)) == {world["new"].pk}
    assert _live(school) == live, "الحيُّ كما هو حتّى يُعتمد"


def test_an_extra_weekly_period_is_placed_in_a_free_cell_and_the_rest_stay(world):
    school = world["school"]
    SubjectClassAssignment.objects.filter(pk=world["assignment"].pk).update(weekly_periods=6)

    outcome = adapt_live(school, YEAR, dry_run=True)

    assert outcome["orphan_tasks"] == 1 and outcome["orphan_cells"] == 0
    assert outcome["placed"] == 1 and outcome["unplaced"] == []
    assert len(outcome["changes"]) == 1, "خانةٌ واحدةٌ امتلأت — والخمسُ الباقيةُ في مواضعها"
    assert outcome["changes"][0]["before"] == "" and "الرياضيات" in outcome["changes"][0]["after"]
    assert outcome["generation"] is None, "العرضُ الجافُّ لا يكتب"


def test_a_lesson_with_no_room_is_named_with_its_blockers_and_no_draft_is_written(world):
    """شعبةٌ خاناتُها كلُّها مشغولة: الحصّةُ الزائدةُ بلا موضعٍ ولا تُكتب مسودّةٌ ناقصة."""
    school, group, old = world["school"], world["group"], world["old"]
    generation = world["approved"]
    filler = _teacher(school, "معلّم الحشو")
    ScheduleSlot.objects.filter(generation=generation).delete()
    lessons = [(day, period) for day in range(5) for period in range(1, 8)]
    for index, (day, period) in enumerate(lessons):
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"S{index}")
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=filler,
            class_group=group,
            subject=subject,
            weekly_periods=1,
            is_active=True,
        )
        ScheduleSlot.objects.create(
            school=school,
            teacher=filler,
            class_group=group,
            subject=subject,
            day_of_week=day,
            period_number=period,
            start_time=time(8, 0),
            end_time=time(8, 45),
            academic_year=YEAR,
            is_active=True,
            generation=generation,
        )
    SubjectClassAssignment.objects.filter(pk=world["assignment"].pk).update(weekly_periods=1)
    generations = ScheduleGeneration.objects.count()

    outcome = adapt_live(school, YEAR, dry_run=False)

    assert old and outcome["placed"] == 0 and len(outcome["unplaced"]) == 1
    assert "تعذر وضع: الرياضيات" in outcome["unplaced"][0]
    assert "أكثرُ ما منعها" in outcome["unplaced"][0] and "الشعبة" in outcome["unplaced"][0]
    assert outcome["generation"] is None
    assert ScheduleGeneration.objects.count() == generations, "لا مسودّةَ ناقصة"


def test_a_timetable_that_matches_the_assignments_has_nothing_to_adapt(world):
    from operations.scheduler_live import LiveScheduleError

    with pytest.raises(LiveScheduleError, match="يطابق الإسنادات"):
        adapt_live(world["school"], YEAR)


def test_the_command_reports_the_placement_and_the_reason_it_could_not(world):
    school = world["school"]
    SubjectClassAssignment.objects.filter(pk=world["assignment"].pk).update(teacher=world["new"])
    out = StringIO()

    call_command(
        "settle_schedule",
        "--adapt",
        "--dry-run",
        "--school",
        school.code,
        "--year",
        YEAR,
        stdout=out,
    )

    text = out.getvalue()
    assert "وُرِّث خانةَ الإسناد القديم 5" in text
    assert "الخانات المتغيّرة (5)" in text
    assert "عرضٌ فقط" in text


def test_the_command_refuses_when_there_is_nothing_to_adapt(world):
    with pytest.raises(CommandError, match="يطابق الإسنادات"):
        call_command(
            "settle_schedule",
            "--adapt",
            "--school",
            world["school"].code,
            "--year",
            YEAR,
            stdout=StringIO(),
        )


def test_settling_after_the_adaptation_reports_its_moves_and_keeps_the_placement(world):
    school = world["school"]
    SubjectClassAssignment.objects.filter(pk=world["assignment"].pk).update(weekly_periods=6)

    outcome = adapt_live(school, YEAR, dry_run=True, settle_after=True, budget=20)

    assert outcome["placed"] == 1 and outcome["unplaced"] == []
    assert {"inherited", "searched", "move", "swap", "eject"} <= set(outcome["settlement"]["moves"])
    assert outcome["after"]["count"] == 0, "جدولٌ سليمٌ يبقى سليماً"
