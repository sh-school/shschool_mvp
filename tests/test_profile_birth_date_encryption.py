"""[W-20261001-016] تاريخُ ميلاد الطالب القاصر مشفَّرٌ at-rest (PDPPL م.16).

مرحلةُ «التوسيع» من توسيعٍ ثمّ تقليص: عمودٌ مشفَّرٌ جديدٌ يُكتب مع القديم
(كتابةٌ مزدوجة، فتبقى النسخةُ القديمةُ من الكود صالحةً أثناء النشر)، والقراءةُ
تتحوّل إلى `Profile.date_of_birth`. حذفُ `birth_date` الصريح إصدارٌ لاحق.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.db import connection

from core.models import Profile

from .conftest import UserFactory

DOB = date(2011, 5, 17)


def _raw(profile, column):
    with connection.cursor() as cur:
        cur.execute(f"SELECT {column} FROM core_profile WHERE id = %s", [profile.pk])
        return cur.fetchone()[0]


@pytest.mark.django_db
class TestBirthDateEncrypted:
    def test_stored_value_is_not_a_plain_date(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)

        raw = _raw(profile, "birth_date_encrypted")

        assert raw, "العمودُ المشفَّر فارغ"
        assert "2011" not in raw and "05-17" not in raw, "القيمةُ في القاعدة تاريخٌ صريح"

    def test_reads_back_as_a_date(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)

        assert Profile.objects.get(pk=profile.pk).date_of_birth == DOB

    def test_update_fields_save_keeps_both_columns_in_step(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        profile.birth_date = date(2012, 1, 2)
        profile.save(update_fields=["birth_date"])  # كما يفعل ministry_import

        assert Profile.objects.get(pk=profile.pk).date_of_birth == date(2012, 1, 2)

    def test_clearing_clears_the_encrypted_column(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        profile.birth_date = None
        profile.save()

        assert _raw(profile, "birth_date_encrypted") in ("", None)
        assert Profile.objects.get(pk=profile.pk).date_of_birth is None

    def test_legacy_row_without_encrypted_value_still_reads(self):
        """صفٌّ سبق الهجرة: القراءةُ تسقط إلى القديم حتى يُملأ بالأمر."""
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="")

        assert Profile.objects.get(pk=profile.pk).date_of_birth == DOB

    def test_backfill_command_fills_legacy_rows_and_is_idempotent(self):
        profile = Profile.objects.create(user=UserFactory(), birth_date=DOB)
        Profile.objects.filter(pk=profile.pk).update(birth_date_encrypted="")

        call_command("backfill_birth_date_encrypted")
        first = _raw(profile, "birth_date_encrypted")
        call_command("backfill_birth_date_encrypted")

        assert first and "2011" not in first
        assert Profile.objects.get(pk=profile.pk).date_of_birth == DOB
        assert _raw(profile, "birth_date_encrypted") == first, "الأمرُ أعاد كتابة صفٍّ مملوء"
