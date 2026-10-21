"""
tests/test_encrypted_fields_covered_by_rotation.py
تدويرُ مفتاح التشفير يعيد تشفير كلّ `EncryptedTextField` في HealthRecord وClinicVisit (W-20261020-024).

كان الأمرُ يسرد خمسةَ حقولٍ من HealthRecord بالاسم فتخطّى أربعةً أُضيفت بعدها (فصيلة الدم واسمُ المركز الصحّي
ورقمُ بطاقته ورقمُ مستشفى حمد)، فتبقى بالمفتاح القديم حين يُسحب. والاختبارُ هنا لا يثق بقائمة الأمر: يكتشف الحقولَ
بنفسه بالانعكاس، ويدوّر تدويراً حقيقيّاً، ثمّ يفكّ كلَّ عمودٍ خامٍّ بالمفتاح الجديد وحدَه — فحقلٌ مشفَّرٌ يُضاف
للنموذج ولا يدخل التدويرَ يُسقطه.
"""

from io import StringIO

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.db import connection
from django.test import override_settings

from clinic.models import ClinicVisit, HealthRecord
from core.fields import EncryptedTextField, encrypted_field_names

pytestmark = pytest.mark.django_db

MODELS = [HealthRecord, ClinicVisit]


def _discovered(model):
    """حقولُ التشفير كما يراها الاختبارُ نفسُه، لا كما يسردها الأمر."""
    return [f for f in model._meta.get_fields() if isinstance(f, EncryptedTextField)]


def _value_for(field):
    """قيمةٌ صالحةٌ للحقل: أوّلُ خيارٍ إن كان له choices، وإلّا نصٌّ مميِّزٌ لاسمه."""
    return field.choices[0][0] if field.choices else f"قيمة-{field.name}"


def _raw(model, pk, column):
    with connection.cursor() as cur:
        cur.execute(
            f'SELECT "{column}" FROM "{model._meta.db_table}" WHERE "{model._meta.pk.column}" = %s',
            [pk],
        )
        return cur.fetchone()[0]


def _make(model, school, student, nurse):
    values = {f.name: _value_for(f) for f in _discovered(model)}
    if model is ClinicVisit:
        return model.objects.create(school=school, student=student, nurse=nurse, **values), values
    return model.objects.create(student=student, **values), values


def test_introspection_finds_the_four_fields_the_old_list_skipped():
    names = set(encrypted_field_names(HealthRecord))
    assert {
        "blood_type_encrypted",
        "health_center_name",
        "health_card_number",
        "hamad_hospital_number",
    } <= names
    assert {"reason", "symptoms", "treatment"} <= set(encrypted_field_names(ClinicVisit))


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_the_helper_agrees_with_independent_discovery(model):
    assert sorted(encrypted_field_names(model)) == sorted(f.name for f in _discovered(model))


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_rotation_reencrypts_every_encrypted_field_under_the_new_key_alone(
    model, school, student_user, nurse_user
):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()

    with override_settings(FERNET_KEY=old, FERNET_OLD_KEYS=""):
        obj, values = _make(model, school, student_user, nurse_user)
        for name in values:
            # الشرطُ المسبق: ما كُتب مشفَّرٌ بالمفتاح القديم فقط (وإلّا فالاختبارُ فارغ).
            Fernet(old).decrypt(_raw(model, obj.pk, name).encode())
            with pytest.raises(Exception):  # noqa: B017, PT011 — InvalidToken من مفتاحٍ لا يطابق
                Fernet(new).decrypt(_raw(model, obj.pk, name).encode())

    with override_settings(FERNET_KEY=new, FERNET_OLD_KEYS=old):
        call_command("rotate_fernet_key", stdout=StringIO(), stderr=StringIO())

    for name, plain in values.items():
        # يُفكّ بالمفتاح الجديد وحدَه — لا بالقديم الذي سيُسحب.
        assert Fernet(new).decrypt(_raw(model, obj.pk, name).encode()).decode() == plain, name

    with override_settings(FERNET_KEY=new, FERNET_OLD_KEYS=""):
        fresh = model.objects.get(pk=obj.pk)
        assert {n: getattr(fresh, n) for n in values} == values
