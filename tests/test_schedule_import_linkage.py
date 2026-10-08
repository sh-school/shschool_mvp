"""استيرادُ الجدول بالمعرّفات وفحصُ الربط — يغطّي schedule_import وschedule_linkage_audit."""

from datetime import time

import pytest

from core.models import TimeBand
from operations import schedule_linkage_audit as audit
from operations.models import (
    ScheduleGeneration,
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
    TimeSlotConfig,
)
from operations.services.schedule_import import ScheduleImportError, import_rows
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2025-2026"


@pytest.fixture
def world(db, school):
    band = TimeBand.objects.create(school=school, code="ground", name="أرضي", order=1)
    # جرسُ النطاق: ح1 7:10–8:00 و ح2 8:00–8:50 (بيوم عاديّ)
    for n, (a, b) in {1: (time(7, 10), time(8, 0)), 2: (time(8, 0), time(8, 50))}.items():
        TimeSlotConfig.objects.create(
            school=school, band=band, period_number=n, start_time=a, end_time=b, day_type="regular"
        )
    klass = ClassGroupFactory(
        school=school, grade="G7", section="1", academic_year=YEAR, time_band=band
    )
    subject = Subject.objects.create(school=school, name_ar="رياضيات", code="M")
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلم")
    MembershipFactory(user=teacher, school=school, role=role)
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=YEAR,
    )
    return {"school": school, "klass": klass, "subject": subject, "teacher": teacher}


def _row(w, day=0, period=1, **extra):
    return {
        "class_group_id": w["klass"].id,
        "subject_id": w["subject"].id,
        "teacher_id": w["teacher"].id,
        "day": day,
        "period": period,
        **extra,
    }


def test_times_come_from_the_band_bell_not_from_the_rows(world):
    report = import_rows(world["school"], YEAR, [_row(world, 0, 2)], source="v2")
    slot = ScheduleSlot.objects.get(generation=report.generation)
    assert (slot.start_time, slot.end_time) == (time(8, 0), time(8, 50))
    assert slot.is_active is False
    assert report.generation.status == "draft"


def test_rows_with_no_live_assignment_are_refused_before_any_write(world):
    other = UserFactory(full_name="آخر")
    bad = {**_row(world), "teacher_id": other.id}
    with pytest.raises(ScheduleImportError) as exc:
        import_rows(world["school"], YEAR, [_row(world, 1, 1), bad])
    assert "السطر 2" in str(exc.value)
    assert not ScheduleGeneration.objects.filter(school=world["school"]).exists()
    assert not ScheduleSlot.objects.exists()


def test_clashes_and_out_of_range_are_named(world):
    problems = __import__("operations.services.schedule_import", fromlist=["x"]).validate_rows(
        world["school"], YEAR, [_row(world, 0, 1), _row(world, 0, 1), _row(world, 9, 1)]
    )
    assert any("شعبةٌ بحصّتين" in p for p in problems)
    assert any("معلّمٌ بحصّتين" in p for p in problems)
    assert any("خارج النطاق" in p for p in problems)


def test_approve_activates_and_audit_is_clean(world):
    import_rows(
        world["school"], YEAR, [_row(world, 0, 1), _row(world, 0, 2)], approve=True, notify=False
    )
    assert ScheduleSlot.objects.filter(is_active=True).count() == 2
    report = audit.audit(world["school"], YEAR)
    assert report.slots == 2 and report.ok, [(f.code, f.count) for f in report.blocking]


def test_audit_flags_wrong_time_unassigned_and_overlap(world):
    school, w = world["school"], world
    good = ScheduleSlot.objects.create(
        school=school,
        teacher=w["teacher"],
        class_group=w["klass"],
        subject=w["subject"],
        day_of_week=0,
        period_number=1,
        start_time=time(7, 30),
        end_time=time(8, 20),  # يخالف الجرس
        academic_year=YEAR,
        is_active=True,
    )
    other_class = ClassGroupFactory(
        school=school, grade="G7", section="2", academic_year=YEAR, time_band=w["klass"].time_band
    )
    ScheduleSlot.objects.create(  # لا إسناد + يتداخل مع الأولى بالساعة
        school=school,
        teacher=w["teacher"],
        class_group=other_class,
        subject=w["subject"],
        day_of_week=0,
        period_number=2,
        start_time=time(8, 0),
        end_time=time(8, 50),
        academic_year=YEAR,
        is_active=True,
    )
    codes = {f.code: f.count for f in audit.audit(school, YEAR).findings}
    assert (
        codes["bell_mismatch"] == 1
        and codes["no_assignment"] == 1
        and codes["teacher_overlap"] == 1
    )
    assert good.id  # لا فحصَ يكتب شيئاً
