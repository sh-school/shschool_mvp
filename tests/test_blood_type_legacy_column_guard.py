"""[W-20260929-011] الإصدار الأول لتقليص العمود القديم blood_type.

الدعاوى:
  ١) لا حقلَ صريحاً `blood_type` في النموذج (الحارس: عودتُه تُفشل).
  ٢) العمودُ باقٍ في القاعدة بافتراضٍ فارغ، فيعمل إدراجُ نموذجٍ قديمٍ بلا ذكره.
  ٣) لا هجرةَ تحذف العمود في هذا الإصدار (الحذفُ طلبٌ منفصلٌ لاحق).
"""

import pathlib
import re

from django.db import connection

from clinic.models import HealthRecord
from core.models import CustomUser

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "clinic" / "migrations"


def test_model_has_no_explicit_blood_type_field():
    names = {f.name for f in HealthRecord._meta.get_fields()}
    assert "blood_type" not in names, "عاد حقلٌ صريحٌ للعمود القديم"
    assert "blood_type_encrypted" in names


def test_legacy_column_stays_with_empty_db_default(db):
    with connection.cursor() as cur:
        desc = connection.introspection.get_table_description(cur, "core_healthrecord")
    cols = {c.name: c for c in desc}
    assert "blood_type" in cols, "العمودُ يبقى في هذا الإصدار"
    assert cols["blood_type"].null_ok is False


def test_old_model_insert_without_the_column_works(db):
    """إدراجُ صفٍّ لا يذكر العمودَ القديم ينجح، وقيمتُه الفارغة من افتراض القاعدة."""
    student = CustomUser.objects.create(
        must_change_password=False, national_id="28800000555", full_name="طالب"
    )
    rec = HealthRecord.objects.create(student=student)
    with connection.cursor() as cur:
        cur.execute("SELECT blood_type FROM core_healthrecord WHERE id = %s", [str(rec.pk)])
        assert cur.fetchone()[0] == ""


def test_no_migration_drops_the_legacy_column():
    pat = re.compile(r"RemoveField\(\s*model_name=.healthrecord.,\s*name=.blood_type.\s*\)", re.S)
    for path in MIGRATIONS.glob("0*.py"):
        text = path.read_text(encoding="utf-8")
        if pat.search(text):
            assert "SeparateDatabaseAndState" in text, f"{path.name}: حذفٌ فعليٌّ للعمود"
