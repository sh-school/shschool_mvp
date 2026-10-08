"""لوحة الطالب تعدّ حضورَ العام الدراسيّ الجاري وحده (W-20261008-001 · البند 2).

العنوان «حضوري هذا العام» وكان الرقمُ تراكمياً لكلّ الأعوام؛ والسطورُ سطورُ حصصٍ لا أيّامٍ.
"""

import datetime as dt

import pytest

from core import dashboard_selectors
from operations.models import Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY

pytestmark = pytest.mark.django_db

WINDOW = (dt.date(2026, 9, 1), dt.date(2027, 6, 30))


def _mark(school, session, kid, status):
    return StudentAttendance.objects.create(
        session=session, student=kid, school=school, status=status
    )


def test_student_dashboard_counts_only_the_current_year(
    monkeypatch, school, klass, teacher, session, kid, bells
):
    monkeypatch.setattr(dashboard_selectors, "academic_year_window", lambda *_a, **_k: WINDOW)
    old = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=dt.date(2025, 10, 5),
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    _mark(school, old, kid, "absent")  # عامٌ سابق: لا يُعدّ
    _mark(school, session, kid, "present")  # الجاريّ

    ctx = dashboard_selectors.get_student_ctx(kid, school, SUNDAY)

    assert (ctx["student_present"], ctx["student_absent"], ctx["student_late"]) == (1, 0, 0)
