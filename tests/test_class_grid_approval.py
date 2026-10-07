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
