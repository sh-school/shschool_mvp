"""
tests/test_clinic_medication_dispensing.py — صرف الدواء من كتالوجٍ معتمَدٍ وبموافقة وليّ أمر (W-20261020-036)

لا صرفَ خارج الكتالوج، ولا بلا موافقةٍ سارية (غائبةً أو منتهيةً أو مسحوبة)، ولا نصَّ حرّاً في المسار،
وكلُّ صرفٍ في التدقيق بمعرّفاتٍ فقط، وهجرةُ توسيعٍ فقط.
"""

import datetime as dt
import pathlib
import re

import pytest
from django.utils import timezone

from clinic.forms import MedicationDispenseForm
from clinic.medication_services import (
    CONSENT_ABSENT,
    CONSENT_APPROVED,
    CONSENT_EXPIRED,
    MedicationNotAllowed,
    MedicationService,
)
from clinic.models import (
    ClinicVisit,
    GuardianMedicationConsent,
    MedicationCatalogItem,
    VisitMedication,
)
from core.models import AuditLog
from tests.conftest import SchoolFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOSE = "500 ملغ"


@pytest.fixture
def item(school, nurse_user):
    return MedicationCatalogItem.objects.create(
        school=school,
        name="دواءٌ تجريبيّ",
        standard_dose=DOSE,
        approved_by=nurse_user,
        approved_at=timezone.now(),
    )


@pytest.fixture
def visit(school, student_user, nurse_user):
    return ClinicVisit.objects.create(
        school=school, student=student_user, nurse=nurse_user, reason="صداع"
    )


def _consent(school, student, item, *, start=-1, days=30, **kw):
    now = timezone.now()
    return GuardianMedicationConsent.objects.create(
        school=school,
        student=student,
        catalog_item=item,
        granted_at=now + dt.timedelta(days=start),
        expires_at=now + dt.timedelta(days=days),
        **kw,
    )


# ── الكتالوج ─────────────────────────────────────────────────────────


def test_an_item_without_clinical_approval_is_not_dispensable(school):
    pending = MedicationCatalogItem.objects.create(school=school, name="ب", standard_dose="1")
    assert pending.is_dispensable is False


def test_an_approved_but_inactive_item_is_not_dispensable(item):
    item.is_active = False
    assert item.is_dispensable is False


def test_the_dispense_form_offers_only_active_approved_items_of_the_school(
    school, item, nurse_user
):
    MedicationCatalogItem.objects.create(school=school, name="لم يُعتمد", standard_dose="1")
    MedicationCatalogItem.objects.create(
        school=school, name="موقوف", standard_dose="1", approved_at=timezone.now(), is_active=False
    )
    form = MedicationDispenseForm(school=school)
    assert list(form.fields["catalog_item"].queryset) == [item]


def test_the_dispense_form_has_no_free_text_field(school):
    form = MedicationDispenseForm(school=school)
    assert list(form.fields) == ["catalog_item"]


# ── حالة الموافقة ────────────────────────────────────────────────────


def test_a_valid_consent_is_approved(school, student_user, item):
    consent = _consent(school, student_user, item)
    assert MedicationService.consent_status(student_user, item) == (CONSENT_APPROVED, consent)


def test_an_expired_consent_is_expired(school, student_user, item):
    _consent(school, student_user, item, start=-30, days=-1)
    assert MedicationService.consent_status(student_user, item) == (CONSENT_EXPIRED, None)


def test_no_consent_is_absent(student_user, item):
    assert MedicationService.consent_status(student_user, item) == (CONSENT_ABSENT, None)


def test_a_revoked_consent_does_not_count_so_it_is_absent(school, student_user, item):
    _consent(school, student_user, item, revoked_at=timezone.now())
    assert MedicationService.consent_status(student_user, item) == (CONSENT_ABSENT, None)


def test_a_consent_for_another_item_does_not_cover_this_one(school, student_user, item):
    other = MedicationCatalogItem.objects.create(
        school=school, name="آخر", standard_dose="1", approved_at=timezone.now()
    )
    _consent(school, student_user, other)
    assert MedicationService.consent_status(student_user, item)[0] == CONSENT_ABSENT


