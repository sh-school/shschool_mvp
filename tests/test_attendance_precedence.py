"""أسبقيّةُ الحالة في الحصّة (W-20261004-025، D-420م): قرارُ تصحيح ← إدخالُ معلّم ← رصدُ مشرف ← الخروجُ عرضٌ فقط."""

import pytest

from operations.attendance_entries import submit_entry
from operations.attendance_precedence import (
    NO_SOURCE,
    OVERWRITABLE_SOURCES,
    Mark,
    may_overwrite,
    resolve_attendance,
)
from operations.models import StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

# ── الدالّةُ الخالصة ──────────────────────────────────────────


def test_correction_beats_teacher_beats_supervisor():
    fix, teacher, sup = Mark("excused"), Mark("absent"), Mark("present")
    assert (
        resolve_attendance(correction=fix, teacher_entry=teacher, supervisor=sup).status
        == "excused"
    )
    assert resolve_attendance(teacher_entry=teacher, supervisor=sup).status == "absent"
    assert resolve_attendance(supervisor=sup).status == "present"


def test_supervisor_fills_only_the_gap():
    won = resolve_attendance(teacher_entry=Mark("late", 5), supervisor=Mark("present"))
    assert (won.status, won.late_minutes, won.source) == ("late", 5, "teacher_entry")


def test_empty_when_nobody_spoke():
    assert resolve_attendance().source == NO_SOURCE


def test_exit_marks_away_and_never_flips_the_status():
    won = resolve_attendance(supervisor=Mark("present"), left_and_not_returned=True)
    assert won.status == "present"
    assert won.away is True


def test_clinic_gate_system_are_not_overwritable():
    assert OVERWRITABLE_SOURCES == {"teacher", "teacher_late", "supervisor"}
    for source in ("clinic", "gate", "system"):
        assert not may_overwrite(source)


# ── الكتابةُ على القاعدة ──────────────────────────────────────


@pytest.mark.django_db
def test_teacher_entry_replaces_an_earlier_supervisor_mark(school, session, teacher, kid, holder):
    StudentAttendance.objects.create(
        school=school,
        session=session,
        student=kid,
        status="present",
        source="supervisor",
        marked_by=holder,
        whereabouts="out_permit",
    )
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    row = StudentAttendance.objects.get(session=session, student=kid)
    assert (row.status, row.source, row.whereabouts) == ("absent", "teacher", "")
    assert row.exit_id is None


@pytest.mark.django_db
def test_a_clinic_row_is_still_never_overwritten(school, session, teacher, kid, holder):
    from operations.attendance_entries import EntryConflictError

    StudentAttendance.objects.create(
        school=school,
        session=session,
        student=kid,
        status="excused",
        source="clinic",
        marked_by=holder,
    )
    with pytest.raises(EntryConflictError):
        submit_entry(teacher, session, kid, "absent", now=at(7, 30))


@pytest.mark.django_db
def test_period_end_never_flips_a_present_student_who_left(school, session, kid, holder):
    from operations.exit_reflection import finalize_exits_for_day

    StudentAttendance.objects.create(
        school=school,
        session=session,
        student=kid,
        status="present",
        source="supervisor",
        marked_by=holder,
    )
    finalize_exits_for_day(school, session.date, at(23, 0))
    assert StudentAttendance.objects.get(session=session, student=kid).status == "present"
