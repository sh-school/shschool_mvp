"""أسبوعٌ فعليّ من حصص الأيّام — قارئُ الجدول الديناميكيّ (2026-09-25).

الجدولُ الأسبوعيّ كان يقرأ الخطّةَ المعتمدة وحدَها فلا يظهر فيه إشغالٌ ولا تبديلٌ ولا تعويضٌ ولا
إجازة. والقارئُ الجديدُ يبني الشكلَ نفسَه (`{يوم: {حصّة: [خانة]}}`) من `Session`، ويعرض من الخطّة
ما لم يُولَّد بعد، ولا يكتب في القاعدة.
"""

import datetime as dt

import pytest
from django.core.management import call_command

from core.models import TimeBand
from operations.models import (
    CompensatorySession,
    ScheduleSlot,
    Session,
    Subject,
    TeacherAbsence,
)
from operations.services import ScheduleService, SubstituteService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUNDAY = dt.date(2026, 10, 11)
#: إجازةُ منتصف الفصل الأوّل: 25–29 أكتوبر — الأسبوعُ كلُّه مغلق.
BREAK_SUNDAY = dt.date(2026, 10, 25)


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _slot(w, klass, teacher, day, period, start, end, subject):
    return ScheduleSlot.objects.create(
        school=w["school"],
        teacher=teacher,
        class_group=w[klass],
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=YEAR,
    )


@pytest.fixture
def world(school, seeded_calendar):
    call_command("seed_time_bands")
    bands = {b.code: b for b in TimeBand.objects.filter(school=school)}
    w = {
        "school": school,
        "math": Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
        "science": Subject.objects.create(school=school, name_ar="العلوم", code="SCI"),
        "t1": _teacher(school, "معلّمُ الرياضيات"),
        "t2": _teacher(school, "معلّمُ العلوم"),
        "sub": _teacher(school, "البديل"),
        "upper": ClassGroupFactory(
            school=school,
            grade="G10",
            level_type="sec",
            academic_year=YEAR,
            time_band=bands["secondary"],
        ),
        "ground": ClassGroupFactory(
            school=school,
            grade="G7",
            level_type="prep",
            academic_year=YEAR,
            time_band=bands["ground"],
        ),
    }
    w["s1"] = _slot(w, "upper", w["t1"], 0, 1, dt.time(7, 10), dt.time(8, 0), w["math"])
    w["s2"] = _slot(w, "upper", w["t2"], 0, 2, dt.time(8, 0), dt.time(8, 45), w["science"])
    w["s3"] = _slot(w, "ground", w["t1"], 2, 3, dt.time(8, 50), dt.time(9, 35), w["math"])
    w["s4"] = _slot(w, "upper", w["t2"], 4, 6, dt.time(11, 10), dt.time(11, 50), w["science"])
    return w


def _generate(w):
    ScheduleService.ensure_sessions_for_date(w["school"], SUNDAY, academic_year=YEAR)


def _week(w, start=SUNDAY, **kw):
    return ScheduleService.get_week_schedule(w["school"], start, academic_year=YEAR, **kw)


def _cells(result):
    return sorted(
        (c.day_of_week, c.period_number, c.source, c.kind)
        for day in result["grid"].values()
        for cells in day.values()
        for c in cells
    )


def _only(result):
    """الخانةُ الوحيدةُ في الشبكة — وإلّا يسقط الاختبارُ برقمها الفعليّ."""
    cells = [
        c
        for periods in result["grid"].values()
        for cell_list in periods.values()
        for c in cell_list
    ]
    assert len(cells) == 1, f"خاناتٌ {len(cells)} لا واحدة"
    return cells[0]


