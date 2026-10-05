"""علامةُ «رصد معلّم بانتظار اعتماد المشرف» في تقرير غياب اليوم (W-20261005-002، D-125م).

المبدئيُّ وسمٌ للمتابعة لا احتساب: لا يزيد غياباً ولا تأخّراً ولا طلاباً مرصودين ولا رفعاً وزاريّاً قبل الاعتماد.
والعدُّ لإدخالات غائب/متأخّر فقط، لرأس الإدخال بلا قرار.
"""

import datetime as dt

import pytest
from django.urls import reverse

from operations.attendance_entries import decide_entry, submit_entry
from operations.daily_absence import daily_report
from operations.models import Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


def _second_session(school, klass, teacher):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )


def _enter(teacher, session, kid, status="absent"):
    """الإدخالُ بعد بدء الحصّة بدقائق (الثانيةُ تبدأ 8:00)."""
    moment = at(8, 5) if session.start_time.hour == 8 else at(7, 30)
    return submit_entry(teacher, session, kid, status, now=moment)


def test_a_pending_absence_is_a_mark_not_an_absence(school, session, teacher, kid):
    _enter(teacher, session, kid)

    report = daily_report(school, SUNDAY)

    assert report.rows == []
    assert (report.absent_students, report.late_students, report.students_recorded) == (0, 0, 0)
    assert report.ministry_absent_count == 0
    assert [(m.student, m.count) for m in report.pending_only] == [(kid, 1)]
    assert report.pending_total == 1


def test_a_pending_late_counts_but_a_pending_present_does_not(school, klass, session, teacher, kid):
    _enter(teacher, session, kid, "late")
    other = _second_session(school, klass, teacher)
    _enter(teacher, other, kid, "present")

    report = daily_report(school, SUNDAY)

    assert report.pending_total == 1


def test_the_mark_sits_on_a_student_who_already_has_an_approved_absence(
    school, klass, session, teacher, holder, kid
):
    approved = _enter(teacher, session, kid)
    decide_entry(holder, approved, approve=True, now=at(7, 31))
    _enter(teacher, _second_session(school, klass, teacher), kid)

    report = daily_report(school, SUNDAY)

    (row,) = report.rows
    assert row.student == kid
    assert row.pending_marks == 1
    assert (row.absent_periods, report.absent_students) == (1, 1), "المعلَّقُ لم يزد الغياب"
    assert report.pending_only == [], "ظاهرٌ في جدوله فلا يتكرّر في الكتلة المنفصلة"
    assert report.pending_total == 1


def test_a_decided_entry_is_no_longer_pending(school, session, teacher, holder, kid):
    entry = _enter(teacher, session, kid)
    decide_entry(holder, entry, approve=True, now=at(7, 31))

    assert daily_report(school, SUNDAY).pending_total == 0


def test_a_rejected_entry_leaves_no_mark(school, session, teacher, holder, kid):
    entry = _enter(teacher, session, kid)
    decide_entry(holder, entry, approve=False, reason="خطأ إدخال", now=at(7, 31))

    report = daily_report(school, SUNDAY)

    assert (report.pending_total, report.pending_only, report.rows) == (0, [], [])


def test_the_mark_follows_the_report_scope(school, session, teacher, other_teacher, kid):
    _enter(teacher, session, kid)

    assert daily_report(school, SUNDAY, teacher_ids=[other_teacher.id]).pending_total == 0
    assert daily_report(school, SUNDAY, teacher_ids=[teacher.id]).pending_total == 1
    assert daily_report(school, SUNDAY, student_ids=[]).pending_total == 0
    assert daily_report(school, SUNDAY, student_ids=[kid.id]).pending_total == 1


def test_a_cancelled_session_leaves_no_mark(school, session, teacher, kid):
    _enter(teacher, session, kid)
    Session.objects.filter(pk=session.pk).update(status="cancelled")

    assert daily_report(school, SUNDAY).pending_total == 0


def test_the_page_shows_the_wording_and_the_total_without_touching_counts(
    client_as, school, session, teacher, kid, holder
):
    _enter(teacher, session, kid)

    body = (
        client_as(holder)
        .get(reverse("daily_report") + f"?date={SUNDAY.isoformat()}")
        .content.decode()
    )

    assert "رصد معلّم بانتظار اعتماد المشرف: 1" in body
    assert kid.full_name in body


def test_a_pending_absence_never_reaches_the_ministry_list(
    client_as, school, klass, session, teacher, kid, holder
):
    """طالبٌ معلَّق غيابُه في الحصّتين الأولى والثانية لا يدخل `ministry_rows` ولا قائمةَ الرفع قبل الاعتماد."""
    _enter(teacher, session, kid)
    _enter(teacher, _second_session(school, klass, teacher), kid)

    report = daily_report(school, SUNDAY)
    body = (
        client_as(holder)
        .get(reverse("daily_report") + f"?date={SUNDAY.isoformat()}")
        .content.decode()
    )

    assert report.ministry_rows == [] and report.ministry_absent_count == 0
    assert "للرفع في نظام الوزارة" not in body
    assert report.pending_total == 2


def test_a_role_that_cannot_see_the_report_never_sees_the_wording(
    client_as, school, session, teacher, kid
):
    _enter(teacher, session, kid)

    response = client_as(teacher).get(reverse("daily_report") + f"?date={SUNDAY.isoformat()}")

    assert "رصد معلّم بانتظار اعتماد المشرف" not in response.content.decode()
