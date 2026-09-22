"""[LEGAL] تقريرُ السنة الأولى — المادة 16 من النظام الوظيفي (ADR-0002 §6.7).

«…وفقاً للمدة التي قضاها خلال هذه السنة، على ألا تقل عن ثلاثة أشهر». فمن باشر في العام ولم
يقضِ فيه ثلاثةَ أشهر لا يوضع له تقريرٌ سنويٌّ بعد. وتاريخُ المباشرة المجهولُ لا يرفض.
وقرارُ المالك (2026-09-21): منسّقُ المادة ومعلّمُ التربية الخاصة يُقيَّمان باستمارة المعلّم.
"""

from __future__ import annotations

from datetime import date

import pytest

from quality.appraisal_forms import forms_by_role
from quality.evaluation_services import _add_months, first_year_rejection
from tests.conftest import UserFactory

YEAR = "2026-2027"


def test_add_months_clamps_to_the_month_end():
    assert _add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert _add_months(date(2026, 10, 31), 3) == date(2027, 1, 31)
    assert _add_months(date(2026, 9, 12), 3) == date(2026, 12, 12)


@pytest.mark.django_db
def test_less_than_three_months_in_the_first_year_is_rejected():
    user = UserFactory(service_start_date=date(2027, 4, 1))
    assert first_year_rejection(user, YEAR, on=date(2027, 6, 1)) is not None
    assert first_year_rejection(user, YEAR, on=date(2027, 7, 1)) is None


@pytest.mark.django_db
def test_the_year_end_caps_the_served_period():
    user = UserFactory(service_start_date=date(2027, 7, 15))
    assert first_year_rejection(user, YEAR, on=date(2028, 1, 1)) is not None


@pytest.mark.django_db
def test_unknown_or_earlier_start_dates_do_not_reject():
    assert first_year_rejection(UserFactory(), YEAR, on=date(2026, 10, 1)) is None
    old = UserFactory(service_start_date=date(2019, 9, 1))
    assert first_year_rejection(old, YEAR, on=date(2026, 10, 1)) is None


@pytest.mark.django_db
def test_a_start_in_a_later_year_does_not_reject_this_year():
    user = UserFactory(service_start_date=date(2027, 10, 1))
    assert first_year_rejection(user, YEAR, on=date(2027, 10, 2)) is None


def test_coordinators_and_ese_teachers_use_the_teacher_form():
    forms = forms_by_role()
    assert forms["coordinator"].code == forms["ese_teacher"].code == forms["teacher"].code
