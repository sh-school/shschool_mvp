"""اعتمادُ جدول الشعبة (W-20261006-005، قرارُ المالك D-239م): حاملُ الجناح يعتمد ما كتبه بنفسه بأساس `wing_holder_self` وتدقيقٍ بعلامة، والقيادةُ لا
تعتمد ما كتبته، والمفتاحُ مطفأً يعيد المنعَ حرفاً، و«الحاضرُ الافتراضيّ» خارجَ اعتماد الحصّة له إجراءٌ منفصلٌ بتأكيدٍ وعدد، وملخّصُ القيادة بلا أسماء.
"""

import pytest
from django.urls import reverse

from operations.attendance_entries import EntryRefusedError, decide_entry
from operations.models import AttendanceDecision, AttendanceEntry, StudentAttendance
from operations.services import class_grid as grid
from operations.services.attendance_teacher import TeacherAttendanceService
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff, at
from tests.test_class_grid import _grid_on, assigned, clock, kids, subject  # noqa: F401

pytestmark = pytest.mark.django_db


def _write(user, school, klass, kids, status="absent", *, fill=False, number=1):
    return grid.save_column(
        user,
        school,
        klass.id,
        number,
        [{"student": str(kids[0].pk), "status": status, "head": ""}],
        fill_empty=fill,
        now=at(9, 0),
    )


def test_the_wing_holder_approves_what_he_wrote_himself_with_a_marked_basis(
    school, assigned, holder, kids, clock
):
    _write(holder, school, assigned, kids)
    entry = AttendanceEntry.objects.get()

    decision, created = decide_entry(holder, entry, approve=True)

    assert created and decision.basis == "wing_holder_self"
    assert (
        decision.evidence["self_entered"] is True and decision.evidence["default_present"] is False
    )
    assert StudentAttendance.objects.get(student=kids[0]).status == "absent"


def test_the_holder_approving_a_teachers_entry_is_an_ordinary_wing_holder_decision(
    school, assigned, teacher, holder, kids, clock
):
    _write(teacher, school, assigned, kids)
    decision, _ = decide_entry(holder, AttendanceEntry.objects.get(), approve=True)
    assert decision.basis == "wing_holder" and decision.evidence["self_entered"] is False


@pytest.mark.parametrize("role", ["principal", "vice_admin"])
def test_the_leadership_never_approves_what_it_wrote(school, assigned, kids, clock, role):
    boss = _staff(school, role, f"قيادة {role}", f"2900000{abs(hash(role)) % 10**4:04d}77")
    _write(boss, school, assigned, kids)
    with pytest.raises(EntryRefusedError) as refused:
        decide_entry(boss, AttendanceEntry.objects.get(), approve=True)
    assert refused.value.reason == "own_entry"
    assert not AttendanceDecision.objects.exists()


def test_with_the_switch_off_the_old_prohibition_returns_literally(
    settings, school, assigned, holder, kids, clock
):
    _write(holder, school, assigned, kids)
    settings.PROVISIONAL_GRID_ENABLED = False
    with pytest.raises(EntryRefusedError) as refused:
        decide_entry(holder, AttendanceEntry.objects.get(), approve=True)
    assert refused.value.reason == "own_entry"


def test_the_default_present_is_outside_the_session_approval(
    school, assigned, teacher, holder, kids, clock
):
    _write(teacher, school, assigned, kids, fill=True)  # واحدٌ مرصودٌ وإثنان افتراضيّان
    group = TeacherAttendanceService.approval_groups(holder, school)[0]
    assert (group.defaults, group.regular, group.present) == (2, 1, 0)

    approved, _skipped = TeacherAttendanceService.approve_session(holder, school, group.session.id)

    assert approved == 1
    assert AttendanceEntry.objects.filter(origin="grid_default", decision__isnull=True).count() == 2


