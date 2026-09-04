"""نطاقاتُ التوقيت: طابقان بجرسين، ومعلّمُ الطابقين يُحكَم بالساعة.

الحصّةُ الثانية في الأرضيّ 8:00–8:50 والثالثةُ في العلويّ 8:45–9:35: رقمان
مختلفان يتداخلان خمسَ دقائق، ولا يراه الحكمُ بالرقم (HC1). فيُمنع التداخلُ
بالساعة (HC12)، ويُجاز التماسُّ (نهايةٌ = بداية) مع عقوبةٍ مرنة، وتُكتب
أوقاتُ الحصص من جرس نطاق شعبتها.
"""

import datetime as dt

import pytest
from django.core.management import call_command

from core.models import TimeBand
from operations.models import ScheduleSlot, Subject, SubjectClassAssignment, TimeSlotConfig
from operations.scheduler import ScheduleGrid, build_tasks, generate_schedule, load_band_times
from operations.scheduler_constraints import (
    check_teacher_time_overlap,
    evaluate_soft_constraints,
)
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def _teacher(school, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


def _assign(school, group, user, subject, periods):
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
def bands(school):
    call_command("seed_time_bands")
    return {b.code: b for b in TimeBand.objects.filter(school=school)}


def test_seed_is_idempotent(school):
    call_command("seed_time_bands")
    n1 = TimeSlotConfig.objects.filter(school=school).count()
    call_command("seed_time_bands")
    assert TimeSlotConfig.objects.filter(school=school).count() == n1
    assert TimeBand.objects.filter(school=school).count() == 3
    assert n1 == 9 + 9 + 9 + 8 + 8 + 9


def test_ground_second_period_overlaps_upper_third_by_the_clock(school, bands):
    ground = ClassGroupFactory(
        school=school, grade="G7", level_type="prep", academic_year=YEAR, time_band=bands["ground"]
    )
    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = _teacher(school, "معلّمُ الطابقين")
    _assign(school, ground, teacher, maths, 1)
    _assign(school, upper, teacher, maths, 1)

    t_ground, t_upper = sorted(build_tasks(school, YEAR), key=lambda t: t.level_type == "sec")
    grid = ScheduleGrid(band_times=load_band_times(school))
    grid.place(0, 2, t_ground)  # الأحد ح2 أرضيّ 8:00–8:50

    assert check_teacher_time_overlap(grid, 0, 3, t_upper) is False, "8:45–9:35 تتداخل مع 8:00–8:50"
    assert check_teacher_time_overlap(grid, 0, 4, t_upper) is True, "9:35–10:25 لا تتداخل"


def test_touching_is_allowed_but_penalised(school, bands):
    ground = ClassGroupFactory(
        school=school, grade="G7", level_type="prep", academic_year=YEAR, time_band=bands["ground"]
    )
    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = _teacher(school, "معلّمُ الطابقين")
    _assign(school, ground, teacher, maths, 1)
    _assign(school, upper, teacher, maths, 1)
    t_ground, t_upper = sorted(build_tasks(school, YEAR), key=lambda t: t.level_type == "sec")
    grid = ScheduleGrid(band_times=load_band_times(school))
    grid.place(0, 3, t_ground)  # أرضيّ ح3 8:50–9:35

    # علويّ ح4 9:35–10:25: تماسٌّ لا تداخل
    assert check_teacher_time_overlap(grid, 0, 4, t_upper) is True
    penalty = evaluate_soft_constraints(grid, 0, 4, t_upper)
    assert "band_transition" in penalty.details


def test_without_band_config_the_clock_rule_is_silent(school):
    ground = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = _teacher(school, "معلّم")
    _assign(school, ground, teacher, maths, 1)
    (task,) = build_tasks(school, YEAR)
    grid = ScheduleGrid(band_times=load_band_times(school))

    assert grid.band_times == {}
    assert check_teacher_time_overlap(grid, 0, 2, task) is True


def test_generated_slots_carry_their_bands_clock(school, bands):
    ground = ClassGroupFactory(
        school=school, grade="G7", level_type="prep", academic_year=YEAR, time_band=bands["ground"]
    )
    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    _assign(school, ground, _teacher(school, "أرضيّ"), maths, 5)
    _assign(school, upper, _teacher(school, "علويّ"), maths, 5)

    result = generate_schedule(school, YEAR)

    assert result["errors"] == []
    g2 = ScheduleSlot.objects.filter(class_group=ground, period_number=2, day_of_week__lt=4).first()
    u2 = ScheduleSlot.objects.filter(class_group=upper, period_number=2, day_of_week__lt=4).first()
    if g2:
        assert (g2.start_time, g2.end_time) == (dt.time(8, 0), dt.time(8, 50))
    if u2:
        assert (u2.start_time, u2.end_time) == (dt.time(8, 0), dt.time(8, 45))
    thu = ScheduleSlot.objects.filter(class_group=upper, day_of_week=4).first()
    if thu:
        cfg = TimeSlotConfig.objects.get(
            school=school,
            band=bands["secondary"],
            day_type="thursday",
            period_number=thu.period_number,
        )
        assert (thu.start_time, thu.end_time) == (cfg.start_time, cfg.end_time)


def test_a_two_floor_teacher_never_overlaps_by_the_clock(school, bands):
    """جدولٌ كامل لمعلّمٍ يقطع الطابقين: لا حصّتان له تتداخلان بالساعة في يوم."""
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = _teacher(school, "معلّمُ الطابقين")
    for grade, level, band in (
        ("G7", "prep", "ground"),
        ("G8", "prep", "ground"),
        ("G10", "sec", "secondary"),
        ("G11", "sec", "secondary"),
    ):
        group = ClassGroupFactory(
            school=school, grade=grade, level_type=level, academic_year=YEAR, time_band=bands[band]
        )
        _assign(school, group, teacher, maths, 5)

    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    by_day: dict[int, list] = {}
    for s in ScheduleSlot.objects.filter(teacher=teacher, is_active=True):
        by_day.setdefault(s.day_of_week, []).append((s.start_time, s.end_time))
    for day, spans in by_day.items():
        spans.sort()
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            assert e1 <= s2, f"تداخلٌ يوم {day}: {s1}-{e1} مع {s2}-{e2}"
