"""لوحةُ مشرف الجناح تقرأ إدخالَ الجدول مع التثبيت القديم معاً (W-20261008-003، الخيار أ، قرار D-256م).

كان مسارُ جدول الشعبة لا يكتب `PeriodConfirmation`، فتعرض لوحةُ المشرف شعبةً رُصدت كاملةً «لم تُرصد» وكلُّ حصصها «فائتة». والإصلاحُ قراءةٌ فقط:
خانةٌ بلا تثبيتٍ وفيها إدخالُ جدولٍ تُعدّ رُصدت؛ والتثبيتُ القديمُ يحكم حالتَه كما كان؛ ولا يُكتب `PeriodConfirmation` إطلاقاً (الخيار ب مؤجَّلٌ لقرار سياسة).
"""

import datetime as dt

import pytest
from django.utils import timezone

from operations.models import PeriodConfirmation, Session
from operations.services import class_grid as grid
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at
from tests.test_class_grid import _grid_on, assigned, clock, kids, subject  # noqa: F401
from wings.services import record_panels, sections_to_record

pytestmark = pytest.mark.django_db

STARTS = (dt.time(7, 10), dt.time(8, 0), dt.time(12, 45))
AFTER_SCHOOL = at(14, 0)  # كلُّ حصّةٍ لم تُرصد بعدها «فائتة»


def _sessions(school, klass, teacher, subject):
    """حصصُ اليوم الثلاث (بلا رصد) كما يولّدها الجدول."""
    return [
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            subject=subject,
            date=SUNDAY,
            start_time=start,
            end_time=(dt.datetime.combine(SUNDAY, start) + dt.timedelta(minutes=45)).time(),
            status="scheduled",
        )
        for start in STARTS
    ]


def _grid_write(user, school, klass, kids, number, status="absent"):
    return grid.save_column(
        user,
        school,
        klass.id,
        number,
        [{"student": str(kids[0].pk), "status": status, "head": ""}],
        now=at(13, 0),
    )


def _legacy_confirm(school, klass, user, start, present=2, absent=1, late=0):
    return PeriodConfirmation.objects.create(
        school=school,
        class_group=klass,
        date=SUNDAY,
        start_time=start,
        end_time=(dt.datetime.combine(SUNDAY, start) + dt.timedelta(minutes=45)).time(),
        confirmed_by=user,
        first_confirmed_at=timezone.now(),
        present_count=present,
        absent_count=absent,
        late_count=late,
    )


def _row(klass):
    return sections_to_record(klass.wing, SUNDAY, now=AFTER_SCHOOL)[0]


def test_a_section_recorded_wholly_through_the_grid_is_recorded_not_missed(
    school, assigned, teacher, subject, kids, clock
):
    _sessions(school, assigned, teacher, subject)
    for number in (1, 2, 3):
        _grid_write(teacher, school, assigned, kids, number)

    row = _row(assigned)

    assert row.statuses == ["confirmed"] * 3
    assert row.is_recorded and row.missed == 0
    assert row.shown_counts.absent_count == 1, "أرقامُ آخر حصّةٍ من إدخالات الجدول"
    assert not PeriodConfirmation.objects.exists(), "قراءةٌ فقط: لا يُكتب تثبيتٌ"


def test_a_section_confirmed_the_old_way_is_unchanged(
    school, assigned, teacher, subject, kids, clock
):
    _sessions(school, assigned, teacher, subject)
    for start in STARTS:
        _legacy_confirm(school, assigned, teacher, start, present=2, absent=1)

    row = _row(assigned)

    assert row.statuses == ["confirmed"] * 3 and row.is_recorded
    counts = row.shown_counts
    assert (counts.present_count, counts.absent_count) == (2, 1)


def test_a_mixed_section_counts_both_paths(school, assigned, teacher, subject, kids, clock):
    _sessions(school, assigned, teacher, subject)
    _grid_write(teacher, school, assigned, kids, 1)  # ح1 بالجدول
    _legacy_confirm(school, assigned, teacher, STARTS[1], present=3, absent=0)  # ح2 قديمٌ
    _legacy_confirm(school, assigned, teacher, STARTS[2], present=1, absent=2)  # ح3 قديمٌ

    row = _row(assigned)

    assert row.statuses == ["confirmed"] * 3 and row.is_recorded
    assert row.shown_counts.absent_count == 2, "آخرُ حصّةٍ رُصدت قديمةٌ فأرقامُها منها"


def test_a_section_never_recorded_stays_missed(school, assigned, teacher, subject, kids, clock):
    _sessions(school, assigned, teacher, subject)

    row = _row(assigned)

    assert row.statuses == ["missed"] * 3
    assert not row.is_recorded and row.shown is None and row.shown_counts is None


def test_a_partly_recorded_section_shows_the_recorded_period_and_misses_the_rest(
    school, assigned, teacher, subject, kids, clock
):
    _sessions(school, assigned, teacher, subject)
    _grid_write(teacher, school, assigned, kids, 1)

    row = _row(assigned)

    assert row.statuses == ["confirmed", "missed", "missed"]
    assert not row.is_recorded and row.missed == 2
    assert row.shown_counts.absent_count == 1


def test_the_panel_totals_follow_the_same_rule(school, assigned, teacher, subject, kids, clock):
    from tests.attendance_fixtures import _staff

    principal = _staff(school, "principal", "مدير اللوحة", "29000009901")
    _sessions(school, assigned, teacher, subject)
    for number in (1, 2, 3):
        _grid_write(teacher, school, assigned, kids, number)

    panels = record_panels(principal, school, assigned.wing.academic_year, SUNDAY)
    mine = next(p for p in panels if p["wing"].pk == assigned.wing.pk)

    assert (mine["done"], mine["remaining"]) == (1, 0), "شعبةٌ رُصدت بالجدول كاملاً ليست «متبقّية»"
