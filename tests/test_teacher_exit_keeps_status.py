"""[W-20261004-015] خروجُ الطالب بإذن المعلّم **ليس غياباً** في كشف المعلّم — ملاحظةُ المالك على المعاينة: «الطالب عند اختيار خروج يعتمد غائب؟».

في كشف المشرف (`record_period`) اختيارُ وجهةٍ يجعل الطالبَ غائباً بوجهته. وللمعلّم الخروجُ سطرُ `ClassExit` يُسجَّل **فوراً بلحظته** (`mark_exit`/`mark_return`)
ويبقى حالُ الطالب كما هو؛ والمشرفُ يرى «غائباً بإذن المعلّم» مشتقّاً من الخروج في كشفه لا من اختيار المعلّم.
"""

from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.models import AttendanceEntry, ClassExit
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db

JS = Path(__file__).resolve().parent.parent / "static" / "js" / "period-register.js"


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


def test_the_teacher_form_carries_the_exit_and_return_endpoints(
    client_as, now_0730, session, teacher, kid
):
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert f'data-exit-url="{reverse("mark_exit", args=[session.id])}"' in html
    assert f'data-return-url="{reverse("mark_return", args=[session.id])}"' in html


def test_the_supervisor_form_has_no_exit_endpoints_so_his_behaviour_is_unchanged(
    client_as, now_0730, klass, session, holder, kid
):
    response = client_as(holder).get(
        reverse("wings:record_section", args=[klass.id]), {"date": session.date.isoformat()}
    )
    assert "data-exit-url" not in response.content.decode()


def test_the_script_does_not_switch_the_student_to_absent_when_the_teacher_exits_him():
    source = JS.read_text(encoding="utf-8")
    assert "if (exitUrl) {" in source and "sendExit(cell, value);" in source
    # التحويلُ إلى «غائب» لوجهة المشرف وحدَه: فرعٌ `else if` بعد فرع المعلّم
    assert "} else if (value) {" in source


def test_the_exit_endpoint_records_a_class_exit_and_no_absence(
    client_as, now_0730, session, teacher, kid
):
    response = client_as(teacher).post(
        reverse("mark_exit", args=[session.id]),
        {"student_id": str(kid.id), "destination": "clinic"},
    )
    assert response.status_code == 200
    assert ClassExit.objects.filter(session=session, student=kid, destination="clinic").exists()
    assert not AttendanceEntry.objects.filter(session=session, student=kid).exists()
