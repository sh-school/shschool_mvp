"""أمرُ بذر الخروج للمعاينة: متساوي الأثر، ويرفض خارج المعاينة (W-20261010-041)."""

import datetime as dt

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.preview_accounts import EMPLOYEE_NUMBERS
from operations.management.commands.seed_preview_exit_tally import Command, last_school_day
from operations.models import DailyExitTally, Subject, SubjectClassAssignment
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
    for index in range(4):
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


def test_seeding_is_idempotent_and_leaves_the_last_student_without_exits(
    school, assigned, teacher, kids
):
    teacher.employee_number = EMPLOYEE_NUMBERS["teacher"]
    teacher.save(update_fields=["employee_number"])
    command = Command()
    command.seed(school, THURSDAY)
    command.seed(school, THURSDAY)
    rows = DailyExitTally.objects.filter(date=THURSDAY)
    assert rows.count() == 3
    assert sorted(r.exit_count for r in rows) == [1, 1, 3]
    assert not rows.filter(student=kids[-1]).exists()


def test_a_class_too_small_to_show_every_case_is_skipped(school, assigned, teacher, kids, subject):
    from tests.conftest import ClassGroupFactory

    small = ClassGroupFactory(
        school=school, academic_year=assigned.academic_year, grade=1, section="A"
    )
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=small,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=assigned.academic_year,
    )
    StudentEnrollmentFactory(
        student=UserFactory(national_id="29000009991"), class_group=small, enrolled_at=ENROLLED
    )
    teacher.employee_number = EMPLOYEE_NUMBERS["teacher"]
    teacher.save(update_fields=["employee_number"])
    Command().seed(school, THURSDAY)
    assert DailyExitTally.objects.filter(date=THURSDAY).count() == 3
