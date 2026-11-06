"""[QUALITY] نصّ معيار خطة الدرس يتبع نموذج التوجيه التربوي (W-20261106-012).

الهجرة 0025 تُحدِّث الصفوف القائمة في مكانها (لا صفّ جديد)، ولها عكس، و seed بعدها يُبقي 23 معياراً.
"""

import importlib

import pytest
from django.apps import apps
from django.core.management import call_command

from quality.management.commands.seed_observation_criteria import CRITERIA
from quality.observation_models import ObservationCriterion

OLD_TEXT = "خطة الدرس متوفرة وبنودها مستكملة ومناسبة ومعلنة على نظام قطر للتعليم."
NEW_TEXT = "خطة الدرس متوفرة وبنودها مستكملة ومناسبة ومعلنة على منصّة التعلّم الإلكتروني."

migration = importlib.import_module("quality.migrations.0025_moe_plan_criterion_text")


def _set_old_text(school):
    """يعيد صفّ خطة الدرس إلى النصّ القديم كما كان في قاعدة ما قبل الهجرة."""
    ObservationCriterion.objects.filter(school=school, text=NEW_TEXT).update(text=OLD_TEXT)


def test_constants_match_seed_and_migration():
    """النصّ الجديد في الزرع هو نفسه في الهجرة، والمعيار الأوّل هو خطة الدرس."""
    assert CRITERIA[0] == ("planning", NEW_TEXT)
    assert migration.NEW_TEXT == NEW_TEXT
    assert migration.OLD_TEXT == OLD_TEXT


@pytest.mark.django_db
def test_migration_updates_existing_row_in_place(school):
    """الصفّ القديم يتحوّل إلى الجديد بالمفتاح نفسه، ولا يزيد عدد المعايير ولا تتغيّر درجاته."""
    call_command("seed_observation_criteria", school=school.code)
    _set_old_text(school)
    row = ObservationCriterion.objects.get(school=school, domain="planning", order=1)
    total_before = ObservationCriterion.objects.filter(school=school).count()

    migration.forward(apps, None)

    row.refresh_from_db()
    assert row.text == NEW_TEXT
    assert row.order == 1
    assert ObservationCriterion.objects.filter(school=school).count() == total_before
    assert not ObservationCriterion.objects.filter(school=school, text=OLD_TEXT).exists()


@pytest.mark.django_db
def test_migration_reverse_restores_old_text(school):
    """العكس يعيد النصّ القديم في الصفّ نفسه بلا صفّ إضافي."""
    call_command("seed_observation_criteria", school=school.code)
    total_before = ObservationCriterion.objects.filter(school=school).count()
    pk = ObservationCriterion.objects.get(school=school, text=NEW_TEXT).pk

    migration.backward(apps, None)

    assert ObservationCriterion.objects.get(pk=pk).text == OLD_TEXT
    assert ObservationCriterion.objects.filter(school=school).count() == total_before


@pytest.mark.django_db
def test_reseed_after_migration_keeps_23_criteria(school):
    """بعد الهجرة، إعادة الزرع لا تنشئ معياراً رابعاً وعشرين."""
    call_command("seed_observation_criteria", school=school.code)
    _set_old_text(school)
    migration.forward(apps, None)

    call_command("seed_observation_criteria", school=school.code)

    assert ObservationCriterion.objects.filter(school=school).count() == 23
    assert ObservationCriterion.objects.filter(school=school, text=NEW_TEXT).count() == 1
