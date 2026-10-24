"""[W-20261020-036] عزلُ جداول الأدوية الثلاثة بين المدارس (RLS) بنمط `test_period_preference_rls`.

الهويّةُ من دور الاتصال (`app_rls_school()`)، فكلُّ قراءةٍ أو تعديلٍ أو حذفٍ أو إدراجٍ
يمرّ بدورٍ مقيَّدٍ يمثّل مدرسةً واحدة.
"""

import datetime as dt
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from clinic.models import (
    ClinicVisit,
    GuardianMedicationConsent,
    MedicationCatalogItem,
    VisitMedication,
)
from tests.conftest import SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

PROBE_ROLE = "w036_medication_probe"
TABLES = {
    "catalog": "clinic_medicationcatalogitem",
    "consent": "clinic_guardianmedicationconsent",
    "dispensing": "clinic_visitmedication",
}


@contextmanager
def _as_tenant(school_id, table):
    if connection.vendor != "postgresql":
        pytest.skip("عقدُ RLS خاصٌّ بـPostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            DO $$
            BEGIN
                CREATE ROLE {PROBE_ROLE} NOSUPERUSER NOBYPASSRLS NOINHERIT;
            EXCEPTION WHEN duplicate_object THEN
                NULL;
            END $$;
            """
        )
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {PROBE_ROLE}")
        cursor.execute(f"GRANT SELECT ON public.app_rls_role_school TO {PROBE_ROLE}")
        cursor.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {PROBE_ROLE}")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO {PROBE_ROLE}")
        cursor.execute(
            """
            INSERT INTO public.app_rls_role_school (db_role, school_id)
            VALUES (session_user, %s)
            ON CONFLICT (db_role) DO UPDATE SET school_id = EXCLUDED.school_id
            """,
            [str(school_id)],
        )
        cursor.execute(f"GRANT {PROBE_ROLE} TO CURRENT_USER")
        cursor.execute(f"SET ROLE {PROBE_ROLE}")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


def _catalog(school):
    return MedicationCatalogItem.objects.create(
        school=school, name="دواءٌ تجريبيّ", standard_dose="500 ملغ"
    )


def _consent(school, item):
    now = timezone.now()
    return GuardianMedicationConsent.objects.create(
        school=school,
        student=UserFactory(),
        catalog_item=item,
        granted_at=now - dt.timedelta(days=1),
        expires_at=now + dt.timedelta(days=30),
    )


def _dispensing(school, item):
    visit = ClinicVisit.objects.create(
        school=school, student=UserFactory(), nurse=UserFactory(), reason="صداع"
    )
    return VisitMedication.objects.create(
        school=school,
        visit=visit,
        catalog_item=item,
        dose="500 ملغ",
        consent=_consent(school, item),
        dispensed_by=UserFactory(),
        dispensed_at=timezone.now(),
    )


def _row(kind, school):
    """صفٌّ في مدرسة `school` من الجدول المطلوب."""
    item = _catalog(school)
    if kind == "catalog":
        return item
    if kind == "consent":
        return _consent(school, item)
    return _dispensing(school, item)


def _model(kind):
    return {"catalog": MedicationCatalogItem, "consent": GuardianMedicationConsent}.get(
        kind, VisitMedication
    )


@pytest.mark.parametrize("kind", TABLES)
def test_a_school_sees_only_its_own_rows(kind):
    a, b = SchoolFactory(), SchoolFactory()
    _row(kind, a)
    mine = _row(kind, b)
    model = _model(kind)
    with _as_tenant(b.pk, TABLES[kind]):
        seen = set(model.objects.values_list("pk", flat=True))
    assert seen == {mine.pk}


@pytest.mark.parametrize("kind", TABLES)
def test_a_school_cannot_update_another_schools_row(kind):
    a, b = SchoolFactory(), SchoolFactory()
    foreign = _row(kind, a)
    model = _model(kind)
    change = {
        "catalog": {"name": "مُعدَّل"},
        "consent": {"revoked_at": timezone.now()},
        "dispensing": {"dose": "مُعدَّل"},
    }[kind]
    with _as_tenant(b.pk, TABLES[kind]):
        updated = model.objects.filter(pk=foreign.pk).update(**change)
    assert updated == 0


@pytest.mark.parametrize("kind", TABLES)
def test_a_school_cannot_delete_another_schools_row(kind):
    a, b = SchoolFactory(), SchoolFactory()
    foreign = _row(kind, a)
    model = _model(kind)
    with _as_tenant(b.pk, TABLES[kind]):
        deleted, _ = model.objects.filter(pk=foreign.pk).delete()
    assert deleted == 0
    assert model.objects.filter(pk=foreign.pk).exists()


@pytest.mark.parametrize("kind", TABLES)
def test_writing_a_row_for_another_school_is_refused_by_with_check(kind):
    a, b = SchoolFactory(), SchoolFactory()
    # الصفوفُ المرجعيّةُ والمستخدمون يُنشأون قبل دخول دور المستأجر، فلا تُعيقهم السياسة ولا الصلاحيات.
    item_a = _catalog(a)
    consent_a = _consent(a, item_a) if kind == "dispensing" else None
    student, nurse, dispenser = UserFactory(), UserFactory(), UserFactory()
    visit = (
        ClinicVisit.objects.create(school=a, student=student, nurse=nurse, reason="صداع")
        if kind == "dispensing"
        else None
    )
    with _as_tenant(b.pk, TABLES[kind]):
        # الرفضُ يجب أن يكون من سياسة RLS تحديداً، لا من صلاحيّةٍ أو مفتاحٍ أجنبيّ.
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            if kind == "catalog":
                MedicationCatalogItem.objects.create(school=a, name="مرفوض", standard_dose="1 ملغ")
            elif kind == "consent":
                GuardianMedicationConsent.objects.create(
                    school=a,
                    student=student,
                    catalog_item=item_a,
                    granted_at=timezone.now() - dt.timedelta(days=1),
                    expires_at=timezone.now() + dt.timedelta(days=30),
                )
            else:
                VisitMedication.objects.create(
                    school=a,
                    visit=visit,
                    catalog_item=item_a,
                    dose="500 ملغ",
                    consent=consent_a,
                    dispensed_by=dispenser,
                    dispensed_at=timezone.now(),
                )


@pytest.mark.parametrize("kind", TABLES)
def test_the_table_has_the_canonical_policy(kind):
    table = TABLES[kind]
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT relrowsecurity FROM pg_class WHERE oid = 'public.{table}'::regclass"
        )
        assert cursor.fetchone()[0] is True
        cursor.execute("SELECT policyname FROM pg_policies WHERE tablename = %s", [table])
        assert [row[0] for row in cursor.fetchall()] == ["school_isolation"]
