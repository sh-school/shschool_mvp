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


# ── الحصصُ القائمة والورقةُ تتبعان جرس النطاق ─────────────────────────


def _slot(school, group, teacher, subject, day, period, start, end):
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=group,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=YEAR,
        is_active=True,
    )


def test_period_times_follow_the_band_and_the_day(school, bands):
    from operations.services import ScheduleService

    regular = ScheduleService.period_times(school, YEAR, band=bands["secondary"])
    thursday = ScheduleService.period_times(
        school, YEAR, band=bands["secondary"], day_type="thursday"
    )
    ground_thu = ScheduleService.period_times(
        school, YEAR, band=bands["ground"], day_type="thursday"
    )

    assert regular[7] == (dt.time(12, 25), dt.time(13, 10))
    assert thursday[7] == (dt.time(11, 50), dt.time(12, 30)), "الثانويُّ الخميسَ ينتهي 12:30"
    assert 7 not in ground_thu, "الأرضيُّ الخميسَ ستُّ حصص"


def test_resync_rewrites_the_stale_clock_of_approved_slots(school, bands):
    """جدولٌ اعتُمد قبل النطاقات يحمل الجرسَ القديم — والمصالحةُ تعيده لجرس شعبته."""
    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    ground = ClassGroupFactory(
        school=school, grade="G7", level_type="prep", academic_year=YEAR, time_band=bands["ground"]
    )
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    t1, t2 = _teacher(school, "علويّ"), _teacher(school, "أرضيّ")
    stale_thu = _slot(school, upper, t1, maths, 4, 7, dt.time(12, 35), dt.time(13, 20))
    stale_reg = _slot(school, ground, t2, maths, 0, 2, dt.time(8, 0), dt.time(8, 45))
    fine = _slot(school, upper, t1, maths, 0, 2, dt.time(8, 0), dt.time(8, 45))
    draft = ScheduleSlot.objects.create(
        school=school,
        teacher=t2,
        class_group=ground,
        subject=maths,
        day_of_week=1,
        period_number=2,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        academic_year=YEAR,
        is_active=False,
    )

    call_command("resync_slot_times", "--dry-run", "--year", YEAR)
    stale_thu.refresh_from_db()
    assert stale_thu.end_time == dt.time(13, 20), "المعاينةُ لا تكتب"

    call_command("resync_slot_times", "--year", YEAR)
    for s in (stale_thu, stale_reg, fine, draft):
        s.refresh_from_db()
    assert (stale_thu.start_time, stale_thu.end_time) == (dt.time(11, 50), dt.time(12, 30))
    assert (stale_reg.start_time, stale_reg.end_time) == (dt.time(8, 0), dt.time(8, 50))
    assert (fine.start_time, fine.end_time) == (dt.time(8, 0), dt.time(8, 45))
    assert draft.end_time == dt.time(8, 45), "المسودّاتُ تُولَّد من جديد ولا تُمَسّ"

    # idempotent: الثانيةُ لا تجد ما تعدّله
    from io import StringIO

    out = StringIO()
    call_command("resync_slot_times", "--year", YEAR, stdout=out)
    assert "updated=0" in out.getvalue()


def test_the_printed_sheet_carries_the_bands_thursday_bell(school, bands):
    """عمودُ الحصّة لشعبةٍ ثانويّة: جرسُ الأحد–الأربعاء وتحته جرسُ الخميس حين يخالفه."""
    from django.test import Client
    from django.urls import reverse

    from core.models.access import Membership, Role

    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    maths = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    teacher = _teacher(school, "علويّ")
    _slot(school, upper, teacher, maths, 4, 7, dt.time(11, 50), dt.time(12, 30))
    principal = UserFactory(full_name="المدير")
    Membership.objects.create(
        user=principal,
        school=school,
        role=Role.objects.get_or_create(school=school, name="principal")[0],
    )
    client = Client()
    client.force_login(principal)

    body = client.get(
        reverse("schedule_print") + f"?view=class&class={upper.id}&year={YEAR}",
        HTTP_HOST="localhost",
    ).content.decode()

    assert "12:25<br>13:10" in body, "جرسُ الأحد–الأربعاء للسابعة"
    assert "11:50<br>12:30" in body, "وجرسُ الخميس تحته"
    assert "13:20" not in body, "لا أثرَ للجرس القديم"

    # ومعلّمُ الطابقين لا جرسَ واحدَ له — فالعمودُ بلا وقتٍ وخاناتُه تحمل أوقاتها.
    ground = ClassGroupFactory(
        school=school, grade="G7", level_type="prep", academic_year=YEAR, time_band=bands["ground"]
    )
    _slot(school, ground, teacher, maths, 0, 2, dt.time(8, 0), dt.time(8, 50))
    body = client.get(
        reverse("schedule_print") + f"?view=teacher&teacher={teacher.id}&year={YEAR}",
        HTTP_HOST="localhost",
    ).content.decode()
    assert 'class="period-time"' not in body
    assert "08:00 – 08:50" in body and "11:50 – 12:30" in body
