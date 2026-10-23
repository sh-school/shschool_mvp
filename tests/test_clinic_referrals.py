"""
tests/test_clinic_referrals.py — الإحالات وإيصالها (W-20261020-038)

الإخفاءُ الجزئيّ للاسم، وغيابُ التشخيص من الإيصال، وحصرُ الإيصال والقائمة بالممرّض،
وتفريقُ القائمة بين المفتوحة والمغلقة، وتسجيلُ كلّ فتحٍ للإيصال.
"""

import pytest
from django.test import Client
from django.urls import reverse

from clinic import choices
from clinic.models import ClinicReferral, ClinicVisit
from clinic.referrals import close_referral, mask_person_name, open_referral
from clinic.services import ClinicService
from core.models.audit import AuditLog


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def _referral(school, nurse_user, student_user, party="health_center"):
    visit = ClinicService.start_visit(school, student_user, nurse_user)
    ClinicService.close_visit(visit, choices.OUTCOME_REFERRAL, party)
    return visit.referral


def test_mask_person_name_keeps_only_the_first_name():
    assert mask_person_name("أحمد محمد علي") == "أحمد م*** ع***"
    assert mask_person_name("أحمد") == "أحمد"
    assert mask_person_name("") == ""


@pytest.mark.django_db
def test_closing_with_referral_opens_one_numbered_referral(school, nurse_user, student_user):
    ref = _referral(school, nurse_user, student_user)
    assert (ref.serial_no, ref.status, ref.follow_up_party) == (
        1,
        choices.REFERRAL_OPEN,
        "health_center",
    )
    assert open_referral(ref.visit, "hospital").pk == ref.pk  # لا ثانية للزيارة نفسها
    assert ClinicReferral.objects.count() == 1


@pytest.mark.django_db
def test_serial_numbers_grow_per_school(school, nurse_user, student_user, django_user_model):
    first = _referral(school, nurse_user, student_user)
    other_student = django_user_model.objects.create(
        full_name="طالب ثانٍ", national_id="28888888888"
    )
    second = _referral(school, nurse_user, other_student, "parent")
    assert (first.serial_no, second.serial_no) == (1, 2)


@pytest.mark.django_db
def test_referral_needs_a_valid_party_and_other_outcomes_make_none(
    school, nurse_user, student_user
):
    visit = ClinicService.start_visit(school, student_user, nurse_user)
    with pytest.raises(ValueError):
        ClinicService.close_visit(visit, choices.OUTCOME_REFERRAL, "nope")
    visit.refresh_from_db()
    assert visit.closed_at is None and not ClinicReferral.objects.exists()
    ClinicService.close_visit(visit, choices.OUTCOME_RETURN)
    assert not ClinicReferral.objects.exists()


@pytest.mark.django_db
def test_list_separates_open_from_closed(school, nurse_user, student_user):
    ref = _referral(school, nurse_user, student_user)
    c = _client(nurse_user)
    page = c.get(reverse("clinic:referrals"))
    assert page.status_code == 200 and "no-store" in page["Cache-Control"]
    assert [r.pk for r in page.context["open_rows"]] == [ref.pk] and not page.context["closed_rows"]

    done = c.post(reverse("clinic:referral_close", args=[ref.id]), {"result": "treated"})
    assert done.status_code == 302
    page = c.get(reverse("clinic:referrals"))
    assert not page.context["open_rows"] and [r.pk for r in page.context["closed_rows"]] == [ref.pk]
    ref.refresh_from_db()
    assert (
        ref.result_code == "treated" and ref.closed_on is not None and ref.closed_by == nurse_user
    )
    assert (
        c.post(reverse("clinic:referral_close", args=[ref.id]), {"result": "treated"}).status_code
        == 400
    )


@pytest.mark.django_db
def test_close_rejects_a_result_outside_the_list(school, nurse_user, student_user):
    ref = _referral(school, nurse_user, student_user)
    with pytest.raises(ValueError):
        close_referral(ref, "free text", nurse_user)


@pytest.mark.django_db
def test_receipt_masks_the_name_and_carries_no_diagnosis(school, nurse_user, student_user):
    visit = ClinicService.start_visit(school, student_user, nurse_user)
    ClinicVisit.objects.filter(pk=visit.pk).update(
        reason="سرّ صحي لا يظهر", symptoms="أعراض سرّية", treatment="علاج سرّي"
    )
    ClinicService.close_visit(
        ClinicVisit.objects.get(pk=visit.pk), choices.OUTCOME_REFERRAL, "hospital"
    )
    ref = ClinicReferral.objects.get()
    html = (
        _client(nurse_user).get(reverse("clinic:referral_receipt", args=[ref.id])).content.decode()
    )
    assert mask_person_name(student_user.full_name) in html
    assert f">{student_user.full_name}<" not in html
    for secret in ("سرّ صحي", "أعراض سرّية", "علاج سرّي"):
        assert secret not in html
    assert "المستشفى" in html and str(ref.serial_no) in html


@pytest.mark.django_db
def test_only_the_nurse_can_open_list_or_receipt(school, nurse_user, teacher_user, student_user):
    ref = _referral(school, nurse_user, student_user)
    c = _client(teacher_user)
    assert c.get(reverse("clinic:referrals")).status_code in (302, 403)
    assert c.get(reverse("clinic:referral_receipt", args=[ref.id])).status_code in (302, 403)
    assert c.post(
        reverse("clinic:referral_close", args=[ref.id]), {"result": "treated"}
    ).status_code in (302, 403)
    ref.refresh_from_db()
    assert ref.status == choices.REFERRAL_OPEN


@pytest.mark.django_db
def test_every_receipt_open_is_audited(school, nurse_user, student_user):
    ref = _referral(school, nurse_user, student_user)
    c = _client(nurse_user)
    before = AuditLog.objects.filter(action="export", object_id=str(ref.id)).count()
    c.get(reverse("clinic:referral_receipt", args=[ref.id]))
    c.get(reverse("clinic:referral_receipt", args=[ref.id]))
    assert AuditLog.objects.filter(action="export", object_id=str(ref.id)).count() == before + 2


@pytest.mark.django_db
def test_a_referral_of_another_school_is_not_reachable(school, nurse_user, student_user):
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    visit = ClinicVisit.objects.create(school=other, student=student_user, reason="")
    ref = ClinicReferral.objects.create(
        school=other, visit=visit, serial_no=1, follow_up_party="parent"
    )
    c = _client(nurse_user)
    assert c.get(reverse("clinic:referral_receipt", args=[ref.id])).status_code == 404
    assert (
        c.post(reverse("clinic:referral_close", args=[ref.id]), {"result": "treated"}).status_code
        == 404
    )
