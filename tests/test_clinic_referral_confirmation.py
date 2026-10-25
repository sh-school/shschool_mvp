"""إشعارُ إحالة الطالب للمنزل بتأكيد الممرّض لا آليّاً (W-20261020-034، قرار المالك).

الزيارةُ التي يُحال بها الطالبُ للمنزل لا تُرسل إشعاراً لوليّ الأمر عند تسجيلها؛ يؤكّدها الممرّضُ بفعلٍ مستقلّ
فيُرسَل إشعارٌ بالحدث وحدَه (بلا السبب ولا الأعراض ولا الإجراء)، ويحترم تجميدَ الأولياء.
"""

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from clinic.models import ClinicVisit
from clinic.services import ClinicService

SECRETS = ("سببٌ-سرّيٌّ-81", "عَرَضٌ-سرّيٌّ-82", "إجراءٌ-سرّيٌّ-83")


def _sent_home_visit(school, student, nurse):
    reason, symptoms, treatment = SECRETS
    return ClinicService.record_visit(
        school=school,
        student=student,
        nurse=nurse,
        reason=reason,
        symptoms=symptoms,
        treatment=treatment,
        is_sent_home=True,
    )


@pytest.mark.django_db
def test_recording_a_referral_sends_nothing_until_the_nurse_confirms(
    school, student_user, nurse_user, parent_user
):
    mail.outbox.clear()
    visit = _sent_home_visit(school, student_user, nurse_user)
    assert visit.parent_notified is False
    assert mail.outbox == []
    assert list(ClinicVisit.objects.needs_notification()) == [visit]


@pytest.mark.django_db
def test_confirming_sends_the_event_notice_without_any_health_text(
    school, student_user, nurse_user, parent_user
):
    mail.outbox.clear()
    visit = _sent_home_visit(school, student_user, nurse_user)

    assert ClinicService.confirm_referral_notice(visit, school, nurse_user) is True

    visit.refresh_from_db()
    assert visit.parent_notified is True
    assert len(mail.outbox) == 1
    for secret in SECRETS:
        assert secret not in mail.outbox[0].subject
        assert secret not in mail.outbox[0].body


@pytest.mark.django_db
def test_confirming_twice_does_not_resend(school, student_user, nurse_user, parent_user):
    visit = _sent_home_visit(school, student_user, nurse_user)
    assert ClinicService.confirm_referral_notice(visit, school, nurse_user) is True
    mail.outbox.clear()
    assert ClinicService.confirm_referral_notice(visit, school, nurse_user) is False
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_visit_not_sent_home_cannot_be_confirmed(school, student_user, nurse_user, parent_user):
    visit = ClinicService.record_visit(
        school=school, student=student_user, nurse=nurse_user, reason="صداع", is_sent_home=False
    )
    mail.outbox.clear()
    assert ClinicService.confirm_referral_notice(visit, school, nurse_user) is False
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(PARENTS_FROZEN=True)
def test_the_parents_freeze_blocks_the_confirmed_notice(
    school, student_user, nurse_user, parent_user
):
    visit = _sent_home_visit(school, student_user, nurse_user)
    mail.outbox.clear()
    assert ClinicService.confirm_referral_notice(visit, school, nurse_user) is False
    visit.refresh_from_db()
    assert visit.parent_notified is False
    assert mail.outbox == []


@pytest.mark.django_db
def test_the_confirm_view_is_post_only_and_nurse_only(
    client_as, nurse_user, teacher_user, school, student_user, parent_user
):
    visit = _sent_home_visit(school, student_user, nurse_user)
    url = reverse("clinic:confirm_referral_notice", args=[visit.pk])

    assert client_as(nurse_user).get(url).status_code == 405
    assert client_as(teacher_user).post(url).status_code == 403
    visit.refresh_from_db()
    assert visit.parent_notified is False

    mail.outbox.clear()
    response = client_as(nurse_user).post(url)
    assert response.status_code == 302
    visit.refresh_from_db()
    assert visit.parent_notified is True
    assert len(mail.outbox) == 1
