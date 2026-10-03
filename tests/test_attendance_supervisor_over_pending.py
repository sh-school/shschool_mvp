"""كتابةُ المشرف فوق رصدِ معلّمٍ لا تكون استبدالاً صامتاً (A11، حكمُ 0105 P2 — W-20261002-020).

المشرفُ يثبّت الحصّةَ (`confirm_period`) فيكتب `StudentAttendance` لكلّ طالب. وكان `update_or_create` يستبدل ما قبله بلا أثر:
إدخالُ معلّمٍ معلَّقٌ يبقى معلَّقاً إلى أن يصطدم اعتمادُه بـ`non_teacher_row`، ورصدٌ معتمَدٌ أو نقرةُ تأخّرٍ تُمحى بلا سطر.
فالإدخالُ يبقى كما كتبه المعلّمُ (سجلٌّ ملحقٌ فقط) ويُضاف قرارٌ مسبَّبٌ بفاعله، وكلُّ استبدالٍ لرصدٍ سابقٍ له سطرُ تدقيقٍ بقبلٍ وبعد.
"""

import datetime as dt

import pytest

from core.models import AuditLog
from operations.attendance_entries import decide_entry, state_of, submit_entry, unapproved_report
from operations.models import AttendanceDecision, AttendanceEntry, StudentAttendance
from operations.period_register import confirm_period
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db

NOW = at(7, 30)
START = dt.time(7, 10)


def _confirm(klass, kid, holder, status="present"):
    return confirm_period(
        klass, SUNDAY, START, {str(kid.id): {"status": status}}, holder, now=at(7, 40)
    )


def _audits():
    return AuditLog.objects.filter(object_repr__contains="تثبيتُ مشرفٍ يستبدل")


def test_a_supervisor_confirmation_over_a_pending_entry_keeps_the_entry_and_records_why(
    klass, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    _confirm(klass, kid, holder, "present")
    assert AttendanceEntry.objects.filter(pk=entry.pk).exists()
    entry.refresh_from_db()
    assert entry.status == "absent"
    decision = AttendanceDecision.objects.get(entry=entry)
    assert decision.decision == "rejected"
    assert decision.basis == "supervisor_record"
    assert decision.decided_by_id == holder.id
    assert "مشرف" in decision.reason
    assert state_of(entry) == "rejected"
    assert StudentAttendance.objects.get(session=session, student=kid).source == "supervisor"


def test_the_overridden_entry_leaves_the_unapproved_report(
    school, klass, session, teacher, holder, kid
):
    submit_entry(teacher, session, kid, "absent", now=NOW)
    assert len(unapproved_report(school, older_than_hours=1, now=at(13, 0))) == 1
    _confirm(klass, kid, holder)
    assert unapproved_report(school, older_than_hours=1, now=at(13, 0)) == []


def test_a_confirmation_over_an_approved_teacher_row_audits_before_and_after(
    klass, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    decide_entry(holder, entry, approve=True, now=NOW)
    _confirm(klass, kid, holder, "present")
    (audit,) = _audits()
    assert audit.changes["before"]["status"] == "absent"
    assert audit.changes["before"]["source"] == "teacher"
    assert audit.changes["after"]["status"] == "present"
    assert audit.user_id == holder.id
    # الإدخالُ المقرَّر لا يُقرَّر ثانيةً.
    assert AttendanceDecision.objects.filter(entry=entry).count() == 1


def test_a_confirmation_over_a_teacher_late_tap_audits_it(klass, session, teacher, holder, kid):
    StudentAttendance.objects.create(
        school=session.school,
        session=session,
        student=kid,
        status="late",
        source="teacher_late",
        marked_by=teacher,
        late_minutes=4,
    )
    _confirm(klass, kid, holder, "present")
    (audit,) = _audits()
    assert audit.changes["before"]["source"] == "teacher_late"


def test_a_first_confirmation_with_nothing_before_writes_no_override_audit(
    klass, session, holder, kid
):
    _confirm(klass, kid, holder)
    assert not _audits().exists()
    assert not AttendanceDecision.objects.exists()


def test_a_confirmation_over_a_previous_supervisor_row_is_not_an_override_of_a_teacher(
    klass, session, holder, kid
):
    _confirm(klass, kid, holder, "present")
    _confirm(klass, kid, holder, "absent")
    assert not _audits().exists()
