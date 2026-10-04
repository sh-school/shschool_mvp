"""[W-20261004-015] جاهزيّةُ الخلفيّة لكشف المعلّم: الجداولُ والأعمدةُ مطابقةٌ للنماذج، ونقطتا الخروج والعودة تحفظان وتعيدان ما يلزم.

أمر المالك: «تأكّد من أنّ الباك اند جاهز وجداولها صحيحة». الدليلُ هنا اختباراتٌ تقرأ **القاعدةَ نفسَها** (جداولُ الاختبار تُبنى من الهجرات) لا النماذج وحدَها:
كلُّ عمودٍ من نماذج الحضور المبدئيّ والخروج موجودٌ في جدوله، وكلُّ عمودٍ في الجدول له حقلٌ — فلا هجرةَ ناقصةً ولا عموداً زائداً.
"""

import pytest
from django.db import connection
from django.urls import reverse
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


def test_the_exit_endpoint_saves_the_moment_and_the_return_closes_it(
    client_as, now_0730, session, teacher, kid
):
    out = client_as(teacher).post(
        reverse("mark_exit", args=[session.id]),
        {"student_id": str(kid.id), "destination": "clinic"},
    )
    assert out.status_code == 200
    exit_ = ClassExit.objects.get(session=session, student=kid)
    assert (exit_.destination, exit_.returned_at, exit_.left_at) == ("clinic", None, at(7, 30))

    back = client_as(teacher).post(
        reverse("mark_return", args=[session.id]), {"student_id": str(kid.id)}
    )
    assert back.status_code == 200
    exit_.refresh_from_db()
    assert exit_.returned_at == at(7, 30)


def test_a_second_exit_press_does_not_duplicate_the_open_exit(
    client_as, now_0730, session, teacher, kid
):
    for _ in range(2):
        client_as(teacher).post(
            reverse("mark_exit", args=[session.id]),
            {"student_id": str(kid.id), "destination": "restroom"},
        )
    assert ClassExit.objects.filter(session=session, student=kid).count() == 1


def test_returning_a_student_who_is_not_out_is_harmless(client_as, now_0730, session, teacher, kid):
    response = client_as(teacher).post(
        reverse("mark_return", args=[session.id]), {"student_id": str(kid.id)}
    )
    assert response.status_code == 200
    assert not ClassExit.objects.exists()


def test_another_teacher_cannot_record_an_exit_in_a_colleagues_session(
    client_as, now_0730, session, other_teacher, kid
):
    response = client_as(other_teacher).post(
        reverse("mark_exit", args=[session.id]),
        {"student_id": str(kid.id), "destination": "clinic"},
    )
    assert response.status_code == 403
    assert not ClassExit.objects.exists()
