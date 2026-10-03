"""حاملُ الجناح الذي لا يصلح حاملاً فعليّاً يُعامَل كغائب فتعتمد القيادةُ (حكمُ 0105 P1/P2، W-20261002-020).

العلّةُ: لو كان معلّمُ الحصّة هو حاملَ جناح شعبتها، ردّت `can_approve` حاملَه بـ`own_session` ولم تأذن للقيادة لأنّ
الحاملَ ليس `None` — فلا أحدَ يعتمد ولا يظهر في تقرير «غيرُ معتمَد» (`holder_missing=False`). ومثلُه حاملٌ غادر المدرسة أو
أُوقفت عضويّتُه: اسمٌ يحجب القيادةَ ولا يستطيع القرار. فالفحصُ في `approval_holder` نفسِه لا في `can_approve` وحدَها.
"""

import pytest

from operations.attendance_entries import (
    EntryRefusedError,
    decide_entry,
    state_of,
    submit_entry,
    unapproved_report,
)
from operations.attendance_policy import approval_holder, can_approve, holder_gap
from operations.models import StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _cover, _staff, at

pytestmark = pytest.mark.django_db

NOW = at(7, 30)
LATER = at(13, 0)


def _enter(teacher, session, kid):
    return submit_entry(teacher, session, kid, "absent", now=NOW)


def _leader(school):
    return _staff(school, "vice_admin", "النائب", "29000003001")


def _make_the_teacher_the_wing_holder(wing, teacher):
    wing.supervisor = teacher
    wing.save(update_fields=["supervisor"])


def test_p1_a_teacher_who_holds_the_wing_leaves_the_wing_without_an_effective_holder(
    wing, session, teacher
):
    _make_the_teacher_the_wing_holder(wing, teacher)
    assert holder_gap(session) == "holder_is_teacher"
    assert approval_holder(session) is None


def test_p1_the_teacher_holder_cannot_approve_his_own_session_but_leadership_can(
    school, wing, session, teacher, kid
):
    _make_the_teacher_the_wing_holder(wing, teacher)
    leader = _leader(school)
    entry = _enter(teacher, session, kid)
    assert can_approve(teacher, session, entered_by=teacher).reason == "own_session"
    with pytest.raises(EntryRefusedError):
        decide_entry(teacher, entry, approve=True)
    decision, created = decide_entry(leader, entry, approve=True, now=LATER)
    assert created
    assert decision.basis == "leadership_holder_is_teacher"
    assert state_of(entry) == "approved"
    assert StudentAttendance.objects.get(session=session, student=kid).status == "absent"


def test_p1_the_stuck_case_shows_in_the_unapproved_report_as_holder_missing(
    school, wing, session, teacher, kid
):
    _make_the_teacher_the_wing_holder(wing, teacher)
    _enter(teacher, session, kid)
    (row,) = unapproved_report(school, older_than_hours=1, now=LATER)
    assert row.holder_missing is True
    assert row.holder_gap == "holder_is_teacher"


def test_p1_a_covering_substitute_who_is_the_teacher_is_the_same_gap(
    school, wing, session, teacher, holder, kid
):
    _cover(wing, teacher, SUNDAY, None, by=holder)
    assert holder_gap(session) == "holder_is_teacher"
    leader = _leader(school)
    entry = _enter(teacher, session, kid)
    decision, _ = decide_entry(leader, entry, approve=True, now=LATER)
    assert decision.basis == "leadership_holder_is_teacher"


def test_p2_a_holder_without_an_active_membership_does_not_block_leadership(
    school, wing, session, teacher, holder, kid
):
    holder.memberships.update(is_active=False)
    assert holder_gap(session) == "holder_inactive"
    assert approval_holder(session) is None
    leader = _leader(school)
    entry = _enter(teacher, session, kid)
    assert not can_approve(holder, session, entered_by=teacher)
    decision, _ = decide_entry(leader, entry, approve=True, now=LATER)
    assert decision.basis == "leadership_holder_inactive"
    # الدليلُ يحفظ من كان مسمّىً حاملاً وقتَ القرار.
    assert decision.evidence["holder_id"] == str(holder.pk)


def test_p2_the_inactive_holder_case_shows_in_the_unapproved_report(
    school, session, teacher, holder, kid
):
    holder.memberships.update(is_active=False)
    _enter(teacher, session, kid)
    (row,) = unapproved_report(school, older_than_hours=1, now=LATER)
    assert (row.holder_missing, row.holder_gap) == (True, "holder_inactive")


def test_a_healthy_holder_still_excludes_leadership_and_is_the_basis(
    school, session, teacher, holder, kid
):
    leader = _leader(school)
    entry = _enter(teacher, session, kid)
    assert holder_gap(session) is None
    assert approval_holder(session) == holder
    with pytest.raises(EntryRefusedError):
        decide_entry(leader, entry, approve=True)
    decision, _ = decide_entry(holder, entry, approve=True, now=LATER)
    assert decision.basis == "wing_holder"


def test_a_wing_without_a_supervisor_is_the_no_holder_gap(school, wing, session):
    wing.supervisor = None
    wing.save(update_fields=["supervisor"])
    assert holder_gap(session) == "no_holder"
