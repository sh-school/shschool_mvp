"""بذرُ مدرسة الحمل (W-20261027-036): العدد، تساوي الأثر، الحارس، وعزلُ الكلمة عن الوسائط."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core import loadtest_seed as seed_module
from core.academic_calendar import academic_year_for_school
from core.models import AcademicYear, ClassGroup, CustomUser, Membership, School, StudentEnrollment

PASSWORD = "Lt-Pass-123!"  # pragma: allowlist secret — كلمةٌ اصطناعيّةٌ للاختبار


@pytest.mark.django_db
def test_seed_creates_requested_students_and_accounts():
    result = seed_module.seed(PASSWORD, students=65, accounts=7)
    school = School.objects.get(code=seed_module.SCHOOL_CODE)
    assert result.students == 65
    assert result.accounts == 7
    # 65 طالباً بـ30 للشعبة ⇒ ثلاثُ شُعب
    assert ClassGroup.objects.filter(school=school).count() == 3
    assert StudentEnrollment.objects.filter(class_group__school=school).count() == 65
    staff = CustomUser.objects.filter(national_id__startswith=seed_module.STAFF_PREFIX)
    assert staff.count() == 7
    roles = set(
        Membership.objects.filter(user__in=staff, school=school).values_list(
            "role__name", flat=True
        )
    )
    assert roles == {"principal"}


@pytest.mark.django_db
def test_seed_is_idempotent():
    seed_module.seed(PASSWORD, students=40, accounts=3)
    again = seed_module.seed(PASSWORD, students=40, accounts=3)
    assert (again.students, again.classes, again.accounts) == (0, 0, 0)
    assert (
        CustomUser.objects.filter(national_id__startswith=seed_module.STUDENT_PREFIX).count() == 40
    )


@pytest.mark.django_db
def test_staff_can_log_in_and_students_cannot():
    seed_module.seed(PASSWORD, students=2, accounts=1)
    assert CustomUser.objects.get(national_id=f"{seed_module.STAFF_PREFIX}001").check_password(
        PASSWORD
    )
    student = CustomUser.objects.get(national_id=f"{seed_module.STUDENT_PREFIX}00001")
    assert not student.has_usable_password()


@pytest.mark.parametrize("students, accounts", [(0, 1), (seed_module.MAX_STUDENTS + 1, 1), (1, 0)])
def test_seed_rejects_out_of_range_counts(students, accounts):
    with pytest.raises(ValueError):
        seed_module.seed(PASSWORD, students=students, accounts=accounts)


@pytest.mark.django_db
def test_command_refuses_without_password(monkeypatch):
    monkeypatch.delenv("LOADTEST_ACCOUNTS_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="LOADTEST_ACCOUNTS_PASSWORD"):
        call_command("seed_loadtest", "--students", "1", "--accounts", "1")


@pytest.mark.django_db
def test_command_refuses_production_settings(monkeypatch, settings):
    monkeypatch.setenv("LOADTEST_ACCOUNTS_PASSWORD", PASSWORD)
    settings.SETTINGS_MODULE = "shschool.settings.production"
    with pytest.raises(CommandError, match="إنتاج"):
        call_command("seed_loadtest", "--students", "1", "--accounts", "1")
    assert not School.objects.filter(code=seed_module.SCHOOL_CODE).exists()


@pytest.mark.django_db
def test_command_refuses_the_preview_database(monkeypatch, settings):
    monkeypatch.setenv("LOADTEST_ACCOUNTS_PASSWORD", PASSWORD)
    monkeypatch.setenv("PREVIEW_DB_NAME", settings.DATABASES["default"]["NAME"])
    with pytest.raises(CommandError, match="المعاينة"):
        call_command("seed_loadtest", "--students", "1", "--accounts", "1")
    assert not School.objects.filter(code=seed_module.SCHOOL_CODE).exists()


@pytest.mark.django_db
def test_command_seeds_with_password_from_environment(monkeypatch):
    monkeypatch.setenv("LOADTEST_ACCOUNTS_PASSWORD", PASSWORD)
    call_command("seed_loadtest", "--students", "5", "--accounts", "2")
    assert (
        CustomUser.objects.filter(national_id__startswith=seed_module.STUDENT_PREFIX).count() == 5
    )


@pytest.mark.django_db
def test_seed_gives_the_school_a_calendar_so_enrollments_match_the_current_year():
    seed_module.seed(PASSWORD, students=3, accounts=1)
    school = School.objects.get(code=seed_module.SCHOOL_CODE)
    assert AcademicYear.objects.filter(school=school).count() == 1
    year = academic_year_for_school(school)
    assert set(
        ClassGroup.objects.filter(school=school).values_list("academic_year", flat=True)
    ) == {year}


@pytest.mark.django_db
def test_rerun_resets_staff_password():
    seed_module.seed(PASSWORD, students=1, accounts=1)
    seed_module.seed("Another-Pass-456!", students=1, accounts=1)  # pragma: allowlist secret
    user = CustomUser.objects.get(national_id=f"{seed_module.STAFF_PREFIX}001")
    assert user.check_password("Another-Pass-456!")  # pragma: allowlist secret