class TestAWeekThatWasNotGeneratedComesFromThePlan:
    def test_every_day_is_projected_and_marked(self, world):
        result = _week(world)

        assert result["week"].plan_days == {0, 1, 2, 3, 4}
        assert _cells(result) == [
            (0, 1, "plan", ""),
            (0, 2, "plan", ""),
            (2, 3, "plan", ""),
            (4, 6, "plan", ""),
        ]
        cell = result["grid"][0][1][0]
        assert (cell.teacher, cell.class_group, cell.subject.name_ar) == (
            world["t1"],
            world["upper"],
            "الرياضيات",
        ), "الخانةُ تفوّض إلى الخانة الأصليّة"
        assert (cell.start_time, cell.end_time) == (dt.time(7, 10), dt.time(8, 0))

    def test_reading_writes_nothing(self, world):
        _week(world)

        assert not Session.objects.exists(), "القراءةُ لا تولّد حصصاً"

    def test_a_partly_generated_week_mixes_both_by_day(self, world):
        _generate(world)
        Session.objects.filter(date=SUNDAY + dt.timedelta(days=2)).delete()  # الثلاثاء

        result = _week(world)

        assert result["week"].plan_days == {2}
        assert _cells(result) == [
            (0, 1, "actual", ""),
            (0, 2, "actual", ""),
            (2, 3, "plan", ""),
            (4, 6, "actual", ""),
        ]


class TestTheActualWeek:
    def test_a_generated_week_is_read_from_the_lessons_with_their_stored_number(self, world):
        _generate(world)

        result = _week(world)

        assert result["week"].plan_days == set()
        assert [(d, p) for d, p, *_ in _cells(result)] == [(0, 1), (0, 2), (2, 3), (4, 6)]
        assert {c[2] for c in _cells(result)} == {"actual"}

    def test_the_shape_matches_the_plans_grid(self, world):
        _generate(world)

        actual = _week(world)["grid"]
        plan = ScheduleService.get_weekly_schedule(world["school"], None, None, YEAR)

        keys = lambda g: {  # noqa: E731
            (d, p): len(cells) for d, periods in g.items() for p, cells in periods.items()
        }
        assert keys(actual) == keys(plan), "الورقةُ نفسُها تقرؤهما بلا تمييز"

    def test_a_handed_over_lesson_follows_its_holder(self, world):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])

        theirs = _week(world, teacher=world["sub"])
        original = _week(world, teacher=world["t1"])

        cell = _only(theirs)
        assert (cell.kind, cell.original_teacher) == ("swap", world["t1"])
        assert (cell.day_of_week, cell.period_number) == (0, 1)
        assert [c[:2] for c in _cells(original)] == [(2, 3)], "من أُشغل عنه لا تظهر عنده"

    def test_a_cover_is_told_from_a_swap_by_its_assignment(self, world):
        _generate(world)
        absence = SubstituteService.register_absence(world["school"], world["t1"], SUNDAY, "sick")
        SubstituteService.assign_substitute(absence, world["s1"], world["sub"])

        cell = _only(_week(world, teacher=world["sub"]))

        assert cell.kind == "cover"

    def test_a_compensation_is_marked(self, world):
        _generate(world)
        lesson = Session.objects.get(date=SUNDAY, teacher=world["t2"], period_number=2)
        lesson.original_teacher = lesson.teacher
        lesson.teacher = world["sub"]
        lesson.save()
        absence = TeacherAbsence.objects.create(
            school=world["school"], teacher=world["sub"], date=SUNDAY - dt.timedelta(days=3)
        )
        CompensatorySession.objects.create(
            school=world["school"],
            teacher=world["sub"],
            original_slot=world["s3"],
            absence=absence,
            compensatory_date=SUNDAY,
            compensatory_period=2,
            class_group=world["upper"],
            subject=world["math"],
            status="approved",
            session_created=lesson,
        )

        cell = _only(_week(world, teacher=world["sub"]))

        assert (cell.kind, cell.original_teacher) == ("comp", world["t2"])

    def test_a_class_filter_keeps_that_class_only(self, world):
        _generate(world)

        result = _week(world, class_group=world["ground"])

        assert [c[:2] for c in _cells(result)] == [(2, 3)]

    def test_a_teacher_with_no_lessons_on_a_day_does_not_make_it_ungenerated(self, world):
        _generate(world)

        result = _week(world, teacher=world["t1"])

        assert result["week"].plan_days == set(), "اليومُ وُلّد للمدرسة، ولو خلا منه هذا المعلّم"


