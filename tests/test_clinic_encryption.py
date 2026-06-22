"""
tests/test_clinic_encryption.py
تشفير بيانات زيارة العيادة at-rest (reason/symptoms/treatment) — م.8 PDPPL.
"""

import pytest
from django.db import connection

from clinic.models import ClinicVisit


@pytest.mark.django_db
def test_clinic_visit_encrypted_at_rest(school, teacher_user, nurse_user):
    visit = ClinicVisit.objects.create(
        school=school,
        student=teacher_user,
        nurse=nurse_user,
        reason="صداع شديد",
        symptoms="حرارة 39 ووهن",
        treatment="مسكن ألم وراحة",
    )
    # القراءة عبر ORM تُعيد نصّاً صريحاً (فكّ شفّاف)
    visit.refresh_from_db()
    assert visit.reason == "صداع شديد"
    assert visit.symptoms == "حرارة 39 ووهن"
    assert visit.treatment == "مسكن ألم وراحة"

    # القيمة الخام في القاعدة مشفّرة (Fernet token) لا نصّاً صريحاً
    with connection.cursor() as cur:
        cur.execute(
            "SELECT reason, symptoms, treatment FROM core_clinicvisit WHERE id = %s",
            [str(visit.id)],
        )
        raw_reason, raw_symptoms, raw_treatment = cur.fetchone()
    assert raw_reason != "صداع شديد"
    assert raw_reason.startswith("gAAAA")  # بادئة رمز Fernet
    assert raw_symptoms.startswith("gAAAA")
    assert raw_treatment.startswith("gAAAA")


@pytest.mark.django_db
def test_clinic_visit_blank_optional_fields(school, teacher_user, nurse_user):
    visit = ClinicVisit.objects.create(
        school=school, student=teacher_user, nurse=nurse_user, reason="إصابة طفيفة"
    )
    visit.refresh_from_db()
    assert visit.reason == "إصابة طفيفة"
    # الحقول الاختيارية الفارغة تبقى فارغة (لا تُشفَّر)
    assert visit.symptoms == ""
    assert visit.treatment == ""
