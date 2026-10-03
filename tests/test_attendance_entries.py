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
    EntryConflictError,
    EntryError,
    EntryRefusedError,
    decide_entry,
    head_of,
    pending_entries,
    state_of,
    submit_entry,
    unapproved_report,
)
from operations.models import AttendanceDecision, AttendanceEntry, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import (
    ENROLLED,
    MONDAY,
    SUNDAY,
    _cover,
    _staff,
    at,
)
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

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


def test_a_teacher_entry_in_a_wing_section_is_pending_and_writes_no_attendance_row(
    session, teacher, kid
):
    entry = _submit(teacher, session, kid, "absent")
    assert state_of(entry) == "pending"
    assert entry.entered_by_id == teacher.id
    assert entry.school_id == session.school_id
    assert entry.entered_at is not None
    assert _row(session, kid) is None
    assert head_of(session, kid) == entry


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


def test_the_same_submission_twice_is_one_row(session, teacher, kid):
    """N6: نقرةٌ مكرّرةٌ لا تضاعف المعلَّق."""
    first = _submit(teacher, session, kid, "absent")
    again = _submit(teacher, session, kid, "absent")
    assert again.pk == first.pk
    assert AttendanceEntry.objects.filter(session=session, student=kid).count() == 1


def test_a_pending_entry_is_not_a_recorded_presence_or_absence(session, teacher, kid):
    _submit(teacher, session, kid, "absent")
    assert not StudentAttendance.objects.filter(session=session).exists()
    assert [e.student_id for e in pending_entries(session)] == [kid.id]


def test_entering_writes_an_audit_line_with_the_actor_role(session, teacher, kid):
    entry = _submit(teacher, session, kid, "absent")
    line = _audits("create").get()
    assert line.user_id == teacher.id
    assert line.object_id == str(entry.pk)
    assert line.changes["role"] == "teacher"
    assert line.changes["status"] == "absent"


def test_the_audit_line_holds_no_student_name(session, teacher, kid):
    """PDPPL: المعرّفاتُ لا الأسماء في سجلّ التدقيق."""
    _submit(teacher, session, kid, "absent")
    line = _audits("create").get()
    assert kid.full_name not in line.object_repr
    assert kid.full_name not in str(line.changes)


# ══════════════════════════════════════════════════════════════════
# الاعتماد
# ══════════════════════════════════════════════════════════════════


