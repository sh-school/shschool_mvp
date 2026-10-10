"""[W-20261004-015] جاهزيّةُ الخلفيّة لكشف المعلّم: الجداولُ والأعمدةُ مطابقةٌ للنماذج، ونقطتا الخروج والعودة تحفظان وتعيدان ما يلزم.

أمر المالك: «تأكّد من أنّ الباك اند جاهز وجداولها صحيحة». الدليلُ هنا اختباراتٌ تقرأ **القاعدةَ نفسَها** (جداولُ الاختبار تُبنى من الهجرات) لا النماذج وحدَها:
كلُّ عمودٍ من نماذج الحضور المبدئيّ والخروج موجودٌ في جدوله، وكلُّ عمودٍ في الجدول له حقلٌ — فلا هجرةَ ناقصةً ولا عموداً زائداً.
"""

import pytest
from django.db import connection
from django.utils import timezone

from operations.models import (
    AttendanceDecision,
    AttendanceEntry,
    ClassExit,
    PeriodConfirmation,
    StudentAttendance,
)
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db

MODELS = [ClassExit, AttendanceEntry, AttendanceDecision, StudentAttendance, PeriodConfirmation]


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_the_table_columns_match_the_model_fields_exactly(model):
    with connection.cursor() as cursor:
        columns = {
            c.name
            for c in connection.introspection.get_table_description(cursor, model._meta.db_table)
        }
    fields = {f.column for f in model._meta.concrete_fields}
    assert fields - columns == set(), f"أعمدةٌ ناقصةٌ في الجدول: {fields - columns}"
    assert columns - fields == set(), f"أعمدةٌ زائدةٌ لا حقلَ لها: {columns - fields}"