def test_approving_the_defaults_needs_a_confirmation_and_the_exact_count(
    client_as, school, assigned, teacher, holder, kids, clock
):
    _write(teacher, school, assigned, kids, fill=True)
    session_id = AttendanceEntry.objects.first().session_id
    url = reverse("attendance_approve_defaults", args=[session_id])
    client = client_as(holder)

    assert client.post(url, {"count": "2"}).status_code == 302  # بلا تأكيد
    assert client.post(url, {"confirm": "1", "count": "1"}).status_code == 302  # عددٌ خطأ
    assert not AttendanceDecision.objects.exists()

    client.post(url, {"confirm": "1", "count": "2"})
    decisions = AttendanceDecision.objects.filter(entry__origin="grid_default")
    assert decisions.count() == 2 and all(d.evidence["default_present"] for d in decisions)


def test_the_leadership_summary_counts_self_approvals_without_names(
    settings, school, assigned, teacher, holder, kids, clock, monkeypatch
):
    _write(holder, school, assigned, kids)
    decide_entry(holder, AttendanceEntry.objects.get(), approve=True)
    boss = _staff(school, "principal", "المدير", "29000005555")
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: at(9, 0).date())

    summary = TeacherAttendanceService.self_approval_summary(boss, school)
    assert summary["counts"] == [1] and summary["alert"] is False
    settings.ATTENDANCE_SELF_APPROVAL_ALERT = 0
    assert TeacherAttendanceService.self_approval_summary(boss, school)["alert"] is True
    assert TeacherAttendanceService.self_approval_summary(teacher, school) is None


def test_the_column_button_approves_the_whole_period_including_the_defaults(
    school, assigned, teacher, holder, kids, clock
):
    _write(teacher, school, assigned, kids, fill=True)  # واحدٌ مرصودٌ وإثنان افتراضيّان
    page = grid.page(holder, school, assigned.id, now=at(9, 0))
    column = next(c for c in page.columns if c.number == 1)
    assert column.pending == 3 and column.approvable

    result = grid.approve_column(holder, school, assigned.id, 1)

    assert result == {"approved": 3, "skipped": 0}
    assert AttendanceDecision.objects.count() == 3
    assert grid.page(holder, school, assigned.id, now=at(9, 0)).approvable_columns == []


def test_the_teacher_gets_no_approve_button_and_cannot_approve_the_column(
    school, assigned, teacher, kids, clock
):
    _write(teacher, school, assigned, kids, fill=True)
    page = grid.page(teacher, school, assigned.id, now=at(9, 0))
    assert not any(c.approvable for c in page.columns)
    with pytest.raises(grid.GridRefusedError) as refused:
        grid.approve_column(teacher, school, assigned.id, 1)
    assert refused.value.reason == "not_approver"
    assert not AttendanceDecision.objects.exists()


def test_the_approve_column_endpoint_is_post_only_and_returns_the_counts(
    client_as, school, assigned, teacher, holder, kids, clock
):
    _write(teacher, school, assigned, kids)
    url = reverse("class_grid_approve", args=[assigned.id])
    client = client_as(holder)
    assert client.get(url).status_code == 405
    response = client.post(url, {"period": "1"})
    assert response.status_code == 200 and response.json()["approved"] == 1


def test_the_wing_supervisors_old_sheet_opens_the_grid_with_the_switch_on(
    client_as, school, assigned, holder, clock
):
    url = reverse("wings:record_section", args=[assigned.id])
    response = client_as(holder).get(url)
    assert response.status_code == 302
    assert response["Location"] == reverse("class_grid", args=[assigned.id])


def test_the_old_sheet_stays_with_the_switch_off_or_another_day(
    settings, client_as, school, assigned, holder, clock
):
    url = reverse("wings:record_section", args=[assigned.id])
    other_day = client_as(holder).get(url + "?date=2020-01-05")
    assert other_day.status_code != 302 or "/grid/" not in other_day["Location"]
    settings.PROVISIONAL_GRID_ENABLED = False
    off = client_as(holder).get(url)
    assert off.status_code != 302 or "/grid/" not in off["Location"]


# ── الرصد النهائيّ بلا اعتماد (قرارُ المالك 2026-10-07) ─────────────────────────────────────────


@pytest.fixture
def direct(settings, assigned):
    settings.ATTENDANCE_GRID_DIRECT_WINGS = assigned.wing.code
    return assigned


