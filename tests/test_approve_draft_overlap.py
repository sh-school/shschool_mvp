"""W-20261121-001: اعتمادُ مسودّةٍ فيها حصّتان على خانةٍ واحدة يُرفض برسالةٍ لا بـIntegrityError."""

from __future__ import annotations

import pytest

from operations.models import ScheduleGeneration, ScheduleSlot, Subject
from operations.services.schedule import DraftSlotOverlapError, ScheduleService
from tests.conftest import ClassGroupFactory, UserFactory

YEAR = "2026-2027"


def _slot(school, gen, group, teacher, subject, *, year=YEAR, active=False, period=2):
    import datetime as dt

    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=group,
        subject=subject,
        day_of_week=1,
        period_number=period,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        academic_year=year,
        is_active=active,
        generation=gen,
    )


@pytest.fixture
def parts(school):
    gen = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="draft", config_snapshot={}
    )
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    return gen, group, subject


@pytest.mark.django_db
def test_two_draft_slots_on_one_class_cell_are_refused_before_any_write(school, parts):
    gen, group, subject = parts
    live = _slot(school, None, group, UserFactory(), subject, active=True, period=5)
    _slot(school, gen, group, UserFactory(), subject)
    _slot(school, gen, group, UserFactory(), subject)

    with pytest.raises(DraftSlotOverlapError) as err:
        ScheduleService.approve_generation(gen, notify=False, acknowledged=True)

    assert "الاثنين" in str(err.value)
    assert "الحصّة 2" in str(err.value)
    gen.refresh_from_db()
    live.refresh_from_db()
    assert gen.status == "draft"
    assert live.is_active is True


@pytest.mark.django_db
def test_a_draft_slot_of_another_year_deactivates_the_live_slot_in_that_year(school, parts):
    gen, group, subject = parts
    other = "2025-2026"
    live = _slot(school, None, group, UserFactory(), subject, year=other, active=True)
    _slot(school, gen, group, UserFactory(), subject, year=other)

    ScheduleService.approve_generation(gen, notify=False, acknowledged=True)

    live.refresh_from_db()
    assert live.is_active is False
    assert ScheduleSlot.objects.filter(generation=gen, is_active=True).count() == 1
