"""مدرسةُ المعاينة الثانية (W-20261004-006): التعريفُ والنطاقُ المحجوز والحارس."""

import pytest

from core import preview_accounts as first
from core import preview_school as second


def test_roles_are_first_ten_plus_two():
    assert list(second.ROLES)[:10] == list(first.ROLES)
    assert list(second.ROLES)[10:] == ["social_worker", "psychologist"]
    assert not set(second.ROLES) & second.FORBIDDEN_ROLES


def test_employee_numbers_range_and_reserved():
    nums = list(second.EMPLOYEE_NUMBERS.values())
    assert nums[0] == "99800001" and nums[-1] == "99800012" and len(set(nums)) == 12
    assert all(first.is_reserved_employee_number(n) for n in nums)
    assert not first.is_reserved_employee_number("99800013")
    assert not set(nums) & set(first.EMPLOYEE_NUMBERS.values())


def test_login_ids_carry_compound_tag():
    assert all(v.startswith(first.ID_PREFIX) for v in second.ROLES.values())
    assert len(set(second.ROLES.values())) == 12
    assert not set(second.ROLES.values()) & set(first.ROLES.values())


class _School:
    def __init__(self, code, name):
        self.code, self.name = code, name


def test_is_preview_school_needs_both_halves():
    assert second.is_preview_school(_School(second.SCHOOL_CODE, second.SCHOOL_NAME))
    assert not second.is_preview_school(_School(second.SCHOOL_CODE, "مدرسة حقيقية"))
    assert not second.is_preview_school(_School("X", second.SCHOOL_NAME))
    assert not second.is_preview_school(None)


@pytest.mark.django_db
def test_guard_flags_school_outside_preview():
    from core.models import School

    assert second.preview_school_in_wrong_environment() is False
    School.objects.create(code=second.SCHOOL_CODE, name=second.SCHOOL_NAME, is_active=True)
    assert second.preview_school_in_wrong_environment() is True


def test_injection_rejects_every_row_of_the_second_school_range():
    from academic_management import preview_reconciliation as recon

    rows = [
        {"teacher_hmac": "", "teacher_employee_number": number}
        for number in second.EMPLOYEE_NUMBERS.values()
    ]
    problems = recon.injection_violations({"assignments": rows, "workload_plans": rows})
    assert len(problems) == 2 * len(rows)


def test_injection_does_not_reject_a_number_just_outside_the_range():
    from academic_management import preview_reconciliation as recon

    problems = recon.injection_violations(
        {
            "assignments": [{"teacher_hmac": "", "teacher_employee_number": "99800013"}],
            "workload_plans": [],
        }
    )
    assert problems == []
