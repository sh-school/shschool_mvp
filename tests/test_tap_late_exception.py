"""[LEGAL] نقرةُ التأخّر tap_late استثناءٌ مسمّىً من «مبدئيّ حتى الاعتماد» بقيودها (D-136م، W-20261002-020).

القرارُ (المالك، وحكمُ 0105 على الاستثناء):
- «متأخّر» فقط، لا «غائب» أبداً — النقرةُ تسجّل لحظةَ دخولٍ لا غياباً.
- **لمعلّم الحصّة الفعليّ وحدَه**: لا القيادةُ (كانت تكتب باسمها «نقرةَ معلّم» فتخلط المصدر)، ولا معلّمٌ آخر، ولا المطوّر.
- **بنافذة الحصّة نفسِها** (من بدئها إلى نهايتها) لا حتى نهاية اليوم — فنقرةُ «دخل الآن» بعد انتهاء الحصّة لا معنى لها.
- **لا تكتب فوق رصدٍ آخر**: لا المشرفِ (كما كان)، ولا رصدِ معلّمٍ معتمَدٍ، ولا العيادةِ/البوّابة/النظام — وحدَها نقرةٌ سابقةٌ تُكرَّر بلا أثر.
- يثبّتها المشرفُ أو يكتب فوقها (مساراتُه المعتادة).

وG4 المعدَّلة: `teacher_out` (خروجٌ بإذن) بنافذة اليوم (`can_enter`)، لمعلّم الحصّة وحدَه.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_policy import can_tap_late, tap_window
from operations.models import ClassExit, StudentAttendance
from operations.period_register import tap_late
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff, at

pytestmark = pytest.mark.django_db


def _tap(client_as, user, session, kid):
    return client_as(user).post(
        reverse("mark_late_tap", args=[session.id]), {"student_id": str(kid.id)}
    )


def _row(session, kid):
    return StudentAttendance.objects.filter(session=session, student=kid).first()


@pytest.fixture
def at_730(monkeypatch):
    """07:30 — داخل الحصّة (07:10–07:55)."""
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


# ── النافذة ───────────────────────────────────────────────────────


def test_the_tap_window_is_the_session_itself(session):
    assert tap_window(session) == (at(7, 10), at(7, 55))


def test_the_session_teacher_taps_inside_the_session(client_as, at_730, session, teacher, kid):
    response = _tap(client_as, teacher, session, kid)
    assert response.status_code == 200
    row = _row(session, kid)
    assert (row.status, row.source, row.marked_by_id) == ("late", "teacher_late", teacher.id)
    assert row.late_minutes == 20  # من 07:10 إلى 07:30


def test_a_tap_before_the_session_starts_is_refused(client_as, monkeypatch, session, teacher, kid):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 9, 59))
    assert _tap(client_as, teacher, session, kid).status_code == 403
    assert _row(session, kid) is None


def test_a_tap_after_the_session_ends_is_refused_though_the_school_day_continues(
    client_as, monkeypatch, session, teacher, kid
):
    """النقرةُ بنافذة الحصّة لا اليوم: 07:55:01 مرفوضٌ ولو بقي من اليوم الدراسيّ ساعاتٌ (آخرُه 13:30 في الجرس المضبوط)."""
    monkeypatch.setattr(timezone, "now", lambda: at(7, 55, 1))
    assert _tap(client_as, teacher, session, kid).status_code == 403
    assert _row(session, kid) is None


def test_the_last_second_of_the_session_is_accepted(client_as, monkeypatch, session, teacher, kid):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 55))
    assert _tap(client_as, teacher, session, kid).status_code == 200


def test_the_date_is_doha_not_utc_for_the_tap(client_as, monkeypatch, session, teacher, kid):
    late = dt.datetime(2026, 9, 13, 21, 30, tzinfo=dt.UTC)  # 00:30 من الاثنين بالدوحة
    monkeypatch.setattr(timezone, "now", lambda: late)
    assert _tap(client_as, teacher, session, kid).status_code == 403


# ── من ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["principal", "vice_admin", "vice_academic"])
def test_leadership_may_no_longer_tap_under_a_teachers_name(
    client_as, at_730, school, session, kid, role
):
    leader = _staff(
        school,
        role,
        role,
        "29000007001"
        if role == "principal"
        else "29000007002"
        if role == "vice_admin"
        else "29000007003",
    )
    assert _tap(client_as, leader, session, kid).status_code == 403
    assert _row(session, kid) is None


def test_another_teacher_may_not_tap(client_as, at_730, session, other_teacher, kid):
    assert _tap(client_as, other_teacher, session, kid).status_code == 403
    assert _row(session, kid) is None


def test_the_developer_may_not_tap(client_as, at_730, school, session, kid):
    developer = _staff(school, "platform_developer", "المطوّر", "29000007004")
    developer.is_superuser = True
    developer.save(update_fields=["is_superuser"])
    assert _tap(client_as, developer, session, kid).status_code == 403
    assert _row(session, kid) is None


def test_a_cancelled_session_cannot_be_tapped(client_as, at_730, session, teacher, kid):
    session.status = "cancelled"
    session.save(update_fields=["status"])
    assert _tap(client_as, teacher, session, kid).status_code == 403


def test_a_student_of_another_section_is_not_found(
    client_as, at_730, school, year, session, teacher
):
    from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

    other = ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year
    )
    outsider = UserFactory(full_name="طالبٌ من شعبةٍ أخرى", national_id="29000007005")
    StudentEnrollmentFactory(student=outsider, class_group=other)
    assert _tap(client_as, teacher, session, outsider).status_code == 404


# ── ما لا يُكتب فوقه ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "source", ["supervisor", "teacher", "clinic", "gate", "system", "teacher_out"]
)
def test_a_tap_never_overwrites_another_recorded_row(
    client_as, at_730, session, teacher, holder, kid, source
):
    StudentAttendance.objects.create(
        session=session,
        student=kid,
        school=session.school,
        status="absent",
        source=source,
        marked_by=holder,
    )
    response = _tap(client_as, teacher, session, kid)
    assert response.status_code == 200  # النقرةُ مقبولةٌ (بلا أثر) لا خطأ
    row = _row(session, kid)
    assert (row.status, row.source) == ("absent", source)


def test_a_repeated_tap_does_not_change_the_minutes(client_as, monkeypatch, session, teacher, kid):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 20))
    _tap(client_as, teacher, session, kid)
    monkeypatch.setattr(timezone, "now", lambda: at(7, 40))
    _tap(client_as, teacher, session, kid)
    assert _row(session, kid).late_minutes == 10


def test_the_tap_writes_only_late_never_absent(session, teacher, kid):
    """قيدُ 0105 (أ): الدالّةُ لا تكتب غيرَ late."""
    tap_late(session, kid, by=teacher, now=at(7, 30))
    assert _row(session, kid).status == "late"


def test_can_tap_late_gives_a_reason_per_refusal(school, session, teacher, other_teacher, kid):
    assert can_tap_late(teacher, session, kid, now=at(7, 30)).allowed
    assert can_tap_late(other_teacher, session, kid, now=at(7, 30)).reason == "not_teacher"
    assert can_tap_late(teacher, session, kid, now=at(7, 9)).reason == "before_start"
    assert can_tap_late(teacher, session, kid, now=at(8, 0)).reason == "after_window"


# ── teacher_out: بنافذة اليوم لمعلّم الحصّة (G4 المعدَّلة) ────────────


def _leave(client_as, user, session, kid):
    return client_as(user).post(
        reverse("mark_exit", args=[session.id]),
        {"student_id": str(kid.id), "destination": "restroom"},
    )


def test_the_session_teacher_may_send_a_student_out_inside_the_day(
    client_as, monkeypatch, session, teacher, kid
):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))
    assert _leave(client_as, teacher, session, kid).status_code == 200
    assert ClassExit.objects.filter(session=session, student=kid).exists()


def test_the_exit_window_is_the_school_day_not_the_session(
    client_as, monkeypatch, session, teacher, kid
):
    """بخلاف النقرة: الخروجُ بإذنٍ يُقيَّد بنافذة اليوم (آخرُها 13:30) — فبعد نهاية الحصّة وقبل نهاية الدوام مقبول."""
    monkeypatch.setattr(timezone, "now", lambda: at(9, 0))
    assert _leave(client_as, teacher, session, kid).status_code == 200


def test_the_exit_after_the_school_day_is_refused(client_as, monkeypatch, session, teacher, kid):
    monkeypatch.setattr(timezone, "now", lambda: at(13, 30, 1))
    assert _leave(client_as, teacher, session, kid).status_code == 403
    assert not ClassExit.objects.exists()


def test_another_teacher_may_not_send_out(client_as, monkeypatch, session, other_teacher, kid):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))
    assert _leave(client_as, other_teacher, session, kid).status_code == 403
    assert not ClassExit.objects.exists()


def test_leadership_may_not_send_out_under_a_teachers_name(
    client_as, monkeypatch, school, session, kid
):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))
    leader = _staff(school, "principal", "المدير", "29000007010")
    assert _leave(client_as, leader, session, kid).status_code == 403
    assert not ClassExit.objects.exists()
