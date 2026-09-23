"""[LEGAL] قاعدةُ السنة الأولى (المادة 16) عبر الشاشة لا الدالّة وحدها — DBT-30.

`first_year_rejection` مُختبَرةٌ في `test_evaluation_first_year.py`، لكنّ أحداً لم يتحقّق من أنّ
العرضَ يردّ 409 فعلاً، ولا أنّ حقل «تاريخ المباشرة» يظهر في صفحة الملفّ ويُحفَظ من نموذجها —
فلو انقطع الوصلُ بين الدالّة والشاشة لمرّ الاختبارُ الأوّل وبقيت القاعدةُ ميّتةً.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from quality.appraisal_forms import forms_by_role
from quality.models import EmployeeEvaluation
from tests.test_evaluation_review_round1 import _seed, _staff, _url
from tests.test_evaluation_review_round3 import _post_total

pytestmark = pytest.mark.django_db


def _started(employee, on):
    employee.service_start_date = on
    employee.save(update_fields=["service_start_date"])
    return employee


def test_the_screen_refuses_a_first_year_report_before_three_months(client, school, principal_user):
    _seed(school)
    employee = _started(_staff(school, "teacher"), timezone.localdate())
    client.force_login(principal_user)

    assert client.get(_url(employee)).status_code == 409
    form = forms_by_role()["teacher"]
    assert client.post(_url(employee), _post_total(form, 80)).status_code == 409
    assert not EmployeeEvaluation.objects.filter(employee=employee).exists(), "الرفضُ لا يترك مسودّة"


def test_the_screen_accepts_a_report_for_someone_with_a_long_service(
    client, school, principal_user
):
    _seed(school)
    employee = _started(_staff(school, "teacher"), date(2019, 9, 1))
    client.force_login(principal_user)

    assert client.get(_url(employee)).status_code == 200


def test_the_start_date_is_shown_on_the_profile_and_saved_from_its_form(
    client_as, school, principal_user, teacher_user
):
    _started(teacher_user, date(2024, 9, 1))
    client = client_as(principal_user)

    page = client.get(
        reverse("staff_affairs:staff_profile", args=[teacher_user.id])
    ).content.decode()
    assert 'name="service_start_date"' in page
    assert 'value="2024-09-01"' in page

    client.post(
        reverse("staff_affairs:staff_profile_save", args=[teacher_user.id, "person"]),
        {
            "full_name": teacher_user.full_name,
            "employee_number": teacher_user.employee_number or "",
            "email": teacher_user.email or "",
            "phone": teacher_user.phone or "",
            "nationality": teacher_user.nationality or "",
            "service_start_date": "2025-01-15",
            "professional_license_number": "",
            "professional_license_expiry": "",
        },
    )
    teacher_user.refresh_from_db()
    assert teacher_user.service_start_date == date(2025, 1, 15)