def test_a_direct_wing_teacher_entry_is_final_and_reaches_the_record_at_once(
    school, direct, teacher, kids, clock
):
    _write(teacher, school, direct, kids)
    decision = AttendanceDecision.objects.get()
    assert decision.basis == "direct_entry" and decision.evidence["rule"] == "direct_wing"
    assert StudentAttendance.objects.get(student=kids[0]).status == "absent"
    page = grid.page(teacher, school, direct.id, now=at(9, 0))
    assert page.approvable_columns == []


def test_without_the_direct_setting_the_entry_still_waits_for_the_holder(
    school, assigned, teacher, kids, clock
):
    _write(teacher, school, assigned, kids)
    assert not AttendanceDecision.objects.exists()
    assert not StudentAttendance.objects.exists()


def test_the_supervisor_replaces_the_teachers_entry_directly_with_a_mandatory_reason_and_the_teacher_is_told(
    school, direct, teacher, holder, kids, clock
):
    from notifications.models import InAppNotification

    _write(teacher, school, direct, kids, status="present")
    head = str(AttendanceEntry.objects.get().pk)
    cell = [{"student": str(kids[0].pk), "status": "absent", "head": head}]

    refused = grid.save_column(holder, school, direct.id, 1, cell, now=at(9, 5))
    assert refused.errors and refused.errors[0]["code"] == "reason_required", "بلا سببٍ لا تصحيح"
    assert StudentAttendance.objects.get(student=kids[0]).status == "present"

    grid.save_column(
        holder, school, direct.id, 1, cell, reason="الطالبُ غائبٌ بشهادة البوابة", now=at(9, 5)
    )
    assert StudentAttendance.objects.get(student=kids[0]).status == "absent"
    assert AttendanceEntry.objects.count() == 2  # السلسلةُ كاملةٌ لا تُمحى
    assert AttendanceEntry.objects.filter(supersedes__isnull=False).get().correction_reason == (
        "الطالبُ غائبٌ بشهادة البوابة"
    )
    note = InAppNotification.objects.get(user=teacher)
    assert "عدّل مشرفُ الجناح" in note.title


def test_in_a_direct_wing_the_approve_button_is_gone_and_only_the_supervisor_sees_the_reason_field(
    client_as, school, direct, teacher, holder, kids, clock
):
    _write(teacher, school, direct, kids, status="absent")
    url = reverse("class_grid", args=[direct.id])

    teacher_page = client_as(teacher).get(url).content.decode()
    holder_page = client_as(holder).get(url).content.decode()

    assert "اعتماد الحصّة" not in teacher_page and "اعتماد الحصّة" not in holder_page
    assert 'data-reason-always="1"' in holder_page and "data-grid-reason" in holder_page
    assert 'data-reason-always="1"' not in teacher_page


def test_the_direct_wings_key_is_empty_by_default_in_code():
    """المفتاحُ فارغٌ افتراضيّاً في الكود (D-262م): تفعيلُه في الإنتاج أمرُ المالك لـ0601 بعد المعاينة."""
    from pathlib import Path

    base = (Path(__file__).resolve().parent.parent / "shschool" / "settings" / "base.py").read_text(
        encoding="utf-8"
    )

    assert (
        'ATTENDANCE_GRID_DIRECT_WINGS = os.environ.get("ATTENDANCE_GRID_DIRECT_WINGS", "")' in base
    )


def test_settling_the_old_pending_entries_decides_them_as_direct(
    settings, school, assigned, teacher, kids, clock
):
    from operations.attendance_entries import settle_pending_as_direct

    _write(teacher, school, assigned, kids)
    settings.ATTENDANCE_GRID_DIRECT_WINGS = assigned.wing.code
    assert settle_pending_as_direct(school) == 1 and not AttendanceDecision.objects.exists()
    assert settle_pending_as_direct(school, apply=True) == 1
    assert AttendanceDecision.objects.get().basis == "direct_entry"
    assert StudentAttendance.objects.get(student=kids[0]).status == "absent"


