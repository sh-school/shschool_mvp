"""تصحيحُ المشرف لما لم يشاهده: سببٌ ونوعُ دليلٍ إلزاميّان ووسمُ «تصحيحٌ دون معاينة» يراه المعلّمُ والنائب (W-20261002-020).

حاملُ الجناح (أو القيادةُ حين لا حاملَ فعليّاً) قد يصحّح رصداً معتمَداً بناءً على ما بلغه — اتّصالُ وليّ أمر، سجلُّ بوّابة، عيادة —
لا على ما رآه. فلا يُكتب ذلك بصمت: سببٌ ونوعُ دليلٍ إلزاميّان، ووسمٌ على الرصد يظهر للمعلّم صاحبِ الحصّة وللنائب، وسطرُ تدقيقٍ
بقبلٍ وبعد. ولا يصحّح غيرُ من له الاعتماد، ولا المعلّمُ على حصّته، ولا يُكتب فوق رصدٍ مصدرُه العيادةُ أو البوّابة.
"""

import pytest

from core.models import AuditLog
from operations.attendance_entries import (
    EVIDENCE_TYPES,
    EntryConflictError,
    EntryError,
    EntryRefusedError,
    correct_without_observation,
    decide_entry,
    submit_entry,
)
from operations.models import AttendanceDecision, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff, at

pytestmark = pytest.mark.django_db

NOW = at(9, 0)


def _approved(teacher, holder, session, kid, status="absent"):
    entry = submit_entry(teacher, session, kid, status, now=at(7, 30))
    decide_entry(holder, entry, approve=True, now=at(7, 31))
    return entry


def _correct(user, session, kid, status="present", **kwargs):
    kwargs.setdefault("reason", "اتّصل وليُّ الأمر وأكّد حضوره")
    kwargs.setdefault("evidence_type", "parent_contact")
    return correct_without_observation(user, session, kid, status, now=NOW, **kwargs)


def _audits():
    return AuditLog.objects.filter(object_repr__contains="تصحيحٌ دون معاينة")


def test_the_holder_corrects_an_approved_row_and_it_is_tagged(session, teacher, holder, kid):
    _approved(teacher, holder, session, kid, "absent")
    row = _correct(holder, session, kid, "present")
    row.refresh_from_db()
    assert (row.status, row.source, row.marked_by_id) == ("present", "supervisor", holder.id)
    tag = row.unobserved_correction
    assert tag["type"] == "parent_contact"
    assert tag["reason"] == "اتّصل وليُّ الأمر وأكّد حضوره"
    assert tag["by"] == str(holder.id)
    assert tag["before"] == {"status": "absent", "source": "teacher"}


def test_a_correction_writes_an_audit_line_with_before_and_after(session, teacher, holder, kid):
    _approved(teacher, holder, session, kid, "absent")
    _correct(holder, session, kid, "present")
    (audit,) = _audits()
    assert audit.user_id == holder.id
    assert audit.changes["before"]["status"] == "absent"
    assert audit.changes["after"]["status"] == "present"
    assert audit.changes["evidence_type"] == "parent_contact"


def test_a_reason_and_a_known_evidence_type_are_mandatory(session, teacher, holder, kid):
    _approved(teacher, holder, session, kid)
    with pytest.raises(EntryError) as no_reason:
        _correct(holder, session, kid, reason="  ")
    assert no_reason.value.code == "reason_required"
    with pytest.raises(EntryError) as bad_type:
        _correct(holder, session, kid, evidence_type="hunch")
    assert bad_type.value.code == "bad_evidence"
    with pytest.raises(EntryError) as too_long:
        _correct(holder, session, kid, reason="س" * 301)
    assert too_long.value.code == "reason_too_long"
    assert StudentAttendance.objects.get(session=session, student=kid).status == "absent"


def test_every_evidence_type_is_accepted(session, teacher, holder, kid):
    _approved(teacher, holder, session, kid)
    for evidence in EVIDENCE_TYPES:
        _correct(holder, session, kid, "present", evidence_type=evidence)


def test_the_session_teacher_cannot_correct_his_own_session(session, teacher, holder, kid):
    _approved(teacher, holder, session, kid)
    with pytest.raises(EntryRefusedError) as raised:
        _correct(teacher, session, kid)
    assert raised.value.reason == "own_session"


def test_the_holder_of_another_wing_cannot_correct(school, year, session, teacher, holder, kid):
    from core.models import Wing

    other = _staff(school, "admin_supervisor", "حاملٌ آخر", "29000006001")
    Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
    )
    _approved(teacher, holder, session, kid)
    with pytest.raises(EntryRefusedError) as raised:
        _correct(other, session, kid)
    assert raised.value.reason == "not_holder"


def test_leadership_corrects_only_when_there_is_no_effective_holder(
    school, wing, session, teacher, holder, kid
):
    leader = _staff(school, "vice_admin", "النائب", "29000006002")
    _approved(teacher, holder, session, kid)
    with pytest.raises(EntryRefusedError):
        _correct(leader, session, kid)
    wing.supervisor = None
    wing.save(update_fields=["supervisor"])
    assert _correct(leader, session, kid).status == "present"


def test_the_developer_cannot_correct(school, session, teacher, holder, kid):
    developer = _staff(school, "platform_developer", "المطوّر", "29000006003")
    _approved(teacher, holder, session, kid)
    with pytest.raises(EntryRefusedError) as raised:
        _correct(developer, session, kid)
    assert raised.value.reason == "developer"


def test_a_clinic_or_gate_row_is_never_overwritten(session, holder, kid):
    StudentAttendance.objects.create(
        school=session.school, session=session, student=kid, status="absent", source="clinic"
    )
    with pytest.raises(EntryConflictError):
        _correct(holder, session, kid)
    assert StudentAttendance.objects.get(session=session, student=kid).source == "clinic"


def test_a_correction_over_a_pending_entry_settles_it_with_a_decision(
    session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    _correct(holder, session, kid, "present")
    decision = AttendanceDecision.objects.get(entry=entry)
    assert (decision.decision, decision.basis) == ("rejected", "supervisor_record")


def test_a_correction_with_no_previous_row_creates_a_tagged_one(session, holder, kid):
    row = _correct(holder, session, kid, "absent")
    assert row.unobserved_correction["before"] == {"status": None, "source": None}
    assert StudentAttendance.objects.filter(session=session, student=kid).count() == 1


def test_a_correction_that_turns_present_clears_a_previous_excuse_fields(
    session, teacher, holder, kid
):
    _approved(teacher, holder, session, kid, "absent")
    row = StudentAttendance.objects.get(session=session, student=kid)
    row.excuse_type = "medical"
    row.save(update_fields=["excuse_type"])
    corrected = _correct(holder, session, kid, "present")
    corrected.refresh_from_db()
    assert corrected.excuse_type == ""


# ══════════════════════════════════════════════════════════════════
# الشاشة: من يصل، وما يُعرض
# ══════════════════════════════════════════════════════════════════
