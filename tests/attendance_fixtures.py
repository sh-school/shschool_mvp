"""fixtures مشتركةٌ لاختبارات رصد المعلّم الفعليّ (W-20261002-020): مدرسةٌ بجناحٍ وجرسٍ وحصّةٍ ومعلّمٍ وحامل.

تُستورد في ملفّات الاختبار بـ`from tests.attendance_fixtures import *  # noqa` فتظهر للـpytest.
"""

import datetime as dt

import pytest
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import TimeBand, Wing
from core.models.academic import WingCoverage
from operations.models import Session, TimeSlotConfig
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

SUNDAY = dt.date(2026, 9, 13)
MONDAY = dt.date(2026, 9, 14)
SATURDAY = dt.date(2026, 9, 12)
ENROLLED = dt.date(2026, 9, 1)


def at(hour, minute, second=0, day=SUNDAY):
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute, second)))


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def band(school):
    return TimeBand.objects.create(school=school, code="ground", name="الأرضيّ", floor="ground")


@pytest.fixture
def bells(school, band):
    """جرسُ الأحد: حصّتان ثمّ فسحةٌ ثمّ حصّةٌ — **آخرُ الدوام 13:30** (لا ثابتَ في الكود)."""
    for number, start, end, brk in (
        (1, dt.time(7, 10), dt.time(7, 55), False),
        (2, dt.time(8, 0), dt.time(8, 45), False),
        (3, dt.time(12, 45), dt.time(13, 30), False),
    ):
        TimeSlotConfig.objects.create(
            school=school,
            band=band,
            day_type="regular",
            period_number=number,
            start_time=start,
            end_time=end,
            is_break=brk,
        )
    return band


@pytest.fixture
def wing(school, year, holder):
    return Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=holder
    )


@pytest.fixture
def klass(school, year, wing, band):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def special_klass(school, year):
    """شعبةُ تربيةٍ خاصّة: بلا جناح عمداً (D-126م)."""
    return ClassGroupFactory(
        school=school,
        grade="G7",
        section="07/ESE",
        level_type="prep",
        academic_year=year,
        wing=None,
    )


@pytest.fixture
def kid(school, klass):
    student = UserFactory(full_name="طالب الشعبة", national_id="29300001001")
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


@pytest.fixture
def teacher(school):
    return _staff(school, "teacher", "معلّم الحصّة", "29300001010")


@pytest.fixture
def other_teacher(school):
    return _staff(school, "teacher", "معلّم آخر", "29300001011")


@pytest.fixture
def holder(school):
    return _staff(school, "admin_supervisor", "حاملُ الجناح", "29300001020")


@pytest.fixture
def session(school, klass, teacher, bells):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


def _cover(wing, substitute, start, end, by):
    return WingCoverage.objects.create(
        wing=wing, substitute=substitute, start_date=start, end_date=end, assigned_by=by
    )
