"""كتابةُ المشرف فوق رصدِ معلّمٍ لا تكون استبدالاً صامتاً (A11، حكمُ 0105 P2 — W-20261002-020).

المشرفُ يثبّت الحصّةَ (`confirm_period`) فيكتب `StudentAttendance` لكلّ طالب. وكان `update_or_create` يستبدل ما قبله بلا أثر:
إدخالُ معلّمٍ معلَّقٌ يبقى معلَّقاً إلى أن يصطدم اعتمادُه بـ`non_teacher_row`، ورصدٌ معتمَدٌ أو نقرةُ تأخّرٍ تُمحى بلا سطر.
فالإدخالُ يبقى كما كتبه المعلّمُ (سجلٌّ ملحقٌ فقط) ويُضاف قرارٌ مسبَّبٌ بفاعله، وكلُّ استبدالٍ لرصدٍ سابقٍ له سطرُ تدقيقٍ بقبلٍ وبعد.
"""

import datetime as dt

import pytest

from core.models import AuditLog
from operations.attendance_entries import state_of, submit_entry
from operations.models import AttendanceDecision, StudentAttendance
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


def test_a_supervisor_confirmation_never_touches_a_pending_teacher_entry(
    klass, session, teacher, holder, kid
):
    """قاموسُ الغياب 2026-10-05 §٣ (يُلغي الرفضَ التلقائيَّ القديم): التثبيتُ يملأ الفراغَ فقط ولا يكتب فوق إدخال معلّمٍ ولا يرفضه."""
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    _confirm(klass, kid, holder, "present")
    entry.refresh_from_db()
    assert entry.status == "absent"
    assert not AttendanceDecision.objects.filter(entry=entry).exists()  # لم يُرفض ولم يُعتمد
    assert state_of(entry) == "pending"
    assert not StudentAttendance.objects.filter(
        session=session, student=kid
    ).exists()  # ولم يُكتب فوقه
    assert not _audits().exists()


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