class TestClosedDays:
    def test_a_holiday_week_has_no_cells_and_names_the_reason(self, world):
        result = _week(world, BREAK_SUNDAY)

        assert set(result["week"].closed) == {0, 1, 2, 3, 4}
        assert result["week"].closed[0] == "إجازة منتصف الفصل الأول"
        assert result["week"].plan_days == set(), "لا تُسقَط الخطّةُ على يوم إجازة"
        assert _cells(result) == []

    def test_a_normal_week_has_no_closed_day(self, world):
        assert _week(world)["week"].closed == {}


class TestLessonsWithoutAStoredNumber:
    def test_the_number_is_derived_from_the_bell_of_the_class_band(self, world):
        session = Session.objects.create(
            school=world["school"],
            teacher=world["t1"],
            class_group=world["upper"],
            subject=world["math"],
            date=SUNDAY,
            start_time=dt.time(8, 45),
            end_time=dt.time(9, 35),
        )  # ثالثةُ الطابق الأوّل الأحد، ولم تُعبَّأ

        result = _week(world)

        assert [(c[0], c[1]) for c in _cells(result)] == [(0, 3)]
        session.refresh_from_db()
        assert session.period_number is None, "القراءةُ لا تكتب الرقم"

    def test_a_lesson_that_matches_no_bell_is_counted_not_hidden(self, world):
        Session.objects.create(
            school=world["school"],
            teacher=world["t1"],
            class_group=world["upper"],
            subject=world["math"],
            date=SUNDAY,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 45),
        )

        result = _week(world)

        assert (_cells(result), result["week"].unplaced) == ([], 1)


class TestTheWeekItself:
    def test_any_day_of_the_week_gives_its_sunday_to_thursday(self, world):
        result = _week(world, SUNDAY + dt.timedelta(days=3))  # الأربعاء

        week = result["week"]
        assert (week.week_start, week.week_end) == (SUNDAY, SUNDAY + dt.timedelta(days=4))
        assert len(week.days) == 5

    def test_the_queries_do_not_grow_with_the_lessons(self, world, django_assert_max_num_queries):
        _generate(world)
        for i in range(30):
            teacher = _teacher(world["school"], f"معلّم {i}")
            klass = ClassGroupFactory(
                school=world["school"], grade="G8", level_type="prep", academic_year=YEAR
            )
            _slot(
                {**world, "x": klass},
                "x",
                teacher,
                1,
                2,
                dt.time(8, 0),
                dt.time(8, 50),
                world["math"],
            )
        ScheduleService.ensure_sessions_for_date(
            world["school"], SUNDAY + dt.timedelta(days=1), academic_year=YEAR
        )

        with django_assert_max_num_queries(9):
            ScheduleService.get_week_schedule(world["school"], SUNDAY, academic_year=YEAR)


class TestTheGeneralScheduleForAWeek:
    def test_rows_follow_the_holder_and_carry_the_week(self, world):
        _generate(world)
        SubstituteService.hand_over_session(world["school"], world["s1"], SUNDAY, world["sub"])

        result = ScheduleService.get_week_matrix(world["school"], SUNDAY, academic_year=YEAR)

        rows = {r["teacher"].full_name: r for r in result["rows"]}
        assert set(rows) == {"معلّمُ الرياضيات", "معلّمُ العلوم", "البديل"}
        assert rows["البديل"]["total"] == 1 and rows["البديل"]["days"][0][0][0].kind == "swap"
        assert rows["معلّمُ الرياضيات"]["total"] == 1, "بقيت له الثلاثاءُ وحدَها"
        assert result["week"].week_start == SUNDAY

    def test_the_plans_matrix_is_unchanged(self, world):
        rows = ScheduleService.get_teachers_matrix(world["school"], YEAR)

        assert {r["teacher"].full_name: r["total"] for r in rows} == {
            "معلّمُ الرياضيات": 2,
            "معلّمُ العلوم": 2,
        }