def test_a1_the_wing_holder_approves_and_the_effective_row_appears(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    decision, created = decide_entry(holder, entry, approve=True)
    assert created
    assert decision.decision == "approved"
    assert decision.basis == "wing_holder"
    assert decision.decided_by_id == holder.id
    row = _row(session, kid)
    assert row.status == "absent"
    assert row.source == "teacher"
    assert row.marked_by_id == teacher.id
    assert state_of(entry) == "approved"


def test_a2_the_holder_of_another_wing_cannot_decide(school, year, session, teacher, kid):
    from core.models import Wing

    other_holder = _staff(school, "admin_supervisor", "مشرف آخر", "29000002001")
    Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(EntryRefusedError) as caught:
        decide_entry(other_holder, entry, approve=True)
    assert caught.value.reason == "not_holder"
    assert not AttendanceDecision.objects.exists()
    assert _row(session, kid) is None


def test_a6_nobody_approves_what_he_entered_or_his_own_session(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(EntryRefusedError):
        decide_entry(teacher, entry, approve=True)
    assert not AttendanceDecision.objects.exists()


def test_a7_leadership_decides_only_when_no_holder_and_records_why(
    school, wing, session, teacher, kid
):
    leader = _staff(school, "vice_admin", "النائب", "29000002002")
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(EntryRefusedError):
        decide_entry(leader, entry, approve=True)
    wing.supervisor = None
    wing.save(update_fields=["supervisor"])
    decision, _ = decide_entry(leader, entry, approve=True)
    assert decision.basis == "leadership_no_holder"
    assert decision.evidence["holder_id"] is None


def test_the_decision_keeps_its_evidence_and_does_not_recompute(
    school, wing, session, teacher, holder, kid
):
    """إن تغيّرت التغطيةُ بعد القرار بقي الدليلُ كما كان وقتَه."""
    substitute = _staff(school, "admin_supervisor", "البديل", "29000002003")
    cover = _cover(wing, substitute, SUNDAY, None, by=holder)
    entry = _submit(teacher, session, kid, "absent")
    decision, _ = decide_entry(substitute, entry, approve=True)
    assert decision.evidence["wing_id"] == str(wing.pk)
    assert decision.evidence["coverage_id"] == str(cover.pk)
    assert decision.evidence["holder_id"] == str(substitute.pk)
    cover.start_date = SUNDAY - dt.timedelta(days=5)
    cover.end_date = SUNDAY - dt.timedelta(days=1)
    cover.save()
    decision.refresh_from_db()
    assert decision.evidence["holder_id"] == str(substitute.pk)


def test_rejection_needs_a_reason_and_writes_no_effective_row(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(EntryError):
        decide_entry(holder, entry, approve=False, reason="")
    decision, _ = decide_entry(holder, entry, approve=False, reason="الطالبُ كان في العيادة")
    assert decision.decision == "rejected"
    assert state_of(entry) == "rejected"
    assert _row(session, kid) is None


def test_after_a_rejection_the_teacher_may_enter_again(session, teacher, holder, kid):
    first = _submit(teacher, session, kid, "absent")
    decide_entry(holder, first, approve=False, reason="خطأٌ في الاسم")
    second = _submit(teacher, session, kid, "present")
    assert second.supersedes_id == first.pk
    assert head_of(session, kid) == second
    assert state_of(first) == "superseded"


def test_a10_a_double_decision_is_one_decision(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    first, created_first = decide_entry(holder, entry, approve=True)
    second, created_second = decide_entry(holder, entry, approve=True)
    assert created_first and not created_second
    assert second.pk == first.pk
    assert AttendanceDecision.objects.count() == 1


def test_a10_the_database_itself_refuses_a_second_decision(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True)
    from django.db import IntegrityError

    with pytest.raises(IntegrityError), transaction.atomic():
        AttendanceDecision.objects.create(
            school=session.school,
            entry=entry,
            decision="approved",
            decided_by=holder,
            basis="wing_holder",
        )


def test_a_superseded_entry_cannot_be_decided(session, teacher, holder, kid):
    first = _submit(teacher, session, kid, "absent")
    _submit(teacher, session, kid, "present")
    with pytest.raises(EntryError) as caught:
        decide_entry(holder, first, approve=True)
    assert caught.value.code == "superseded"


def test_approval_never_writes_over_a_row_the_supervisor_recorded(session, teacher, holder, kid):
    """التعارضُ: يبقى الإدخالُ معلَّقاً ويبقى رصدُ المشرف — لا كتابةَ فوق رصدٍ بشريّ آخر."""
    StudentAttendance.objects.create(
        session=session,
        student=kid,
        school=session.school,
        status="present",
        source="supervisor",
        marked_by=holder,
    )
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(EntryConflictError):
        decide_entry(holder, entry, approve=True)
    assert not AttendanceDecision.objects.exists()
    assert state_of(entry) == "pending"
    assert _row(session, kid).status == "present"
    # ويُحلّ بالرفض بسبب فيبقى رصدُ المشرف.
    decide_entry(holder, entry, approve=False, reason="رصدُ المشرف أدقّ")
    assert _row(session, kid).source == "supervisor"


def test_approval_replaces_a_teacher_late_tap_with_an_audit_line(session, teacher, holder, kid):
    StudentAttendance.objects.create(
        session=session,
        student=kid,
        school=session.school,
        status="late",
        late_minutes=4,
        source="teacher_late",
        marked_by=teacher,
    )
    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True)
    row = _row(session, kid)
    assert row.status == "absent"
    line = _audits("update").get()
    assert line.changes["before"]["status"] == "late"
    assert line.changes["after"]["status"] == "absent"


# ══════════════════════════════════════════════════════════════════
# A9 — التصحيحُ بعد الاعتماد: صفٌّ جديدٌ بسببٍ لا تعديل
# ══════════════════════════════════════════════════════════════════


def test_a9_a_correction_after_approval_needs_a_reason(session, teacher, holder, kid):
    original = _submit(teacher, session, kid, "absent")
    decide_entry(holder, original, approve=True)
    with pytest.raises(EntryError) as caught:
        _submit(teacher, session, kid, "present")
    assert caught.value.code == "reason_required"


def test_a9_a_correction_is_a_new_pending_row_and_the_effective_row_waits(
    session, teacher, holder, kid
):
    original = _submit(teacher, session, kid, "absent")
    decide_entry(holder, original, approve=True)
    fix = _submit(teacher, session, kid, "present", correction_reason="دخل قبل الجرس")
    assert fix.supersedes_id == original.pk
    assert fix.correction_reason == "دخل قبل الجرس"
    assert state_of(fix) == "pending"
    assert state_of(original) == "superseded"
    assert _row(session, kid).status == "absent"  # الفعّالُ لا يتغيّر قبل اعتماد التصحيح
    decide_entry(holder, fix, approve=True)
    assert _row(session, kid).status == "present"


def test_a9_the_unchanged_status_is_not_a_correction(session, teacher, holder, kid):
    original = _submit(teacher, session, kid, "absent")
    decide_entry(holder, original, approve=True)
    with pytest.raises(EntryError) as caught:
        _submit(teacher, session, kid, "absent", correction_reason="لا جديد")
    assert caught.value.code == "unchanged"


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


def test_s5_the_original_teachers_entry_stays_and_the_new_teacher_adds_a_version(
    session, teacher, other_teacher, kid
):
    original = _submit(teacher, session, kid, "absent")
    session.original_teacher = teacher
    session.teacher = other_teacher
    session.save(update_fields=["teacher", "original_teacher"])
    revised = _submit(other_teacher, session, kid, "present")
    assert AttendanceEntry.objects.filter(pk=original.pk, status="absent").exists()
    assert revised.supersedes_id == original.pk
    assert revised.entered_by_id == other_teacher.id


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


def test_m2_a_wingless_ordinary_section_stays_pending(school, year, teacher, bells):
    """الجناحُ الفارغُ خطأً لا يجعل الإدخالَ نهائيّاً."""
    stray = ClassGroupFactory(
        school=school, grade="G8", section="3", level_type="prep", academic_year=year, wing=None
    )
    student = UserFactory(full_name="طالبٌ عاديّ", national_id="29000002011")
    StudentEnrollmentFactory(student=student, class_group=stray, enrolled_at=ENROLLED)
    sess = Session.objects.create(
        school=school,
        class_group=stray,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    entry = submit_entry(teacher, sess, student, "absent", now=at(8, 10))
    assert state_of(entry) == "pending"
    assert _row(sess, student) is None
    assert not AttendanceDecision.objects.exists()


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


def test_l1_a_decision_cannot_be_updated_or_deleted_through_the_orm(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    decision, _ = decide_entry(holder, entry, approve=True)
    decision.reason = "x"
    with pytest.raises(PermissionDenied):
        decision.save()
    with pytest.raises(PermissionDenied):
        decision.delete()
    with pytest.raises(PermissionDenied):
        AttendanceDecision.objects.filter(pk=decision.pk).update(decision="rejected")
    with pytest.raises(PermissionDenied):
        AttendanceDecision.objects.all().delete()


def _raw(sql, *params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_l1_the_database_refuses_update_and_delete_on_both_tables(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True)
    for table, column, value in (
        ("operations_attendanceentry", "status", "present"),
        ("operations_attendancedecision", "reason", "x"),
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            _raw(f"UPDATE {table} SET {column} = %s", value)
        with pytest.raises(DatabaseError), transaction.atomic():
            _raw(f"DELETE FROM {table}")
    assert AttendanceEntry.objects.filter(pk=entry.pk, status="absent").exists()


def test_l1_the_erasure_flag_allows_delete_only_never_update(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True)
    with transaction.atomic():
        _raw("SELECT set_config('app.attendance_erasure', 'on', true)")
        with pytest.raises(DatabaseError), transaction.atomic():
            _raw("UPDATE operations_attendanceentry SET status = 'present'")
        _raw("DELETE FROM operations_attendancedecision")
        _raw("DELETE FROM operations_attendanceentry")
    assert not AttendanceEntry.objects.exists()


def test_l2_deciding_writes_an_audit_line_with_the_actor_role_and_time(
    session, teacher, holder, kid
):
    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True)
    line = _audits("create").filter(changes__decision="approved").get()
    assert line.user_id == holder.id
    assert line.changes["role"] == "admin_supervisor"
    assert line.timestamp is not None


def test_l2_rejecting_writes_an_audit_line_with_the_reason(session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=False, reason="خطأ")
    line = _audits("create").filter(changes__decision="rejected").get()
    assert line.changes["reason"] == "خطأ"


# ══════════════════════════════════════════════════════════════════
# تقرير «غيرُ معتمَد بعد X ساعة» — قراءةٌ فقط للنائب
# ══════════════════════════════════════════════════════════════════


def test_the_unapproved_report_lists_old_pending_heads_only(school, session, teacher, holder, kid):
    entry = _submit(teacher, session, kid, "absent")
    entered = entry.entered_at
    soon = entered + dt.timedelta(hours=1)
    later = entered + dt.timedelta(hours=30)
    assert unapproved_report(school, older_than_hours=24, now=soon) == []
    rows = unapproved_report(school, older_than_hours=24, now=later)
    assert [r.entry.pk for r in rows] == [entry.pk]
    assert rows[0].age_hours >= 30
    decide_entry(holder, entry, approve=True)
    assert unapproved_report(school, older_than_hours=24, now=later) == []


def test_the_unapproved_report_skips_superseded_entries(school, session, teacher, kid):
    first = _submit(teacher, session, kid, "absent")
    second = _submit(teacher, session, kid, "present")
    later = first.entered_at + dt.timedelta(hours=30)
    assert [r.entry.pk for r in unapproved_report(school, older_than_hours=24, now=later)] == [
        second.pk
    ]


def test_the_unapproved_report_is_per_school(session, teacher, kid):
    from tests.conftest import SchoolFactory

    entry = _submit(teacher, session, kid, "absent")
    later = entry.entered_at + dt.timedelta(hours=30)
    assert unapproved_report(SchoolFactory(), older_than_hours=24, now=later) == []


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


def test_m3_erasing_a_student_removes_his_ledger_and_logs_the_counts(
    school, session, teacher, holder, kid
):
    from core.models import ErasureRequest
    from governance.erasure_service import ErasureService

    entry = _submit(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True)
    fix = _submit(teacher, session, kid, "present", correction_reason="دخل قبل الجرس")
    assert AttendanceEntry.objects.filter(student=kid).count() == 2
    assert fix.supersedes_id == entry.pk

    admin = UserFactory(full_name="مدير المحو", national_id="29000003010", is_superuser=True)
    request = ErasureRequest.objects.create(
        school=school,
        student=kid,
        requested_by=admin,
        reason="طلبُ محو",
        status="approved",
        reviewed_by=admin,
    )
    summary = ErasureService.execute(request)

    assert not AttendanceEntry.objects.filter(student=kid).exists()
    assert not AttendanceDecision.objects.filter(entry__student=kid).exists()
    assert summary["models"]["AttendanceEntry"] == 2
    assert summary["models"]["AttendanceDecision"] == 1
    line = AuditLog.objects.filter(
        action="delete", model_name="other", object_repr__contains="محوُ سجلّ طالب"
    ).get()
    assert line.changes == {"decisions": 1, "entries": 2}


def test_m3_the_erasure_flag_does_not_leak_to_the_next_transaction(session, teacher, kid):
    """علَمُ المحو محلّيٌّ في المعاملة (set_config … true): ما بعدها يُرفض فيه الحذف."""
    from operations.attendance_entries import erase_attendance_ledger

    _submit(teacher, session, kid, "absent")
    erase_attendance_ledger(kid)
    entry = _submit(teacher, session, kid, "absent")
    with pytest.raises(DatabaseError), transaction.atomic():
        _raw("DELETE FROM operations_attendanceentry WHERE id = %s", str(entry.pk))
    assert AttendanceEntry.objects.filter(pk=entry.pk).exists()
