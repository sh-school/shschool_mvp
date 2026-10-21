"""اقتراحُ العذر الطبّي من زيارة العيادة عبر مسار الأعذار القائم (W-20261020-041، قرار المالك 2026-10-21).

الزيارةُ التي يُرسَل بها الطالبُ للمنزل تقترح عذراً «بانتظار النائب» لغياب يومها: لا يتغيّر الحضورُ آلياً،
ولا يحمل الاقتراحُ نصّاً صحّيّاً، ويراه صاحبُ قدرة قبول الأعذار (النائب والمنسّق) في صفحة الأعذار المنتظرة.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from clinic.services import ClinicService
from core.permissions import EXCUSE_AFTER_DEADLINE
from operations.excuses import (
    CLINIC_PROPOSAL_NOTE,
    approve_excuse,
    pending_for_vice,
    propose_medical_excuse_from_clinic,
)
from operations.models import AbsenceExcuse, StudentAttendance
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_absence_excuses import _absent_day, vice_admin  # noqa: F401
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    kids,
    klass,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db

SECRETS = ("سببٌ-سرّيٌّ-91", "عَرَضٌ-سرّيٌّ-92", "إجراءٌ-سرّيٌّ-93")


@pytest.fixture
def absent_kid(school, seeded_calendar, klass, kids, teacher, supervisor):
    _absent_day(school, klass, kids[0], teacher, supervisor)
    return kids[0]


@pytest.fixture
def nurse(school):
    user = UserFactory(full_name="ممرّض الاختبار", national_id="29300000501")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="nurse"))
    return user


def _unexcused(student):
    return StudentAttendance.objects.filter(student=student, status="absent", excuse_type="")


def test_a_clinic_proposal_waits_pending_and_leaves_the_attendance_alone(school, absent_kid, nurse):
    before = _unexcused(absent_kid).count()
    excuse = propose_medical_excuse_from_clinic(
        student=absent_kid, school=school, day=SUNDAY, by=nurse
    )

    assert excuse is not None and excuse.status == "pending" and excuse.kind == "medical"
    assert _unexcused(absent_kid).count() == before > 0
    assert not StudentAttendance.objects.filter(excuse=excuse).exists()


def test_the_proposal_carries_no_health_text(school, absent_kid, nurse):
    excuse = propose_medical_excuse_from_clinic(
        student=absent_kid, school=school, day=SUNDAY, by=nurse
    )
    assert excuse.notes == CLINIC_PROPOSAL_NOTE
    blob = f"{excuse.notes}{excuse.override_reason}{excuse.rejection_reason}"
    assert not any(secret in blob for secret in SECRETS)


def test_no_proposal_without_an_unexcused_absence_or_when_one_is_waiting(school, absent_kid, nurse):
    other_day = SUNDAY + dt.timedelta(days=1)
    assert (
        propose_medical_excuse_from_clinic(
            student=absent_kid, school=school, day=other_day, by=nurse
        )
        is None
    )
    first = propose_medical_excuse_from_clinic(
        student=absent_kid, school=school, day=SUNDAY, by=nurse
    )
    again = propose_medical_excuse_from_clinic(
        student=absent_kid, school=school, day=SUNDAY, by=nurse
    )
    assert first is not None and again is None
    assert AbsenceExcuse.objects.filter(student=absent_kid).count() == 1


def test_recording_a_sent_home_visit_proposes_through_the_existing_path(
    school, absent_kid, nurse, monkeypatch
):
    monkeypatch.setattr(
        timezone, "localtime", lambda value: dt.datetime.combine(SUNDAY, dt.time(10))
    )
    ClinicService.record_visit(
        school=school,
        student=absent_kid,
        nurse=nurse,
        reason=SECRETS[0],
        symptoms=SECRETS[1],
        treatment=SECRETS[2],
        is_sent_home=True,
    )
    [excuse] = AbsenceExcuse.objects.filter(student=absent_kid)
    assert excuse.status == "pending" and excuse.notes == CLINIC_PROPOSAL_NOTE
    assert excuse in pending_for_vice(school)


def test_a_visit_that_is_not_sent_home_proposes_nothing(school, absent_kid, nurse):
    ClinicService.record_visit(
        school=school, student=absent_kid, nurse=nurse, reason=SECRETS[0], is_sent_home=False
    )
    assert not AbsenceExcuse.objects.filter(student=absent_kid).exists()


def test_the_decision_stays_in_the_existing_approval_path(school, absent_kid, nurse, vice_admin):
    excuse = propose_medical_excuse_from_clinic(
        student=absent_kid, school=school, day=SUNDAY, by=nurse
    )
    covered = approve_excuse(excuse, by=vice_admin, reason="تقريرٌ طبّيٌّ مرفق")
    excuse.refresh_from_db()
    assert covered > 0 and excuse.status == "accepted" and excuse.reviewed_by == vice_admin


def test_the_coordinator_holds_the_capability_and_sees_the_proposal(
    client, school, absent_kid, nurse
):
    assert "student_affairs_coordinator" in EXCUSE_AFTER_DEADLINE
    coordinator = UserFactory(full_name="منسّق شؤون الطلبة", national_id="29300000502")
    MembershipFactory(
        user=coordinator,
        school=school,
        role=RoleFactory(school=school, name="student_affairs_coordinator"),
    )
    propose_medical_excuse_from_clinic(student=absent_kid, school=school, day=SUNDAY, by=nurse)
    client.force_login(coordinator)
    response = client.get(reverse("wings:excuse_requests"))
    assert response.status_code == 200
    assert absent_kid.full_name in response.content.decode()
    assert not any(secret in response.content.decode() for secret in SECRETS)
