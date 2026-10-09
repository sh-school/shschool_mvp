"""[LEGAL] سجلُّ رصد المعلّم المضاف إليه ولا يُمحى، واعتمادُه، وما يصل `StudentAttendance` (W-20261002-020).

التصميمُ بحكم 0105 (شروط M1–M4): جدولان مضافان-فقط — `AttendanceEntry` (ما أدخله المعلّم) و
`AttendanceDecision` (قرارُ الاعتماد أو الرفض، صفٌّ واحدٌ لكلّ إدخال) — ويبقى `StudentAttendance` الرصدَ
**المعتمَدَ الفعّالَ** بقيده الفريد، فلا يُكتب إليه إلّا عند الاعتماد (أو فوراً للتربية الخاصّة).
فيرى كلُّ قارئٍ المعتمَدَ وحدَه دون المساس بالقرّاء.

الرموزُ من مواصفة W-020: E إدخال، S تبديل، A اعتماد، L سجلّ، X تربيةٌ خاصّة، M من شروط 0105.
"""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction

from core.models import AuditLog
from operations.attendance_entries import (
    EntryError,
    EntryRefusedError,
    submit_entry,
)
from operations.models import AttendanceEntry, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import (
    ENROLLED,
    MONDAY,
    SUNDAY,
    at,
)
from tests.conftest import StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

NOW = at(7, 30)


def _submit(teacher, session, kid, status="absent", **kwargs):
    return submit_entry(teacher, session, kid, status, now=kwargs.pop("now", NOW), **kwargs)


def _row(session, kid):
    return StudentAttendance.objects.filter(session=session, student=kid).first()


def _audits(action=None):
    qs = AuditLog.objects.filter(model_name="other", object_repr__startswith="رصدُ المعلّم")
    return qs.filter(action=action) if action else qs


# ══════════════════════════════════════════════════════════════════
# الإدخال: مبدئيٌّ لا يصل المعتمَدَ
# ══════════════════════════════════════════════════════════════════


def test_a_refused_entry_writes_nothing(session, other_teacher, kid):
    with pytest.raises(EntryRefusedError) as caught:
        _submit(other_teacher, session, kid)
    assert caught.value.reason == "not_teacher"
    assert not AttendanceEntry.objects.exists()
    assert _row(session, kid) is None


def test_a_teacher_may_only_enter_present_absent_or_late(session, teacher, kid):
    with pytest.raises(EntryError):
        _submit(teacher, session, kid, "excused")
    assert not AttendanceEntry.objects.exists()


def test_a_late_entry_carries_its_minutes(session, teacher, kid):
    entry = _submit(teacher, session, kid, "late", tardiness_minutes=7)
    assert entry.tardiness_minutes == 7


# ══════════════════════════════════════════════════════════════════
# الاعتماد
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# A9 — التصحيحُ بعد الاعتماد: صفٌّ جديدٌ بسببٍ لا تعديل
# ══════════════════════════════════════════════════════════════════


