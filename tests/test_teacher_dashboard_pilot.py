"""تجربة لوحة المعلّم: شارةُ حالة الرصد لكل حصّة، ونصُّ البلاطة، وصفوفٌ مضغوطة (W-20261003-038، D-177م).

الشارةُ تُقرأ من رؤوس الإدخالات لا من `StudentAttendance`: المعلَّقُ ليس حضوراً ولا غياباً فيُعرض وسماً.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.dashboard_selectors import session_entry_states
from operations.attendance_entries import submit_entry
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def live_schedule(school, klass, teacher, year):
    """جدولٌ حيّ للمدرسة (حصّةٌ نشطة): بغيابه تعرض اللوحةُ بطاقةَ الرصد المؤقّت لا حصصَ اليوم (W-20261010-055)."""
    from operations.models import ScheduleSlot, Subject

    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=klass,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=year,
    )


def _enter(teacher, session, kid):
    return submit_entry(teacher, session, kid, "absent", now=at(7, 30))


def test_a_session_with_no_entry_says_not_entered(session):
    assert session_entry_states([session.id]) == {session.id: "none"}


def test_an_entry_is_final_so_the_session_is_recorded(session, teacher, kid, now_0730):
    """لا اعتمادَ في المنصّة (أمر المالك 10-09): رصدُ المعلّم نهائيٌّ فيُقرأ فوراً «مرصود»."""
    _enter(teacher, session, kid)
    assert session_entry_states([session.id]) == {session.id: "approved"}


def test_the_states_come_from_one_query_for_all_sessions(
    django_assert_num_queries, session, school, klass, teacher
):
    other = type(session).objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    with django_assert_num_queries(1):
        states = session_entry_states([session.id, other.id])
    assert states == {session.id: "none", other.id: "none"}


def test_no_sessions_means_no_query(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert session_entry_states([]) == {}


def test_the_dashboard_row_shows_the_state_badge(
    client_as, teacher, session, kid, now_0730, monkeypatch, live_schedule
):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)
    html = client_as(teacher).get(reverse("dashboard")).content.decode()
    assert "لم يُدخَل" in html
    _enter(teacher, session, kid)
    html = client_as(teacher).get(reverse("dashboard")).content.decode()
    assert "تم الرصد" in html


def test_the_dashboard_makes_a_single_state_query_not_one_per_row(
    client_as, teacher, session, monkeypatch, live_schedule
):
    """لا N+1: عددُ استعلاماتِ الإدخالات في اللوحة واحدٌ مهما كثرت الحصص."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)
    with CaptureQueriesContext(connection) as ctx:
        client_as(teacher).get(reverse("dashboard"))
    entry_queries = [q for q in ctx.captured_queries if "operations_attendanceentry" in q["sql"]]
    assert len(entry_queries) <= 1


def test_the_tile_no_longer_says_attendance_is_for_special_education_only(
    client_as, teacher, monkeypatch, live_schedule
):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)
    html = client_as(teacher).get(reverse("dashboard")).content.decode()
    assert "والحضورُ لشُعب التربية الخاصّة" not in html
    assert "حصصُ اليوم وتسجيلُ حضور الطلبة" in html


def test_the_session_rows_are_compact():
    """py-2 لا py-4: 6 حصصٍ بـ16px أقلّ لكلّ صفّ يُنزل فائضَ 768 من 78 إلى 0 (قياس 2026-10-04)."""
    from pathlib import Path

    source = Path("templates/dashboard/partials/_sessions_list.html").read_text(encoding="utf-8")
    assert "px-5 py-2" in source and "py-4" not in source


def test_without_a_live_schedule_the_dashboard_shows_the_provisional_card_not_the_rows(
    client_as, teacher, session, monkeypatch
):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)
    html = client_as(teacher).get(reverse("dashboard")).content.decode()
    assert "شُعبي للرصد" in html and "لم يُدخَل" not in html
