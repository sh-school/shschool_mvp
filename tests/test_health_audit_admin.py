"""
tests/test_health_audit_admin.py — فتحُ البيان الصحّيّ من لوحة الإدارة يترك سطرَ تدقيق (CLN-03).

سطرٌ لكلّ نوع صفحة بمعرّفاتٍ وأعدادٍ فقط، ولا سطرَ لقائمةٍ فارغة ولا لمن رُفض وصولُه. وكلُّ نموذجٍ
يُسجَّل من تطبيق clinic يلزمه تصنيف.
"""

import json
from datetime import date, timedelta

import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

from clinic.health_access import HealthAuditAdminMixin
from clinic.models import GuardianMedicationConsent, MedicationCatalogItem, VisitMedication
from core.models import AuditLog
from operations.models import ExitPermit, TeacherAbsence
from tests.conftest import (
    ClassGroupFactory,
    ClinicVisitFactory,
    HealthRecordFactory,
    SchoolFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

#: نماذجُ clinic المسجَّلةُ التي لا تعرض بياناً صحّيّاً فرديّاً: الاسمُ ← السبب.
NON_HEALTH_MODELS = {"MedicationCatalogItem": "كتالوجُ أدويةٍ بلا طالب"}

SECRET = "نصٌّ صحّيٌّ سرّيّ"
STUDENT_NAME = "طالبٌ اصطناعيّ للتدقيق"


@pytest.fixture
def root(client, developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    client.force_login(developer_user)
    return developer_user


@pytest.fixture
def student():
    return UserFactory(full_name=STUDENT_NAME, national_id="29000000001")


def _url(model, page, *args):
    return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_{page}", args=args)


def _lines(model_name):
    return list(AuditLog.objects.filter(action="view", model_name=model_name))


def _assert_clean(lines):
    for line in lines:
        text = json.dumps(line.changes, ensure_ascii=False) + line.object_repr
        for forbidden in (SECRET, STUDENT_NAME, "29000000001"):
            assert forbidden not in text


def _make(model_name, student):
    school = SchoolFactory()
    if model_name == "HealthRecord":
        return HealthRecordFactory(student=student, allergies=SECRET)
    if model_name == "ClinicVisit":
        return ClinicVisitFactory(school=school, student=student, reason=SECRET)
    item = MedicationCatalogItem.objects.create(school=school, name="دواء", standard_dose="1")
    now = timezone.now()
    consent = GuardianMedicationConsent.objects.create(
        school=school,
        student=student,
        catalog_item=item,
        granted_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=30),
    )
    if model_name == "GuardianMedicationConsent":
        return consent
    visit = ClinicVisitFactory(school=school, student=student, reason=SECRET)
    return VisitMedication.objects.create(
        school=school,
        visit=visit,
        catalog_item=item,
        consent=consent,
        dose="1",
        dispensed_at=now,
    )


@pytest.mark.parametrize(
    "model_name",
    ["HealthRecord", "ClinicVisit", "GuardianMedicationConsent", "VisitMedication"],
)
def test_every_clinic_admin_page_is_audited(client, root, student, model_name):
    obj = _make(model_name, student)
    model = type(obj)
    pages = [
        ("القائمة", _url(model, "changelist") + "?q=29000000001", ""),
        ("صفحة السجل", _url(model, "change", obj.pk), str(obj.pk)),
        ("تاريخ السجل", _url(model, "history", obj.pk), str(obj.pk)),
    ]
    if model is not VisitMedication:  # سجلُّ الصرف لا يُحذف من اللوحة
        pages.append(("تأكيد الحذف", _url(model, "delete", obj.pk), str(obj.pk)))
    if model is VisitMedication:
        pages[0] = ("القائمة", _url(model, "changelist"), "")
    for screen, url, object_id in pages:
        before = {line.pk for line in _lines(model_name)}
        assert client.get(url).status_code == 200
        new = [line for line in _lines(model_name) if line.pk not in before]
        assert len(new) == 1, screen
        assert new[0].changes == {"screen": f"لوحة الإدارة: {screen}", "rows": 1}
        assert new[0].object_id == object_id
        assert new[0].user == root
        _assert_clean(new)


def test_delete_selected_confirmation_is_audited(client, root, student):
    record = _make("HealthRecord", student)
    response = client.post(
        _url(type(record), "changelist"),
        {"action": "delete_selected", "_selected_action": [str(record.pk)], "index": 0},
    )
    assert response.status_code == 200
    lines = _lines("HealthRecord")
    assert [line.changes for line in lines] == [{"screen": "لوحة الإدارة: إجراء جماعي", "rows": 1}]
    _assert_clean(lines)


def test_empty_list_and_refused_access_write_nothing(client, root, student):
    record = _make("HealthRecord", student)
    model = type(record)
    assert client.get(_url(model, "changelist") + "?q=zzzz").status_code == 200
    client.force_login(UserFactory(is_staff=True))
    for page, args in (("changelist", ()), ("change", (record.pk,)), ("history", (record.pk,))):
        assert client.get(_url(model, page, *args)).status_code in (302, 403)
    assert not _lines("HealthRecord")


def test_exit_permit_audited_only_for_medical_reason(client, root, student):
    group = ClassGroupFactory()
    permits = [
        ExitPermit.objects.create(
            school=group.school,
            student=student,
            class_group=group,
            sequence=number,
            reason=reason,
        )
        for number, reason in enumerate(("family", "medical"), start=1)
    ]
    assert client.get(_url(ExitPermit, "change", permits[0].pk)).status_code == 200
    assert not _lines("ExitPermit")
    assert client.get(_url(ExitPermit, "changelist")).status_code == 200
    assert [line.changes["rows"] for line in _lines("ExitPermit")] == [1]
    _assert_clean(_lines("ExitPermit"))


def test_sick_absence_audited_on_list_and_autocomplete(client, root):
    school = SchoolFactory()
    TeacherAbsence.objects.create(
        school=school, teacher=UserFactory(), date=date(2026, 1, 5), reason="sick"
    )
    assert client.get(_url(TeacherAbsence, "changelist")).status_code == 200
    response = client.get(
        reverse("admin:autocomplete"),
        {
            "app_label": "operations",
            "model_name": "substituteassignment",
            "field_name": "absence",
        },
    )
    assert response.status_code == 200
    assert sorted(line.changes["screen"] for line in _lines("TeacherAbsence")) == [
        "لوحة الإدارة: إكمال تلقائي",
        "لوحة الإدارة: القائمة",
    ]


def test_every_registered_clinic_model_has_an_audit_class():
    registered = {
        model.__name__: model_admin
        for model, model_admin in admin.site._registry.items()
        if model._meta.app_label == "clinic"
    }
    unclassified = [
        name
        for name, model_admin in registered.items()
        if not isinstance(model_admin, HealthAuditAdminMixin) and name not in NON_HEALTH_MODELS
    ]
    assert not unclassified, f"نماذجُ clinic بلا تصنيف تدقيق: {unclassified}"
    assert set(NON_HEALTH_MODELS) <= set(registered)
