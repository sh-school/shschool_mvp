"""
tests/test_clinic_querysets_sent_home.py
استعلاما العيادة sent_home وneeds_notification يفلتران بالحقل الفعليّ is_sent_home
(W-20261008-001 · البند 5) — كانا يرميان FieldError لأنّ الحقل المسمّى sent_home غير موجود.
"""

import pytest

from clinic.models import ClinicVisit


def _visit(school, student, nurse, **kw):
    return ClinicVisit.objects.create(
        school=school, student=student, nurse=nurse, reason="صداع", **kw
    )


@pytest.mark.django_db
def test_sent_home_returns_only_sent_home_visits(school, teacher_user, nurse_user):
    home = _visit(school, teacher_user, nurse_user, is_sent_home=True)
    _visit(school, teacher_user, nurse_user, is_sent_home=False)
    assert list(ClinicVisit.objects.sent_home()) == [home]


@pytest.mark.django_db
def test_needs_notification_is_sent_home_and_not_yet_notified(school, teacher_user, nurse_user):
    pending = _visit(school, teacher_user, nurse_user, is_sent_home=True, parent_notified=False)
    _visit(school, teacher_user, nurse_user, is_sent_home=True, parent_notified=True)
    _visit(school, teacher_user, nurse_user, is_sent_home=False, parent_notified=False)
    assert list(ClinicVisit.objects.needs_notification()) == [pending]
