"""أمرُ بذر الخروج للمعاينة: متساوي الأثر، ويرفض خارج المعاينة (W-20261010-041)."""

import datetime as dt

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.preview_accounts import EMPLOYEE_NUMBERS
from operations.management.commands.seed_preview_exit_tally import Command, last_school_day
from operations.models import ClassExit, Session, Subject, SubjectClassAssignment
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED
from tests.conftest import StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

THURSDAY = dt.date(2026, 10, 8)


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def assigned(school, year, klass, teacher, subject):
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    return klass


@pytest.fixture
def kids(assigned):
    people = []
    for index in range(5):
        student = UserFactory(full_name=f"طالب {index}", national_id=f"2900000300{index}")
        StudentEnrollmentFactory(student=student, class_group=assigned, enrolled_at=ENROLLED)
        people.append(student)
    return people


def test_the_command_refuses_outside_preview():
    with pytest.raises(CommandError):
        call_command("seed_preview_exit_tally")


def test_the_default_day_skips_the_rest_days():
    assert last_school_day(dt.date(2026, 10, 10)) == THURSDAY  # السبت
    assert last_school_day(dt.date(2026, 10, 9)) == THURSDAY  # الجمعة
    assert last_school_day(THURSDAY) == THURSDAY


def _sessions(school, klass, teacher, subject):
    for number, hour in ((1, 7), (2, 8)):
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            subject=subject,
            date=THURSDAY,
            start_time=dt.time(hour, 10),
            end_time=dt.time(hour, 55),
            period_number=number,
        )


def test_seeding_is_idempotent_and_leaves_the_last_student_without_exits(
    school, assigned, teacher, kids, subject
):
    teacher.employee_number = EMPLOYEE_NUMBERS["teacher"]
    teacher.save(update_fields=["employee_number"])
    _sessions(school, assigned, teacher, subject)
    command = Command()
    command.seed(school, THURSDAY)
    command.seed(school, THURSDAY)
    rows = ClassExit.objects.filter(session__date=THURSDAY)
    assert rows.count() == 7  # 1 + 3 + 1 + 2
    assert not rows.filter(student=kids[-1]).exists()
    # الطالبُ الرابع خرج من حصّتَين ⇒ دائرتان
    assert rows.filter(student=kids[3]).values("session").distinct().count() == 2


def test_a_class_without_sessions_that_day_seeds_nothing(school, assigned, teacher, kids):
    teacher.employee_number = EMPLOYEE_NUMBERS["teacher"]
    teacher.save(update_fields=["employee_number"])
    Command().seed(school, THURSDAY)
    assert not ClassExit.objects.exists()
