"""تجربة لوحة المعلّم: شارةُ حالة الرصد لكل حصّة، ونصُّ البلاطة، وصفوفٌ مضغوطة (W-20261003-038، D-177م).

الشارةُ تُقرأ من رؤوس الإدخالات لا من `StudentAttendance`: المعلَّقُ ليس حضوراً ولا غياباً فيُعرض وسماً.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.dashboard_selectors import session_entry_states
from operations.attendance_entries import decide_entry, submit_entry
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


def _enter(teacher, session, kid):
    return submit_entry(teacher, session, kid, "absent", now=at(7, 30))


def test_a_session_with_no_entry_says_not_entered(session):
    assert session_entry_states([session.id]) == {session.id: "none"}


def test_an_undecided_entry_makes_the_session_pending(session, teacher, kid, now_0730):
    _enter(teacher, session, kid)
    assert session_entry_states([session.id]) == {session.id: "pending"}


def test_an_approved_entry_makes_the_session_approved(session, teacher, holder, kid, now_0730):
    entry = _enter(teacher, session, kid)
    decide_entry(holder, entry, approve=True, now=at(7, 31))
    assert session_entry_states([session.id]) == {session.id: "approved"}


def test_a_rejected_only_session_goes_back_to_not_entered(session, teacher, holder, kid, now_0730):
    """المرفوضُ لا أثرَ له: على المعلّم أن يرصد من جديد."""
    entry = _enter(teacher, session, kid)
    decide_entry(holder, entry, approve=False, reason="سببٌ", now=at(7, 31))
    assert session_entry_states([session.id]) == {session.id: "none"}


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
    client_as, teacher, session, kid, now_0730, monkeypatch
):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)
    html = client_as(teacher).get(reverse("dashboard")).content.decode()
    assert "لم يُدخَل" in html
    _enter(teacher, session, kid)
    html = client_as(teacher).get(reverse("dashboard")).content.decode()
    assert "بانتظار الاعتماد" in html


def test_the_dashboard_makes_a_single_state_query_not_one_per_row(
    client_as, teacher, session, monkeypatch
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
    client_as, teacher, monkeypatch
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