def test_the_latest_valid_consent_wins_over_an_older_expired_one(school, student_user, item):
    _consent(school, student_user, item, start=-60, days=-30)
    fresh = _consent(school, student_user, item)
    assert MedicationService.consent_status(student_user, item) == (CONSENT_APPROVED, fresh)


# ── الصرف ────────────────────────────────────────────────────────────


def test_dispensing_with_a_valid_consent_records_the_catalog_dose(
    school, student_user, nurse_user, item, visit
):
    consent = _consent(school, student_user, item)
    record = MedicationService.dispense(visit, item, nurse_user)

    assert record.dose == DOSE
    assert record.consent == consent and record.visit == visit and record.catalog_item == item
    assert record.dispensed_by == nurse_user
    assert visit.medications.count() == 1


def test_the_dispensed_dose_is_a_snapshot_not_a_live_link(
    school, student_user, nurse_user, item, visit
):
    _consent(school, student_user, item)
    record = MedicationService.dispense(visit, item, nurse_user)
    item.standard_dose = "1000 ملغ"
    item.save()
    record.refresh_from_db()
    assert record.dose == DOSE


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"start": -30, "days": -1}, "consent_expired"),
        ({"revoked_at": "now"}, "consent_absent"),
    ],
)
def test_an_expired_or_revoked_consent_blocks_dispensing(
    school, student_user, nurse_user, item, visit, kwargs, code
):
    if kwargs.get("revoked_at") == "now":
        kwargs = {"revoked_at": timezone.now()}
    _consent(school, student_user, item, **kwargs)
    with pytest.raises(MedicationNotAllowed) as exc:
        MedicationService.dispense(visit, item, nurse_user)
    assert exc.value.code == code
    assert not VisitMedication.objects.exists()


def test_a_missing_consent_blocks_dispensing(nurse_user, item, visit):
    with pytest.raises(MedicationNotAllowed) as exc:
        MedicationService.dispense(visit, item, nurse_user)
    assert exc.value.code == "consent_absent"
    assert not VisitMedication.objects.exists()


def test_an_unapproved_item_blocks_dispensing_even_with_consent(
    school, student_user, nurse_user, visit
):
    pending = MedicationCatalogItem.objects.create(school=school, name="ج", standard_dose="1")
    _consent(school, student_user, pending)
    with pytest.raises(MedicationNotAllowed) as exc:
        MedicationService.dispense(visit, pending, nurse_user)
    assert exc.value.code == "not_approved"


def test_an_item_of_another_school_blocks_dispensing(school, student_user, nurse_user, visit):
    other_school = SchoolFactory()
    foreign = MedicationCatalogItem.objects.create(
        school=other_school, name="غريب", standard_dose="1", approved_at=timezone.now()
    )
    _consent(school, student_user, foreign)
    with pytest.raises(MedicationNotAllowed) as exc:
        MedicationService.dispense(visit, foreign, nurse_user)
    assert exc.value.code == "foreign_item"


def test_the_service_takes_a_catalog_item_not_free_text(nurse_user, visit):
    with pytest.raises(AttributeError):
        MedicationService.dispense(visit, "باراسيتامول", nurse_user)


# ── التدقيق ──────────────────────────────────────────────────────────


def test_every_dispensing_is_audited_with_ids_only(school, student_user, nurse_user, item, visit):
    _consent(school, student_user, item)
    record = MedicationService.dispense(visit, item, nurse_user)

    log = AuditLog.objects.get(model_name="VisitMedication", object_id=str(record.pk))
    dump = f"{log.object_repr} {log.changes}"
    assert log.action == "create" and log.user == nurse_user
    assert str(item.pk) in dump and str(visit.pk) in dump
    # بلا اسم دواءٍ ولا جرعةٍ ولا اسم طالب ولا نصٍّ صحّيّ.
    for forbidden in (item.name, DOSE, student_user.full_name, "صداع"):
        assert forbidden not in dump


# ── الهجرة: توسيعٌ فقط ──────────────────────────────────────────────


def test_the_migration_only_creates():
    source = (ROOT / "clinic/migrations/0017_medication_catalog_consent_dispensing.py").read_text(
        encoding="utf-8"
    )
    assert not re.search(r"RemoveField|DeleteModel|RenameField|RenameModel|AlterField", source)
    assert source.count("CreateModel") == 3