def test_the_end_of_day_sweep_checks_the_gates_of_todays_absentees(
    monkeypatch, school, direct, teacher, kids, clock
):
    import datetime as dt

    from operations.end_of_day import sweep_absence_gates
    from operations.services import AttendanceService

    _write(teacher, school, direct, kids)
    seen = []
    monkeypatch.setattr(
        AttendanceService,
        "raise_absence_alerts",
        staticmethod(lambda student, school, on=None: seen.append((student.pk, on))),
    )
    day = AttendanceEntry.objects.get().session.date
    assert sweep_absence_gates(school, day) == 1
    assert seen == [(kids[0].pk, day)]
    assert sweep_absence_gates(school, day + dt.timedelta(days=1)) == 0


def test_the_settle_command_counts_by_default_and_writes_only_with_apply(
    settings, school, assigned, teacher, kids, clock, capsys
):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    _write(teacher, school, assigned, kids)  # معلَّقٌ: المفتاحُ فارغ
    settings.ATTENDANCE_GRID_DIRECT_WINGS = assigned.wing.code

    call_command("settle_direct_entries")
    assert "سيُسوّى فعلاً 1" in capsys.readouterr().out and not AttendanceDecision.objects.exists()
    call_command("settle_direct_entries", "--count")
    assert not AttendanceDecision.objects.exists(), "العدُّ لا يكتب"
    with pytest.raises(CommandError):
        call_command("settle_direct_entries", "--count", "--apply")

    call_command("settle_direct_entries", "--apply")
    assert "سُوِّي 1" in capsys.readouterr().out
    assert AttendanceDecision.objects.get().basis == "direct_entry"
    assert StudentAttendance.objects.get(student=kids[0]).status == "absent"


def test_an_empty_key_or_stray_commas_never_make_a_wing_direct(settings, school, assigned):
    """ "".split(",") يعطي {""}: جناحٌ برمزٍ فارغٍ كان يُعدّ مباشراً (ملاحظة 0104)."""
    from core.models import Wing
    from operations.attendance_policy import is_direct_class

    for raw in ("", ",", " , ,"):
        settings.ATTENDANCE_GRID_DIRECT_WINGS = raw
        assert not is_direct_class(assigned), repr(raw)
    Wing.objects.filter(pk=assigned.wing_id).update(code="")
    assigned.wing.refresh_from_db()
    settings.ATTENDANCE_GRID_DIRECT_WINGS = ","
    assert not is_direct_class(assigned), "رمزٌ فارغٌ مع مفتاحٍ فارغ"
    settings.ATTENDANCE_GRID_DIRECT_WINGS = "*"
    assert is_direct_class(assigned), "النجمةُ لكلّ الأجنحة"


def test_the_bulk_settlement_leaves_a_reason_and_an_operator_audit_line_without_names(
    settings, school, assigned, teacher, kids, clock
):
    from core.models import AuditLog
    from operations.attendance_entries import settle_pending_as_direct

    _write(teacher, school, assigned, kids)
    settings.ATTENDANCE_GRID_DIRECT_WINGS = assigned.wing.code

    assert settle_pending_as_direct(school, apply=True) == 1

    decision = AttendanceDecision.objects.get()
    assert decision.reason == "تسوية جماعية" and decision.evidence["bulk_settlement"] is True
    audit = AuditLog.objects.get(object_repr__contains="تسويةٌ جماعيّةٌ")
    assert audit.changes["settled"] == 1 and audit.changes["wings"] == [assigned.wing.code]
    assert "at" in audit.changes
    assert teacher.full_name not in str(audit.changes)


def test_the_correction_reason_is_stored_in_the_entry_not_copied_into_the_audit(
    school, direct, teacher, holder, kids, clock
):
    from core.models import AuditLog

    _write(teacher, school, direct, kids, status="present")
    head = str(AttendanceEntry.objects.get().pk)
    secret = "سببٌ حرٌّ فيه نصٌّ يخصّ الطالب"

    grid.save_column(
        holder,
        school,
        direct.id,
        1,
        [{"student": str(kids[0].pk), "status": "absent", "head": head}],
        reason=secret,
        now=at(9, 5),
    )

    assert (
        AttendanceEntry.objects.filter(supersedes__isnull=False).get().correction_reason == secret
    )
    assert not any(secret in str(row.changes) for row in AuditLog.objects.all())
