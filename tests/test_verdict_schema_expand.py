"""مرحلةُ التوسيع للحكم الواحد (هجرات assessments 0011–0017) — لا كاتبَ ولا قارئَ بعد.

ما يثبته هذا الملفّ ثلاثة:
1. **نسخةٌ قديمةٌ تكتب**: الأعمدةُ الجديدة في `assessments_annualsubjectresult` لها افتراضٌ
   دائمٌ في القاعدة (`db_default`) — فإدراجٌ لا يذكرها (كشيفرة ما قبل الطلب، أثناء نشرٍ
   متدحرج أو شجرةِ جلسةٍ على القاعدة نفسها) لا يسقط بـ NOT NULL.
2. **التعبئة** (`backfill_standing`) تحفظ ما كانت الشهادةُ تعرضه: راسبٌ إن وُجدت مادّةٌ راسبة،
   وإلّا ناجحٌ إن وُجدت ناجحة، وغيرُ ذلك لا يُمسّ.
3. **إصدارُ القواعد** يبقى 0 (ما قبل الحكم الواحد) حتّى يوصل الحسابُ الجديد.
"""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.db import connection

from assessments.models import (
    AnnualSubjectResult,
    ExamDeprivation,
    ExamMisconduct,
    SubjectClassSetup,
)
from operations.models import Subject
from tests.conftest import ClassGroupFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2025-2026"


def _setup(school, teacher, code):
    cg = ClassGroupFactory(school=school, grade=8)
    subject = Subject.objects.create(school=school, name_ar=f"مادة {code}", code=code)
    return SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher, academic_year=YEAR
    )


def test_an_insert_that_omits_the_new_columns_still_works(school, teacher_user):
    student = UserFactory()
    setup = _setup(school, teacher_user, "S1")
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO assessments_annualsubjectresult "
            "(id, student_id, setup_id, school_id, academic_year, pass_grade, status, updated_at) "
            "VALUES (gen_random_uuid(), %s, %s, %s, %s, 50, 'pass', now())",
            [student.pk, setup.pk, school.pk, YEAR],
        )
    row = AnnualSubjectResult.objects.get(student=student, setup=setup)
    assert (row.standing, row.mark, row.article, row.review) == ("incomplete", "", "", "")
    assert row.second_round_absent is False
    assert row.ruleset == 0
    assert row.second_round_score is None and row.second_round_max is None


def test_orm_default_ruleset_is_the_legacy_one(school, teacher_user):
    student = UserFactory()
    row = AnnualSubjectResult.objects.create(
        student=student,
        setup=_setup(school, teacher_user, "S2"),
        school=school,
        academic_year=YEAR,
        annual_total=Decimal("70"),
        status="pass",
    )
    assert row.ruleset == 0


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["pass", "pass"], "passed"),
        (["pass", "fail"], "failed"),
        (["pass", "second_round"], "second_round"),
        (["fail", "second_round"], "failed"),
        (["incomplete"], "incomplete"),  # لا يُمسّ
    ],
)
def test_backfill_standing_keeps_what_the_certificate_showed(
    school, teacher_user, statuses, expected
):
    student = UserFactory()
    for i, status in enumerate(statuses):
        AnnualSubjectResult.objects.create(
            student=student,
            setup=_setup(school, teacher_user, f"B{i}"),
            school=school,
            academic_year=YEAR,
            status=status,
        )
    migration = importlib.import_module("assessments.migrations.0011_verdict_standing_deprivation")
    migration.backfill_standing(django_apps, None)
    standings = set(
        AnnualSubjectResult.objects.filter(student=student).values_list("standing", flat=True)
    )
    assert standings == {expected}


def test_the_new_tables_exist_and_are_school_scoped(school):
    for model in (ExamDeprivation, ExamMisconduct):
        assert model._meta.get_field("school").remote_field.model.__name__ == "School"
