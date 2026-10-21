"""
tests/test_encrypted_fields_covered_by_rotation.py
تدويرُ مفتاح التشفير يعيد تشفير كلّ `EncryptedTextField` في المشروع كلِّه (W-20261020-024، وعمّمتها W-20261021-003).

كان الأمرُ يسرد خمسةَ حقولٍ من HealthRecord بالاسم فتخطّى أربعةً أُضيفت بعدها (فصيلة الدم واسمُ المركز الصحّي
ورقمُ بطاقته ورقمُ مستشفى حمد)، فتبقى بالمفتاح القديم حين يُسحب. والاختبارُ هنا لا يثق بقائمة الأمر: يكتشف الحقولَ
بنفسه بالانعكاس، ويدوّر تدويراً حقيقيّاً، ثمّ يفكّ كلَّ عمودٍ خامٍّ بالمفتاح الجديد وحدَه — فحقلٌ مشفَّرٌ يُضاف
لأيّ نموذجٍ ولا يدخل التدويرَ يُسقطه — ومنه ما خلا HealthRecord وClinicVisit (behavior وoperations
وCustomUser وProfile وغيرُها)، تُنشأ صفوفُه بلا `save()` ولا قيودِ المفاتيح الأجنبيّة (مؤجَّلةٌ في معاملة الاختبار).
"""

import datetime
import uuid
from decimal import Decimal
from io import StringIO

import pytest
from cryptography.fernet import Fernet
from django.apps import apps
from django.core.management import call_command
from django.db import connection, models
from django.test import override_settings
from django.utils import timezone

from clinic.models import ClinicVisit, HealthRecord
from core.fields import EncryptedTextField, encrypted_field_names

pytestmark = pytest.mark.django_db


def _discovered(model):
    """حقولُ التشفير كما يراها الاختبارُ نفسُه، لا كما يسردها الأمر."""
    return [f for f in model._meta.get_fields() if isinstance(f, EncryptedTextField)]


def _all_encrypted_models():
    """كلُّ نموذجٍ حقيقيٍّ فيه حقلٌ مشفَّر، من سجلّ التطبيقات مباشرةً."""
    return sorted(
        (m for m in apps.get_models() if not m._meta.proxy and _discovered(m)),
        key=lambda m: m._meta.label,
    )


def _value_for(field):
    """قيمةٌ صالحةٌ للحقل: أوّلُ خيارٍ إن كان له choices، وإلّا نصٌّ مميِّزٌ لاسمه."""
    return field.choices[0][0] if field.choices else f"قيمة-{field.name}"


def _filler(field):
    """قيمةٌ مقبولةٌ لعمودٍ غيرِ مشفَّر لازمٍ لإدراج الصفّ (المفاتيحُ الأجنبيّة مؤجَّلةُ الفحص)."""
    if field.has_default():
        return field.get_default()
    if field.null:
        return None
    if field.choices:
        return field.choices[0][0]
    if isinstance(field, models.ForeignKey):
        target = field.target_field
        return uuid.uuid4() if isinstance(target, models.UUIDField) else 1
    if isinstance(field, models.UUIDField):
        return uuid.uuid4()
    if isinstance(field, models.JSONField):
        return {}
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, models.DateTimeField):
        return timezone.now()
    if isinstance(field, models.DateField):
        return datetime.date(2026, 1, 1)
    if isinstance(field, models.TimeField):
        return datetime.time(8, 0)
    if isinstance(field, models.DecimalField):
        return Decimal("1")
    if isinstance(field, models.FloatField):
        return 1.0
    if isinstance(field, models.IntegerField):
        return 1
    if isinstance(field, models.EmailField):
        return "a@b.co"
    return f"x{uuid.uuid4().hex[:8]}"


def _raw(model, pk, column):
    with connection.cursor() as cur:
        cur.execute(
            f'SELECT "{column}" FROM "{model._meta.db_table}" WHERE "{model._meta.pk.column}" = %s',
            [pk],
        )
        return cur.fetchone()[0]


def _make(model):
    """يُدرج صفّاً بكلّ حقوله المشفَّرة مملوءة، بلا `save()` ولا مفاتيحَ أجنبيّةٍ حقيقيّة."""
    values = {f.name: _value_for(f) for f in _discovered(model)}
    kwargs = {}
    for f in model._meta.concrete_fields:
        if f.name in values or f.primary_key and f.auto_created:
            continue
        kwargs[f.attname] = _filler(f)
    obj = model(**kwargs, **values)
    with connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL DEFERRED")
    model._base_manager.bulk_create([obj])
    return obj, values


def _purge(model, pk):
    """يحذف الصفَّ الخامَّ قبل نهاية المعاملة: مفاتيحُه الأجنبيّة وهميّةٌ فيفشل فحصُ القيود عند التفكيك."""
    with connection.cursor() as cur:
        cur.execute(
            f'DELETE FROM "{model._meta.db_table}" WHERE "{model._meta.pk.column}" = %s', [pk]
        )


def test_introspection_finds_the_four_fields_the_old_list_skipped():
    names = set(encrypted_field_names(HealthRecord))
    assert {
        "blood_type_encrypted",
        "health_center_name",
        "health_card_number",
        "hamad_hospital_number",
    } <= names
    assert {"reason", "symptoms", "treatment"} <= set(encrypted_field_names(ClinicVisit))


def test_the_known_models_outside_the_clinic_are_discovered():
    labels = {m._meta.label for m in _all_encrypted_models()}
    assert {
        "behavior.BehaviorInfraction",
        "operations.AbsenceContactLog",
        "core.CustomUser",
        "core.Profile",
    } <= labels


@pytest.mark.parametrize("model", _all_encrypted_models(), ids=lambda m: m._meta.label)
def test_the_helper_agrees_with_independent_discovery(model):
    assert sorted(encrypted_field_names(model)) == sorted(f.name for f in _discovered(model))


def test_the_command_rotates_every_model_that_has_an_encrypted_field():
    """النماذجُ التي يدوّرها الأمرُ + `CustomUser` (مسارُه الخاصّ) = كلُّ ما في المشروع."""
    from core.models import CustomUser
    from governance.management.commands.rotate_fernet_key import Command

    covered = {m._meta.label for m in Command.rotated_models()} | {CustomUser._meta.label}
    assert covered == {m._meta.label for m in _all_encrypted_models()}


@pytest.mark.parametrize("model", _all_encrypted_models(), ids=lambda m: m._meta.label)
def test_rotation_reencrypts_every_encrypted_field_under_the_new_key_alone(model):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    obj = None
    try:
        with override_settings(FERNET_KEY=old, FERNET_OLD_KEYS=""):
            obj, values = _make(model)
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
            fresh = model._base_manager.get(pk=obj.pk)
            assert {n: getattr(fresh, n) for n in values} == values
    finally:
        if obj is not None:
            _purge(model, obj.pk)
