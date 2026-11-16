"""وجهاتُ الخروج العشر (طلب المدير 2026-11-14): ما يختاره المعلّمُ وما يُحجب عنه."""

import pytest
from django.core.exceptions import PermissionDenied

from operations.class_exit import leave, may_record_school_exit
from operations.models import ClassExit
from operations.services.class_grid import GridPage
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    _periods,
    at,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def test_there_are_ten_destinations_and_codes_fit_the_column():
    codes = [code for code, _ in ClassExit.CURRENT_DESTINATIONS]
    assert len(codes) == 10 and all(len(c) <= 10 for c in codes)
    assert {"admin", "other"} <= {c for c, _ in ClassExit.DESTINATIONS}


def test_teacher_list_is_wing_supervisor_only():
    assert [c for c, _ in ClassExit.TEACHER_DESTINATIONS] == ["wing_sup"]
    assert tuple(GridPage.__dataclass_fields__["destinations"].default) == tuple(
        ClassExit.TEACHER_DESTINATIONS
    )
    assert len(ClassExit.SUPERVISOR_DESTINATIONS) == 9


@pytest.mark.parametrize("destination", ["clinic", "restroom", "admin", "other", "bogus"])
def test_teacher_cannot_record_any_destination_but_wing_supervisor(
    school, seeded_calendar, klass, kids, teacher, destination
):
    (period,) = _periods(school, klass, teacher, 1)

    with pytest.raises(PermissionDenied):
        leave(period, kids[0], destination, by=teacher, now=at(7, 20))

    assert not ClassExit.objects.exists()


def test_teacher_wing_supervisor_exit_is_recorded(school, seeded_calendar, klass, kids, teacher):
    (period,) = _periods(school, klass, teacher, 1)

    exit_ = leave(period, kids[0], "wing_sup", by=teacher, now=at(7, 20))

    assert exit_ is not None and exit_.destination == "wing_sup"


def test_teacher_cannot_record_school_exit(school, seeded_calendar, klass, kids, teacher):
    (period,) = _periods(school, klass, teacher, 1)

    with pytest.raises(PermissionDenied):
        leave(period, kids[0], "school", by=teacher, now=at(7, 20))

    assert not ClassExit.objects.exists()
    assert not may_record_school_exit(teacher)
    assert not may_record_school_exit(None)