def test_m4_a_row_has_one_successor_only(session, teacher, kid):
    """لا فرعان لصفٍّ واحد: `supersedes` فريدٌ في القاعدة."""
    from django.db import IntegrityError

    first = _submit(teacher, session, kid, "absent")
    AttendanceEntry.objects.create(
        school=session.school,
        session=session,
        student=kid,
        status="present",
        entered_by=teacher,
        supersedes=first,
        correction_reason="س",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AttendanceEntry.objects.create(
            school=session.school,
            session=session,
            student=kid,
            status="late",
            entered_by=teacher,
            supersedes=first,
            correction_reason="ص",
        )


def test_m4_one_root_entry_per_session_and_student(session, teacher, kid):
    from django.db import IntegrityError

    AttendanceEntry.objects.create(
        school=session.school, session=session, student=kid, status="absent", entered_by=teacher
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AttendanceEntry.objects.create(
            school=session.school,
            session=session,
            student=kid,
            status="present",
            entered_by=teacher,
        )


# ══════════════════════════════════════════════════════════════════
# S — التبديل: الجديدُ يضيف نسخةً ولا يمحو ما قبله
# ══════════════════════════════════════════════════════════════════


def test_s2_the_original_teacher_cannot_enter_after_the_handover(
    session, teacher, other_teacher, kid
):
    session.original_teacher = teacher
    session.teacher = other_teacher
    session.save(update_fields=["teacher", "original_teacher"])
    with pytest.raises(EntryRefusedError):
        _submit(teacher, session, kid, "absent")


# ══════════════════════════════════════════════════════════════════
# X — التربيةُ الخاصّة نهائيّةٌ بلا اعتماد، والشعبةُ العاديّةُ بلا جناحٍ معلَّقة
# ══════════════════════════════════════════════════════════════════


def test_x1b_special_education_is_final_with_a_self_decision_marked_as_such(
    school, special_klass, teacher, bells
):
    student = UserFactory(full_name="طالب التربية الخاصّة", national_id="29000002010")
    StudentEnrollmentFactory(student=student, class_group=special_klass, enrolled_at=ENROLLED)
    sess = Session.objects.create(
        school=school,
        class_group=special_klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    entry = submit_entry(teacher, sess, student, "absent", now=at(8, 10))
    decision = entry.decision
    assert decision.decision == "approved"
    assert decision.basis == "special_ed_self"
    assert decision.decided_by_id == teacher.id
    row = _row(sess, student)
    assert row.status == "absent"
    assert row.source == "teacher"
    assert AuditLog.objects.filter(changes__basis="special_ed_self").exists()


# ══════════════════════════════════════════════════════════════════
# L — سجلٌّ لا يُمحى: ORM وقاعدةُ البيانات
# ══════════════════════════════════════════════════════════════════


def test_l1_an_entry_cannot_be_updated_or_deleted_through_the_orm(session, teacher, kid):
    entry = _submit(teacher, session, kid, "absent")
    entry.status = "present"
    with pytest.raises(PermissionDenied):
        entry.save()
    with pytest.raises(PermissionDenied):
        entry.delete()
    with pytest.raises(PermissionDenied):
        AttendanceEntry.objects.filter(pk=entry.pk).update(status="present")
    with pytest.raises(PermissionDenied):
        AttendanceEntry.objects.filter(pk=entry.pk).delete()


def _raw(sql, *params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


# ══════════════════════════════════════════════════════════════════
# تقرير «غيرُ معتمَد بعد X ساعة» — قراءةٌ فقط للنائب
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# M4-ب — مزامنةُ الحصص لا تحذف حصّةً لها إدخالٌ ولو معلَّقاً
# ══════════════════════════════════════════════════════════════════


def test_m4_a_session_with_a_pending_entry_is_not_untouched(session, teacher, kid):
    from operations.services.schedule_sessions import ScheduleSessionsMixin

    before = ScheduleSessionsMixin._untouched(Session.objects.filter(pk=session.pk)).count()
    assert before == 1
    _submit(teacher, session, kid, "absent")
    after = ScheduleSessionsMixin._untouched(Session.objects.filter(pk=session.pk)).count()
    assert after == 0


def test_m4_a_session_with_entries_cannot_be_deleted(session, teacher, kid):
    from django.db.models import ProtectedError

    _submit(teacher, session, kid, "absent")
    with pytest.raises(ProtectedError):
        session.delete()


# ══════════════════════════════════════════════════════════════════
# الشعبة/اليوم الآخر — المعلّمُ لا يرى إلّا بيئتَه
# ══════════════════════════════════════════════════════════════════


def test_an_entry_for_another_day_session_is_outside_its_window(session, teacher, kid):
    with pytest.raises(EntryRefusedError) as caught:
        submit_entry(teacher, session, kid, "absent", now=at(7, 30, day=MONDAY))
    assert caught.value.reason == "after_window"


# ══════════════════════════════════════════════════════════════════
# M3 — محوُ طالبٍ (PDPPL م.18) يمرّ بمساره المسمّى وحدَه
# ══════════════════════════════════════════════════════════════════


def test_m3_the_erasure_flag_does_not_leak_to_the_next_transaction(session, teacher, kid):
    """علَمُ المحو محلّيٌّ في المعاملة (set_config … true): ما بعدها يُرفض فيه الحذف."""
    from operations.attendance_entries import erase_attendance_ledger

    _submit(teacher, session, kid, "absent")
    erase_attendance_ledger(kid)
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(DatabaseError), transaction.atomic():
        _raw("DELETE FROM operations_attendanceentry WHERE id = %s", str(entry.pk))
    assert AttendanceEntry.objects.filter(pk=entry.pk).exists()
